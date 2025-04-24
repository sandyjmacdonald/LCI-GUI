import tkinter as tk
from tkinter import messagebox, simpledialog
import datetime
import os
import re
import contextlib

# For image display
try:
    from PIL import Image, ImageTk
except ImportError:
    Image = None
    ImageTk = None

# --- Mock hardware libraries ---
try:
    from sangaboard import Sangaboard
except ImportError:
    class Sangaboard:
        class Illum:
            def __init__(self): self._cc_led = 0.0
            @property
            def cc_led(self): return self._cc_led
            @cc_led.setter
            def cc_led(self, val): print(f"[Mock] LED brightness set to {val}"); self._cc_led = val
        def __enter__(self): return self
        def __exit__(self, exc_type, exc_val, exc_tb): pass
        @property
        def illumination(self): return Sangaboard.Illum()
        def move_rel(self, rel): print(f"[Mock] move_rel called with {rel}")

try:
    from picamzero import Camera
except ImportError:
    class Camera:
        def start_preview(self): print("[Mock] Camera preview started")
        def stop_preview(self): print("[Mock] Camera preview stopped")
        def take_photo(self, filename): print(f"[Mock] Photo taken and saved to {filename}")

# Default increments and LED brightness
DEFAULT_FINE_INCREMENT = 50
DEFAULT_COARSE_INCREMENT = 500
DEFAULT_LED_BRIGHTNESS = 0.33

# Utility to parse a time value string into seconds
def parse_time_value(time_str):
    pattern = r"^\s*((?P<days>\d+)\s*d)?\s*((?P<hours>\d+)\s*h)?\s*((?P<minutes>\d+)\s*m)?\s*((?P<seconds>\d+)\s*s)?\s*$"
    match = re.match(pattern, time_str.strip(), re.IGNORECASE)
    if not match:
        return None
    days = int(match.group('days') or 0)
    hours = int(match.group('hours') or 0)
    minutes = int(match.group('minutes') or 0)
    seconds = int(match.group('seconds') or 0)
    return days*86400 + hours*3600 + minutes*60 + seconds

class App:
    def __init__(self, root):
        self.root = root
        root.title("OpenFlexure Timelapse Controller")

        # Hardware: open persistent Sangaboard connection
        self.sb = Sangaboard()
        try:
            self.sb.open()
        except Exception:
            pass  # if open not needed or mock
        self.cam = Camera()
        self.root.protocol('WM_DELETE_WINDOW', self.cleanup)

        # State
        self.motor_increment_fine = DEFAULT_FINE_INCREMENT
        self.motor_increment_coarse = DEFAULT_COARSE_INCREMENT
        self.led_brightness = DEFAULT_LED_BRIGHTNESS
        self.timelapse_running = False
        self.after_id = None
        self.previewing = False

        # Motor control frames
        self.coarse_frame = tk.LabelFrame(root, text=f"Coarse Motor Control (inc: {self.motor_increment_coarse})")
        self.coarse_frame.pack(padx=10, pady=5)
        self.fine_frame = tk.LabelFrame(root, text=f"Fine Motor Control (inc: {self.motor_increment_fine})")
        self.fine_frame.pack(padx=10, pady=5)
        self.build_motor_controls()

        # Change increments button
        self.change_inc_btn = tk.Button(root, text="Change increments", command=self.change_increments)
        self.change_inc_btn.pack(pady=5)

        # ... rest unchanged
        self.after_id = None
        self.previewing = False

        # Motor control frames
        self.coarse_frame = tk.LabelFrame(root, text=f"Coarse Motor Control (inc: {self.motor_increment_coarse})")
        self.coarse_frame.pack(padx=10, pady=5)
        self.fine_frame = tk.LabelFrame(root, text=f"Fine Motor Control (inc: {self.motor_increment_fine})")
        self.fine_frame.pack(padx=10, pady=5)
        self.build_motor_controls()

        # Change increments button
        self.change_inc_btn = tk.Button(root, text="Change increments", command=self.change_increments)
        self.change_inc_btn.pack(pady=5)

        # LED brightness frame
        led_frame = tk.LabelFrame(root, text="LED Brightness", width=400)
        led_frame.pack(anchor='center', padx=10, pady=5)
        led_frame.pack_propagate(False)
        self.led_scale = tk.Scale(led_frame, from_=0.0, to=1.0, resolution=0.01,
                                  orient='horizontal', command=self.update_led)
        self.led_scale.set(self.led_brightness)
        self.led_scale.pack(fill='x', padx=10, pady=5)

        # Preview controls
        self.preview_btn = tk.Button(root, text="Start Preview", command=self.toggle_preview)
        self.preview_btn.pack(pady=5)

        # Camera display frame
        display = tk.LabelFrame(root, text="Camera View", width=400)
        display.pack(anchor='center', padx=10, pady=5)
        display.pack_propagate(False)
        self.image_label = tk.Label(display)
        self.image_label.pack()

        # Timelapse settings frame
        tl = tk.LabelFrame(root, text="Timelapse Settings", width=400)
        tl.pack(anchor='center', padx=10, pady=5)
        tl.pack_propagate(False)
        # Explanatory text
        tk.Label(tl, text="e.g. 1h 30m 10s", fg="gray").grid(row=0, column=0, columnspan=2, pady=(5,2))
        tk.Label(tl, text="Duration:").grid(row=1, column=0, sticky="e", padx=5, pady=2)
        self.duration_entry = tk.Entry(tl)
        self.duration_entry.grid(row=1, column=1, padx=5, pady=2)
        self.duration_entry.insert(0, "30m")
        tk.Label(tl, text="Frequency:").grid(row=2, column=0, sticky="e", padx=5, pady=2)
        self.freq_entry = tk.Entry(tl)
        self.freq_entry.grid(row=2, column=1, padx=5, pady=2)
        self.freq_entry.insert(0, "5s")

        # Start/Stop timelapse button
        self.start_btn = tk.Button(root, text="Confirm settings and start timelapse", command=self.start_timelapse)
        self.start_btn.pack(pady=10)

    def build_motor_controls(self):
        # Clear old buttons and update titles
        for w in self.coarse_frame.winfo_children(): w.destroy()
        for w in self.fine_frame.winfo_children(): w.destroy()
        self.coarse_frame.config(text=f"Coarse Motor Control (inc: {self.motor_increment_coarse})")
        self.fine_frame.config(text=f"Fine Motor Control (inc: {self.motor_increment_fine})")
        # Axes in two-row layout
        axes = [('X+', (1,0,0)), ('Y+', (0,1,0)), ('Z+', (0,0,1)),
                ('X-', (-1,0,0)), ('Y-', (0,-1,0)), ('Z-', (0,0,-1))]
        self.coarse_buttons, self.fine_buttons = [], []
        for idx, (txt, d) in enumerate(axes):
            rel_c = (d[0]*self.motor_increment_coarse, d[1]*self.motor_increment_coarse, d[2]*self.motor_increment_coarse)
            btn_c = tk.Button(self.coarse_frame, text=txt, command=lambda r=rel_c: self.move(r))
            btn_c.grid(row=idx//3, column=idx%3, padx=5, pady=5)
            self.coarse_buttons.append(btn_c)
            rel_f = (d[0]*self.motor_increment_fine, d[1]*self.motor_increment_fine, d[2]*self.motor_increment_fine)
            btn_f = tk.Button(self.fine_frame, text=txt, command=lambda r=rel_f: self.move(r))
            btn_f.grid(row=idx//3, column=idx%3, padx=5, pady=5)
            self.fine_buttons.append(btn_f)

    def change_increments(self):
        new_coarse = simpledialog.askinteger("Coarse increment", "Enter coarse increment:", initialvalue=self.motor_increment_coarse, minvalue=1)
        if new_coarse is None: return
        new_fine = simpledialog.askinteger("Fine increment", "Enter fine increment:", initialvalue=self.motor_increment_fine, minvalue=1)
        if new_fine is None: return
        self.motor_increment_coarse, self.motor_increment_fine = new_coarse, new_fine
        self.build_motor_controls()

    def move(self, rel):
        with self.sb as board:
            board.illumination.cc_led = self.led_brightness
            board.move_rel(list(rel))
            board.illumination.cc_led = 0.0

    def update_led(self, val):
        self.led_brightness = float(val)
        if self.previewing:
            with self.sb as board:
                board.illumination.cc_led = self.led_brightness

    def toggle_preview(self):
        if not self.previewing:
            with self.sb as board:
                board.illumination.cc_led = self.led_brightness
            self.cam.start_preview()
            self.preview_btn.config(text="Stop Preview")
            self.previewing = True
            self.image_label.config(text="Preview running...", image='')
        else:
            self.cam.stop_preview()
            with self.sb as board:
                board.illumination.cc_led = 0.0
            self.preview_btn.config(text="Start Preview")
            self.previewing = False
            self.image_label.config(image='', text='')

    def start_timelapse(self):
        if not self.timelapse_running:
            dur = parse_time_value(self.duration_entry.get())
            freq = parse_time_value(self.freq_entry.get())
            if not dur or dur <= 0 or not freq or freq <= 0:
                messagebox.showerror("Error", "Invalid duration or frequency")
                return
            for btn in self.coarse_buttons + self.fine_buttons:
                btn.config(state='disabled')
            self.change_inc_btn.config(state='disabled')
            self.led_scale.config(state='disabled')
            self.preview_btn.config(state='disabled')
            now = datetime.datetime.now()
            self.folder = now.strftime("%Y-%m-%d_%H-%M-%S")
            os.makedirs(self.folder, exist_ok=True)
            self.end_time = now + datetime.timedelta(seconds=dur)
            self.start_btn.config(text="Stop and end timelapse early", command=self.stop_timelapse)
            self.timelapse_running = True
            self.capture_loop(freq)

    def stop_timelapse(self):
        if self.after_id:
            self.root.after_cancel(self.after_id)
        messagebox.showinfo("Stopped", "Timelapse stopped early")
        self._reset_after_timelapse()

    def finish_timelapse(self):
        messagebox.showinfo("Done", "Timelapse complete")
        self._reset_after_timelapse()

    def _reset_after_timelapse(self):
        for btn in self.coarse_buttons + self.fine_buttons:
            btn.config(state='normal')
        self.change_inc_btn.config(state='normal')
        self.led_scale.config(state='normal')
        self.preview_btn.config(state='normal')
        self.start_btn.config(text="Confirm settings and start timelapse", command=self.start_timelapse)
        self.timelapse_running = False

    def capture_loop(self, freq):
        if datetime.datetime.now() >= self.end_time:
            self.finish_timelapse()
            return
        ts = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        fname = os.path.join(self.folder, f"{ts}.jpg")
        with self.sb as board:
            board.illumination.cc_led = self.led_brightness
            self.cam.take_photo(fname)
            board.illumination.cc_led = 0.0
        print(f"Captured: {fname}")
        if Image and ImageTk:
            try:
                img = Image.open(fname)
                img.thumbnail((400, 400))
                self.photo = ImageTk.PhotoImage(img)
                self.image_label.config(image=self.photo, text='')
            except Exception:
                pass
        self.after_id = self.root.after(int(freq * 1000), lambda: self.capture_loop(freq))

if __name__ == '__main__':
    root = tk.Tk()
    app = App(root)
    root.mainloop()
