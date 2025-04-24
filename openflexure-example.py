import tkinter as tk
from tkinter import messagebox, simpledialog
import datetime
import os
import re
from PIL import Image, ImageTk

# Mock or real Sangaboard
def get_sangaboard():
    try:
        from sangaboard import Sangaboard
        return Sangaboard()
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

        return Sangaboard()

# Mock or real Camera
def get_camera():
    try:
        from picamzero import Camera
        return Camera()
    except ImportError:
        class Camera:
            def start_preview(self):
                print("[Mock] Camera preview started")

            def stop_preview(self):
                print("[Mock] Camera preview stopped")

            def take_photo(self, filename):
                print(f"[Mock] Photo taken and saved to {filename}")
                img = Image.new('RGB', (640, 480), 'gray')
                img.save(filename)

        return Camera()

# Defaults
DEFAULT_FINE_INCREMENT = 50
DEFAULT_COARSE_INCREMENT = 500
DEFAULT_LED_BRIGHTNESS = 0.33

# Parse time strings
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

        # Hardware connections
        self.sb = get_sangaboard()
        try:
            self.sb.open()
        except Exception:
            pass

        self.cam = get_camera()
        self.sb.illumination.cc_led = 0.0

        # State variables
        self.motor_increment_fine = DEFAULT_FINE_INCREMENT
        self.motor_increment_coarse = DEFAULT_COARSE_INCREMENT
        self.led_brightness = DEFAULT_LED_BRIGHTNESS
        self.timelapse_running = False
        self.previewing = False
        self.after_id = None
        self.folder = None

        # Build GUI sections
        self.build_motor_controls()
        self.build_led_control()
        self.build_preview_button()
        self.build_image_display()
        self.build_timelapse_controls()

        self.root.protocol('WM_DELETE_WINDOW', self.cleanup)

    def build_motor_controls(self):
        """Create coarse and fine motor controls."""
        self.coarse_frame = tk.LabelFrame(self.root, text=f"Coarse Motor Control (inc: {self.motor_increment_coarse})")
        self.coarse_frame.pack(padx=10, pady=5)
        self.fine_frame = tk.LabelFrame(self.root, text=f"Fine Motor Control (inc: {self.motor_increment_fine})")
        self.fine_frame.pack(padx=10, pady=5)

        axes = [
            ('X+', (1,0,0)), ('Y+', (0,1,0)), ('Z+', (0,0,1)),
            ('X-', (-1,0,0)), ('Y-', (0,-1,0)), ('Z-', (0,0,-1))
        ]
        for idx, (txt, d) in enumerate(axes):
            rel_c = (d[0]*self.motor_increment_coarse, d[1]*self.motor_increment_coarse, d[2]*self.motor_increment_coarse)
            btn_c = tk.Button(self.coarse_frame, text=txt, command=lambda r=rel_c: self.move(r))
            btn_c.grid(row=idx//3, column=idx%3, padx=5, pady=5)

            rel_f = (d[0]*self.motor_increment_fine, d[1]*self.motor_increment_fine, d[2]*self.motor_increment_fine)
            btn_f = tk.Button(self.fine_frame, text=txt, command=lambda r=rel_f: self.move(r))
            btn_f.grid(row=idx//3, column=idx%3, padx=5, pady=5)

    def build_led_control(self):
        """Create LED brightness slider."""
        led_frame = tk.LabelFrame(self.root, text="LED Brightness")
        led_frame.pack(padx=10, pady=5)
        self.led_scale = tk.Scale(
            led_frame,
            from_=0.0,
            to=1.0,
            resolution=0.01,
            orient='horizontal',
            command=self.update_led
        )
        self.led_scale.set(self.led_brightness)
        self.led_scale.pack(fill='x', padx=10, pady=5)

    def build_preview_button(self):
        """Create button to launch external preview."""
        self.preview_btn = tk.Button(
            self.root,
            text="Show External Preview",
            command=self.toggle_external_preview
        )
        self.preview_btn.pack(pady=5)

    def build_image_display(self):
        """Create frame to display last captured image."""
        frame = tk.LabelFrame(
            self.root,
            text="Last Captured Image",
            width=400,
            height=300
        )
        frame.pack(padx=10, pady=5)
        frame.pack_propagate(False)
        self.image_label = tk.Label(frame, text="No images yet")
        self.image_label.pack(expand=True)

    def build_timelapse_controls(self):
        """Create timelapse duration/frequency inputs and start button."""
        tl = tk.LabelFrame(self.root, text="Timelapse Settings", width=400)
        tl.pack(padx=10, pady=5)
        tk.Label(tl, text="e.g. 1h 30m 10s", fg='gray').grid(row=0, column=0, columnspan=2)
        tk.Label(tl, text="Duration:").grid(row=1, column=0, sticky='e', padx=5)
        self.duration_entry = tk.Entry(tl)
        self.duration_entry.grid(row=1, column=1, padx=5)
        self.duration_entry.insert(0, '30m')
        tk.Label(tl, text="Frequency:").grid(row=2, column=0, sticky='e', padx=5)
        self.freq_entry = tk.Entry(tl)
        self.freq_entry.grid(row=2, column=1, padx=5)
        self.freq_entry.insert(0, '5s')

        self.start_btn = tk.Button(
            self.root,
            text="Confirm settings and start timelapse",
            command=self.start_timelapse
        )
        self.start_btn.pack(pady=10)

    def move(self, rel):
        """Move the stage without toggling LED."""
        self.sb.move_rel(rel)

    def update_led(self, val):
        """Update LED brightness while previewing."""
        self.led_brightness = float(val)
        if self.previewing:
            self.sb.illumination.cc_led = self.led_brightness

    def toggle_external_preview(self):
        """Launch or close external preview and sync LED."""
        if not self.previewing:
            self.sb.illumination.cc_led = self.led_brightness
            try:
                self.cam.start_preview()
            except Exception:
                pass
            self.previewing = True
            self.preview_btn.config(text="Stop Preview")
        else:
            try:
                self.cam.stop_preview()
            except Exception:
                pass
            self.sb.illumination.cc_led = 0.0
            self.previewing = False
            self.preview_btn.config(text="Show External Preview")

    def start_timelapse(self):
        """Stop preview, disable controls, then begin capturing."""
        if self.previewing:
            try:
                self.cam.stop_preview()
            except Exception:
                pass
            self.sb.illumination.cc_led = 0.0
            self.previewing = False
            self.preview_btn.config(text="Show External Preview")

        duration = parse_time_value(self.duration_entry.get())
        frequency = parse_time_value(self.freq_entry.get())
        if duration is None or duration <= 0 or frequency is None or frequency <= 0:
            messagebox.showerror("Error", "Invalid duration or frequency")
            return

        # Disable controls
        for btn in self.coarse_frame.winfo_children():
            btn.config(state='disabled')
        for btn in self.fine_frame.winfo_children():
            btn.config(state='disabled')
        self.led_scale.config(state='disabled')
        self.preview_btn.config(state='disabled')
        self.duration_entry.config(state='disabled')
        self.freq_entry.config(state='disabled')
        self.start_btn.config(state='disabled')

        now = datetime.datetime.now()
        self.folder = now.strftime("%Y-%m-%d_%H-%M-%S")
        os.makedirs(self.folder, exist_ok=True)
        self.end_time = now + datetime.timedelta(seconds=duration)

        self.start_btn.config(
            text="Stop and end timelapse early",
            command=self.stop_timelapse,
            state='normal'
        )
        self.timelapse_running = True
        self.capture_loop(frequency)

    def stop_timelapse(self):
        """Stop timelapse early and reset controls."""
        if self.after_id:
            self.root.after_cancel(self.after_id)
        messagebox.showinfo("Stopped", "Timelapse stopped early")
        self.reset_controls()

    def finish_timelapse(self):
        """Handle normal completion of timelapse."""
        messagebox.showinfo("Done", "Timelapse complete")
        self.reset_controls()

    def reset_controls(self):
        """Re-enable all controls after timelapse."""
        for btn in self.coarse_frame.winfo_children():
            btn.config(state='normal')
        for btn in self.fine_frame.winfo_children():
            btn.config(state='normal')
        self.led_scale.config(state='normal')
        self.preview_btn.config(state='normal')
        self.duration_entry.config(state='normal')
        self.freq_entry.config(state='normal')
        self.start_btn.config(
            text="Confirm settings and start timelapse",
            command=self.start_timelapse,
            state='normal'
        )
        self.timelapse_running = False

    def capture_loop(self, freq):
        """Capture images until timelapse end_time."""
        if datetime.datetime.now() >= self.end_time:
            self.finish_timelapse()
            return
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = os.path.join(self.folder, f"{timestamp}.jpg")

        self.sb.illumination.cc_led = self.led_brightness
        self.cam.take_photo(filename)
        self.sb.illumination.cc_led = 0.0

        print(f"Captured: {filename}")
        img = Image.open(filename)
        img.thumbnail((380, 280))
        self.photo = ImageTk.PhotoImage(img)
        self.image_label.config(image=self.photo, text='')

        self.after_id = self.root.after(int(freq * 1000), lambda: self.capture_loop(freq))

    def cleanup(self):
        """Cleanup hardware and exit GUI."""
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
