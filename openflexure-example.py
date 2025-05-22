import tkinter as tk
from tkinter import messagebox, simpledialog
import datetime
import os
import re
from PIL import Image, ImageTk

# Defaults
DEFAULT_FINE_INCREMENT = 50
DEFAULT_COARSE_INCREMENT = 500
DEFAULT_LED_BRIGHTNESS = 0.33
DEFAULT_EXPOSURE = 10000  # in microseconds (10 ms)
DEFAULT_WHITEBALANCE = 'daylight'
AWB_OPTIONS = ['auto', 'tungsten', 'fluorescent', 'indoor', 'daylight', 'cloudy', 'custom']


def get_sangaboard():
    """Return a real or mock Sangaboard instance."""
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


def get_camera():
    """Return a Picamera2-based camera instance or a mock."""
    try:
        from picamera2 import Picamera2, Preview
        from libcamera import controls

        picam2 = Picamera2()
        # Use string control keys to avoid ControlId issues
        picam2.set_controls({
            "ExposureTime": DEFAULT_EXPOSURE,
            "AwbEnable": True,
            "AwbMode": getattr(controls.AwbModeEnum, DEFAULT_WHITEBALANCE.capitalize())
        })
        preview_cfg = picam2.create_preview_configuration(
            main={'size': picam2.sensor_resolution}
        )
        still_cfg = picam2.create_still_configuration(
            main={'size': picam2.sensor_resolution}
        )
        picam2.configure(preview_cfg)
        picam2.start()

        class Camera:
            """Wrapper for Picamera2 preview, capture, AWB, and exposure control."""
            def __init__(self, picam, prev_cfg, still_cfg, controls_mod):
                self._picam = picam
                self._prev_cfg = prev_cfg
                self._still_cfg = still_cfg
                self._controls = controls_mod

            def start_preview(self):
                self._picam.start_preview(Preview.QTGL)

            def stop_preview(self):
                self._picam.stop_preview()

            def take_photo(self, filename):
                self._picam.switch_mode(self._still_cfg)
                self._picam.capture_file(filename)
                self._picam.switch_mode(self._prev_cfg)

            def set_awb(self, mode_str):
                awb_val = getattr(self._controls.AwbModeEnum, mode_str.capitalize())
                # Use string key
                self._picam.set_controls({'AwbMode': awb_val})

            def set_exposure(self, exp_us):
                # Use string key
                self._picam.set_controls({'ExposureTime': int(exp_us)})

        return Camera(picam2, preview_cfg, still_cfg, controls)
    except ImportError:
        class Camera:
            def start_preview(self):
                print("[Mock] Camera preview started")

            def stop_preview(self):
                print("[Mock] Camera preview stopped")

            def take_photo(self, filename):
                print(f"[Mock] Photo taken and saved to {filename}")

            def set_awb(self, mode_str):
                print(f"[Mock] AWB set to {mode_str}")

            def set_exposure(self, exp_us):
                print(f"[Mock] Exposure set to {exp_us}")

        return Camera()
    except ImportError:
        class Camera:
            def start_preview(self):
                print("[Mock] Camera preview started")

            def stop_preview(self):
                print("[Mock] Camera preview stopped")

            def take_photo(self, filename):
                print(f"[Mock] Photo taken and saved to {filename}")

            def set_awb(self, mode_str):
                print(f"[Mock] AWB set to {mode_str}")

            def set_exposure(self, exp_us):
                print(f"[Mock] Exposure set to {exp_us}")

        return Camera()
    except ImportError:
        class Camera:
            def start_preview(self):
                print("[Mock] Camera preview started")

            def stop_preview(self):
                print("[Mock] Camera preview stopped")

            def take_photo(self, filename):
                print(f"[Mock] Photo taken and saved to {filename}")

            def set_awb(self, mode_str):
                print(f"[Mock] AWB set to {mode_str}")

            def set_exposure(self, exp_us):
                print(f"[Mock] Exposure set to {exp_us}")

        return Camera()


def format_exposure(us):
    """Convert microseconds to milliseconds string."""
    ms = us // 1000
    return f"{ms} ms"


def parse_time_value(time_str):
    """Parse strings like '1d 2h 30m 5s' into total seconds."""
    pattern = (
        r"^\s*(?:(?P<days>\d+)\s*d)?\s*"
        r"(?:(?P<hours>\d+)\s*h)?\s*"
        r"(?:(?P<minutes>\d+)\s*m)?\s*"
        r"(?:(?P<seconds>\d+)\s*s)?\s*$"
    )
    m = re.match(pattern, time_str.strip(), re.IGNORECASE)
    if not m:
        return None
    days = int(m.group('days') or 0)
    hours = int(m.group('hours') or 0)
    minutes = int(m.group('minutes') or 0)
    seconds = int(m.group('seconds') or 0)
    return days*86400 + hours*3600 + minutes*60 + seconds


class App:
    """Main application GUI for timelapse control."""
    def __init__(self, root):
        self.root = root
        root.title("OpenFlexure Timelapse Controller")

        # Hardware setup
        self.sb = get_sangaboard()
        try:
            self.sb.open()
        except Exception:
            pass
        self.cam = get_camera()
        self.sb.illumination.cc_led = 0.0

        # Initial state
        self.motor_increment_fine = DEFAULT_FINE_INCREMENT
        self.motor_increment_coarse = DEFAULT_COARSE_INCREMENT
        self.led_brightness = DEFAULT_LED_BRIGHTNESS
        self.awb_mode = DEFAULT_WHITEBALANCE
        self.exposure_time = DEFAULT_EXPOSURE
        self.previewing = False
        self.timelapse_running = False
        self.after_id = None
        self.folder = None

        # Layout containers
        self.motor_container = tk.Frame(self.root)
        self.motor_container.pack(padx=10, pady=5)

        self.light_container = tk.Frame(self.root)
        for i in range(3):
            self.light_container.grid_columnconfigure(i, weight=1)
        self.light_container.grid_rowconfigure(0, weight=1)
        self.light_container.pack(padx=10, pady=5)

        # Build UI
        self.build_motor_controls()
        self.build_increment_button()
        self.build_awb_control()
        self.build_exposure_control()
        self.build_led_control()
        self.build_preview_button()
        self.build_image_display()
        self.build_timelapse_controls()

        self.root.protocol('WM_DELETE_WINDOW', self.cleanup)

    def build_motor_controls(self):
        """Create coarse and fine motor control frames side by side."""
        for attr in ('coarse_frame', 'fine_frame'):
            if hasattr(self, attr):
                getattr(self, attr).destroy()

        self.coarse_frame = tk.LabelFrame(
            self.motor_container,
            text=f"Coarse Motor Control (inc: {self.motor_increment_coarse})"
        )
        self.fine_frame = tk.LabelFrame(
            self.motor_container,
            text=f"Fine Motor Control (inc: {self.motor_increment_fine})"
        )

        self.coarse_frame.grid(row=0, column=0, padx=5, pady=5, sticky='nsew')
        self.fine_frame.grid(row=0, column=1, padx=5, pady=5, sticky='nsew')

        axes = [
            ('X+', (1, 0, 0)), ('Y+', (0, 1, 0)), ('Z+', (0, 0, 1)),
            ('X-', (-1, 0, 0)), ('Y-', (0, -1, 0)), ('Z-', (0, 0, -1))
        ]
        for idx, (lbl, d) in enumerate(axes):
            rel_c = [d[i] * self.motor_increment_coarse for i in range(3)]
            rel_f = [d[i] * self.motor_increment_fine for i in range(3)]

            btn_c = tk.Button(
                self.coarse_frame,
                text=lbl,
                command=lambda r=rel_c: self.move(r)
            )
            btn_c.grid(row=idx//3, column=idx%3, padx=5, pady=5)

            btn_f = tk.Button(
                self.fine_frame,
                text=lbl,
                command=lambda r=rel_f: self.move(r)
            )
            btn_f.grid(row=idx//3, column=idx%3, padx=5, pady=5)

    def build_increment_button(self):
        """Button spanning motor control columns to change increments."""
        if hasattr(self, 'change_inc_btn'):
            self.change_inc_btn.destroy()
        self.change_inc_btn = tk.Button(
            self.motor_container,
            text="Change motor increments",
            command=self.change_increments
        )
        self.change_inc_btn.grid(row=1, column=0, columnspan=2, pady=5)

    def change_increments(self):
        """Prompt dialogs for new motor increments."""
        new_c = simpledialog.askinteger(
            "Coarse increment",
            "Enter coarse increment:",
            initialvalue=self.motor_increment_coarse,
            minvalue=1
        )
        if new_c is not None:
            self.motor_increment_coarse = new_c

        new_f = simpledialog.askinteger(
            "Fine increment",
            "Enter fine increment:",
            initialvalue=self.motor_increment_fine,
            minvalue=1
        )
        if new_f is not None:
            self.motor_increment_fine = new_f

        self.build_motor_controls()
        self.build_increment_button()

    def build_awb_control(self):
        """Create dropdown for white balance selection."""
        if hasattr(self, 'awb_frame'):
            self.awb_frame.destroy()
        self.awb_frame = tk.LabelFrame(self.light_container, text="White Balance")
        self.awb_frame.grid(row=0, column=0, padx=5, pady=5, sticky='nsew')

        self.awb_var = tk.StringVar(value=self.awb_mode)
        awb_menu = tk.OptionMenu(
            self.awb_frame,
            self.awb_var,
            *AWB_OPTIONS,
            command=self.change_awb
        )
        awb_menu.pack(fill='both', expand=True, padx=10, pady=5)

    def build_exposure_control(self):
        """Create slider for exposure time in milliseconds."""
        if hasattr(self, 'exp_frame'):
            self.exp_frame.destroy()
        self.exp_frame = tk.LabelFrame(self.light_container, text="Exposure Time (ms)")
        self.exp_frame.grid(row=0, column=1, padx=5, pady=5, sticky='nsew')

        # Slider: 1 ms to 100 ms
        self.exp_scale = tk.Scale(
            self.exp_frame,
            from_=1,
            to=100,
            resolution=1,
            orient='horizontal',
            command=self.change_exposure
        )
        # initialize slider position
        self.exp_scale.set(self.exposure_time // 1000)
        self.exp_scale.pack(fill='both', expand=True, padx=10, pady=5)

    def build_led_control(self):
        """Create slider for LED brightness."""
        if hasattr(self, 'led_frame'):
            self.led_frame.destroy()
        self.led_frame = tk.LabelFrame(self.light_container, text="LED Brightness")

        self.led_frame.grid(row=0, column=2, padx=5, pady=5, sticky='nsew')

        self.led_scale = tk.Scale(
            self.led_frame,
            from_=0.0,
            to=1.0,
            resolution=0.01,
            orient='horizontal',
            command=self.update_led
        )
        self.led_scale.set(self.led_brightness)
        self.led_scale.pack(fill='both', expand=True, padx=10, pady=5)

    def build_preview_button(self):
        """Create button to toggle camera preview."""
        if hasattr(self, 'preview_btn'):
            self.preview_btn.destroy()
        self.preview_btn = tk.Button(
            self.root,
            text="Show camera preview",
            command=self.toggle_external_preview
        )
        self.preview_btn.pack(pady=5)

    def build_image_display(self):
        """Create frame to display last captured image."""
        if hasattr(self, 'image_frame'):
            self.image_frame.destroy()
        self.image_frame = tk.LabelFrame(
            self.root,
            text="Last captured image",
            width=400,
            height=300
        )
        self.image_frame.pack(padx=10, pady=5)
        self.image_frame.pack_propagate(False)
        self.image_label = tk.Label(self.image_frame, text="No images yet")
        self.image_label.pack(expand=True)

    def build_timelapse_controls(self):
        """Create timelapse settings fields and start button."""
        if hasattr(self, 'tl_frame'):
            self.tl_frame.destroy()
        self.tl_frame = tk.LabelFrame(self.root, text="Timelapse settings", width=400)
        self.tl_frame.pack(padx=10, pady=5)

        tk.Label(self.tl_frame, text="e.g. 1h 30m 10s", fg='gray').grid(row=0, column=0, columnspan=2)

        tk.Label(self.tl_frame, text="Duration:").grid(row=1, column=0, sticky='e', padx=5)
        self.duration_entry = tk.Entry(self.tl_frame)
        self.duration_entry.grid(row=1, column=1, padx=5)
        self.duration_entry.insert(0, '30m')

        tk.Label(self.tl_frame, text="Frequency:").grid(row=2, column=0, sticky='e', padx=5)
        self.freq_entry = tk.Entry(self.tl_frame)
        self.freq_entry.grid(row=2, column=1, padx=5)
        self.freq_entry.insert(0, '5s')

        if hasattr(self, 'start_btn'):
            self.start_btn.destroy()
        self.start_btn = tk.Button(
            self.root,
            text="Confirm settings and start timelapse",
            command=self.start_timelapse
        )
        self.start_btn.pack(pady=10)

    def change_awb(self, selection):
        """Apply white balance change in real time."""
        self.awb_mode = selection
        try:
            self.cam.set_awb(selection)
        except Exception:
            pass

    def change_exposure(self, val):
        """Apply exposure change in real time (ms)."""
        # val is in milliseconds
        self.exposure_time = int(val) * 1000
        try:
            self.cam.set_exposure(self.exposure_time)
        except Exception:
            pass

    def update_led(self, val):
        """Adjust LED brightness immediately if previewing."""
        self.led_brightness = float(val)
        if self.previewing:
            self.sb.illumination.cc_led = self.led_brightness

    def toggle_external_preview(self):
        """Toggle camera preview on/off."""
        if not self.previewing:
            self.sb.illumination.cc_led = self.led_brightness
            try:
                self.cam.start_preview()
            except Exception:
                pass
            self.previewing = True
            self.preview_btn.config(text="Stop preview")
        else:
            try:
                self.cam.stop_preview()
            except Exception:
                pass
            self.sb.illumination.cc_led = 0.0
            self.previewing = False
            self.preview_btn.config(text="Show camera preview")

    def move(self, rel):
        """Move stage by given relative vector."""
        self.sb.move_rel(list(rel))

    def start_timelapse(self):
        """Begin timelapse: disable controls and schedule captures."""
        if self.previewing:
            try:
                self.cam.stop_preview()
            except Exception:
                pass
            self.sb.illumination.cc_led = 0.0
            self.previewing = False
            self.preview_btn.config(text="Show camera preview")

        duration = parse_time_value(self.duration_entry.get())
        frequency = parse_time_value(self.freq_entry.get())
        if not duration or duration <= 0 or not frequency or frequency <= 0:
            messagebox.showerror("Error", "Invalid duration or frequency")
            return

        for btn in self.coarse_frame.winfo_children():
            btn.config(state='disabled')
        for btn in self.fine_frame.winfo_children():
            btn.config(state='disabled')
        self.change_inc_btn.config(state='disabled')
        self.exp_scale.config(state='disabled')
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
        """Stop timelapse early and reset UI."""
        if self.after_id:
            self.root.after_cancel(self.after_id)
        messagebox.showinfo("Stopped", "Timelapse stopped early")
        self.reset_controls()

    def finish_timelapse(self):
        """Handle normal completion of timelapse."""
        messagebox.showinfo("Done", "Timelapse complete")
        self.reset_controls()

    def reset_controls(self):
        """Re-enable UI after timelapse stops."""
        for btn in self.coarse_frame.winfo_children():
            btn.config(state='normal')
        for btn in self.fine_frame.winfo_children():
            btn.config(state='normal')
        self.change_inc_btn.config(state='normal')
        self.exp_scale.config(state='normal')
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
        """Capture images at each interval until end_time."""
        if datetime.datetime.now() >= self.end_time:
            self.finish_timelapse()
            return

        ts = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = os.path.join(self.folder, f"{ts}.jpg")

        self.sb.illumination.cc_led = self.led_brightness
        self.cam.take_photo(filename)
        self.sb.illumination.cc_led = 0.0

        print(f"Captured: {filename}")
        try:
            img = Image.open(filename)
            img.thumbnail((380, 280))
            self.photo = ImageTk.PhotoImage(img)
            self.image_label.config(image=self.photo, text='')
        except Exception:
            pass

        self.after_id = self.root.after(int(freq * 1000), lambda: self.capture_loop(freq))

    def cleanup(self):
        """Cleanup hardware and exit."""
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
