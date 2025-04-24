import tkinter as tk
from tkinter import messagebox, simpledialog
import datetime
import os
import re
import tempfile

# For image display
try:
    from PIL import Image, ImageTk
except ImportError:
    Image = None
    ImageTk = None

# --- Mock or real Sangaboard ---
try:
    from sangaboard import Sangaboard
except ImportError:
    class Sangaboard:
        class Illum:
            def __init__(self):
                self._cc_led = 0.0

            @property
            def cc_led(self):
                return self._cc_led

            @cc_led.setter
            def cc_led(self, val):
                print(f"[Mock] LED brightness set to {val}")
                self._cc_led = val

        def open(self):
            print("[Mock] Sangaboard opened")

        def close(self):
            print("[Mock] Sangaboard closed")

        @property
        def illumination(self):
            return Sangaboard.Illum()

        def move_rel(self, rel):
            print(f"[Mock] move_rel called with {rel}")

# --- Mock or real Camera ---
try:
    from picamzero import Camera
except ImportError:
    class Camera:
        def start_preview(self):
            print("[Mock] Camera preview started")

        def stop_preview(self):
            print("[Mock] Camera preview stopped")

        def take_photo(self, filename):
            print(f"[Mock] Photo taken and saved to {filename}")
            # Create placeholder image
            try:
                from PIL import Image
                img = Image.new('RGB', (640, 480), 'gray')
                img.save(filename)
            except Exception:
                open(filename, 'wb').close()

# Defaults
DEFAULT_FINE_INCREMENT = 50
DEFAULT_COARSE_INCREMENT = 500
DEFAULT_LED_BRIGHTNESS = 0.33

# Time parsing
def parse_time_value(time_str):
    pattern = r"^\s*((?P<days>\d+)\s*d)?\s*((?P<hours>\d+)\s*h)?\s*((?P<minutes>\d+)\s*m)?\s*((?P<seconds>\d+)\s*s)?\s*$"
    m = re.match(pattern, time_str.strip(), re.IGNORECASE)
    if not m:
        return None
    days = int(m.group('days') or 0)
    hours = int(m.group('hours') or 0)
    minutes = int(m.group('minutes') or 0)
    seconds = int(m.group('seconds') or 0)
    return days * 86400 + hours * 3600 + minutes * 60 + seconds

class App:
    def __init__(self, root):
        self.root = root
        root.title("OpenFlexure Timelapse Controller")

        # Hardware
        self.sb = Sangaboard()
        try:
            self.sb.open()
        except Exception:
            pass
        self.sb.illumination.cc_led = 0.0
        self.cam = Camera()
        self.root.protocol('WM_DELETE_WINDOW', self.cleanup)

        # State
        self.motor_increment_fine = DEFAULT_FINE_INCREMENT
        self.motor_increment_coarse = DEFAULT_COARSE_INCREMENT
        self.led_brightness = DEFAULT_LED_BRIGHTNESS
        self.timelapse_running = False
        self.previewing = False
        self.after_id = None
        self.preview_after_id = None
        self.preview_file = os.path.join(tempfile.gettempdir(), 'preview.jpg')

        # Build UI
        self.build_motor_controls()
        self.build_led_control()
        self.build_preview_control()
        self.build_timelapse_controls()

    def build_motor_controls(self):
        frame_coarse = tk.LabelFrame(self.root, text=f"Coarse Motor Control (inc: {self.motor_increment_coarse})")
        frame_coarse.pack(padx=10, pady=5)
        frame_fine = tk.LabelFrame(self.root, text=f"Fine Motor Control (inc: {self.motor_increment_fine})")
        frame_fine.pack(padx=10, pady=5)

        axes = [('X+', (1,0,0)), ('Y+', (0,1,0)), ('Z+', (0,0,1)),
                ('X-', (-1,0,0)), ('Y-', (0,-1,0)), ('Z-', (0,0,-1))]
        for idx, (txt, d) in enumerate(axes):
            rel_c = (d[0]*self.motor_increment_coarse, d[1]*self.motor_increment_coarse, d[2]*self.motor_increment_coarse)
            btn = tk.Button(frame_coarse, text=txt, command=lambda r=rel_c: self.move(r))
            btn.grid(row=idx//3, column=idx%3, padx=5, pady=5)
        for idx, (txt, d) in enumerate(axes):
            rel_f = (d[0]*self.motor_increment_fine, d[1]*self.motor_increment_fine, d[2]*self.motor_increment_fine)
            btn = tk.Button(frame_fine, text=txt, command=lambda r=rel_f: self.move(r))
            btn.grid(row=idx//3, column=idx%3, padx=5, pady=5)

    def build_led_control(self):
        led_frame = tk.LabelFrame(self.root, text="LED Brightness")
        led_frame.pack(padx=10, pady=5)
        self.led_scale = tk.Scale(led_frame, from_=0.0, to=1.0, resolution=0.01,
                                  orient='horizontal', command=self.update_led)
        self.led_scale.set(self.led_brightness)
        self.led_scale.pack(fill='x', padx=10, pady=5)

    def build_preview_control(self):
        self.preview_btn = tk.Button(self.root, text="Start Preview", command=self.toggle_preview)
        self.preview_btn.pack(pady=5)
        display = tk.LabelFrame(self.root, text="Camera View", width=400, height=300)
        display.pack(padx=10, pady=5)
        display.pack_propagate(False)
        self.image_label = tk.Label(display, text="Preview stopped")
        self.image_label.pack(expand=True)

    def build_timelapse_controls(self):
        tl = tk.LabelFrame(self.root, text="Timelapse Settings", width=400)
        tl.pack(padx=10, pady=5)
        tl.pack_propagate(False)
        tk.Label(tl, text="e.g. 1h 30m 10s", fg='gray').grid(row=0, column=0, columnspan=2)
        tk.Label(tl, text="Duration:").grid(row=1, column=0, sticky='e', padx=5)
        self.duration_entry = tk.Entry(tl)
        self.duration_entry.grid(row=1, column=1, padx=5)
        self.duration_entry.insert(0, '30m')
        tk.Label(tl, text="Frequency:").grid(row=2, column=0, sticky='e', padx=5)
        self.freq_entry = tk.Entry(tl)
        self.freq_entry.grid(row=2, column=1, padx=5)
        self.freq_entry.insert(0, '5s')

        self.start_btn = tk.Button(self.root, text="Confirm settings and start timelapse",
                                   command=self.start_timelapse)
        self.start_btn.pack(pady=10)

    def move(self, rel):
        self.sb.move_rel(list(rel))

    def update_led(self, val):
        self.led_brightness = float(val)
        if self.previewing:
            self.sb.illumination.cc_led = self.led_brightness

    def toggle_preview(self):
        if not self.previewing:
            self.sb.illumination.cc_led = self.led_brightness
            self.preview_loop()
            self.preview_btn.config(text="Stop Preview")
            self.previewing = True
        else:
            if self.preview_after_id:
                self.root.after_cancel(self.preview_after_id)
            self.sb.illumination.cc_led = 0.0
            self.preview_btn.config(text="Start Preview")
            self.previewing = False
            self.image_label.config(text="Preview stopped", image='')

    def preview_loop(self):
        self.cam.take_photo(self.preview_file)
        if Image:
            img = Image.open(self.preview_file)
            img.thumbnail((380, 280))
            self.photo = ImageTk.PhotoImage(img)
            self.image_label.config(image=self.photo)
        self.preview_after_id = self.root.after(500, self.preview_loop)

    def start_timelapse(self):
        dur = parse_time_value(self.duration_entry.get())
        freq = parse_time_value(self.freq_entry.get())
        if dur is None or dur <= 0 or freq is None or freq <= 0:
            messagebox.showerror("Error", "Invalid duration or frequency")
            return
        for widget in self.root.winfo_children():
            if isinstance(widget, tk.Button) or isinstance(widget, tk.Scale):
                widget.config(state='disabled')
        now = datetime.datetime.now()
        self.folder = now.strftime("%Y-%m-%d_%H-%M-%S")
        os.makedirs(self.folder, exist_ok=True)
        self.end_time = now + datetime.timedelta(seconds=dur)
        self.start_btn.config(text="Stop and end timelapse early",
                              command=self.stop_timelapse)
        self.timelapse_running = True
        self.capture_loop(freq)

    def stop_timelapse(self):
        if self.after_id:
            self.root.after_cancel(self.after_id)
        messagebox.showinfo("Stopped", "Timelapse stopped early")
        self.reset_controls()

    def finish_timelapse(self):
        messagebox.showinfo("Done", "Timelapse complete")
        self.reset_controls()

    def reset_controls(self):
        for widget in self.root.winfo_children():
            if isinstance(widget, tk.Button) or isinstance(widget, tk.Scale):
                widget.config(state='normal')
        self.start_btn.config(text="Confirm settings and start timelapse",
                              command=self.start_timelapse)
        self.timelapse_running = False

    def capture_loop(self, freq):
        if datetime.datetime.now() >= self.end_time:
            self.finish_timelapse()
            return
        ts = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = os.path.join(self.folder, f"{ts}.jpg")
        self.sb.illumination.cc_led = self.led_brightness
        self.cam.take_photo(filename)
        self.sb.illumination.cc_led = 0.0
        print(f"Captured: {filename}")
        if Image:
            img = Image.open(filename)
            img.thumbnail((380, 280))
            self.photo = ImageTk.PhotoImage(img)
            self.image_label.config(image=self.photo)
        self.after_id = self.root.after(int(freq * 1000), lambda: self.capture_loop(freq))

    def cleanup(self):
        if self.previewing and self.preview_after_id:
            self.root.after_cancel(self.preview_after_id)
        try:
            self.sb.illumination.cc_led = 0.0
        except Exception:
            pass
        try:
            self.sb.close()
        except Exception:
            pass
        self.root.destroy()

if __name__ == '__main__':
    root = tk.Tk()
    app = App(root)
    root.mainloop()
