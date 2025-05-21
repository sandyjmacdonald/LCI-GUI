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
DEFAULT_EXPOSURE = 10  # exposure in microseconds or use camera default
DEFAULT_WHITEBALANCE = "daylight"


def get_sangaboard():
    """Return a real or mock Sangaboard instance."""
    try:
        from sangaboard import Sangaboard
        sb = Sangaboard()
        return sb
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
        picam2 = Picamera2()
        # Configure for full sensor preview at reduced fps
        preview_config = picam2.create_preview_configuration(
            main={'size': picam2.sensor_resolution}
        )
        still_config = picam2.create_still_configuration(
            main={'size': picam2.sensor_resolution}
        )
        picam2.configure(preview_config)
        picam2.start()

        class Camera:
            def __init__(self, picam):
                self._picam = picam
            def start_preview(self):
                # software preview uses full sensor scaled to overlay
                self._picam.start_preview(Preview.QTGL)
            def stop_preview(self):
                self._picam.stop_preview()
            def take_photo(self, filename):
                # switch to still config for capture
                self._picam.switch_mode(still_config)
                self._picam.capture_file(filename)
                # return to preview
                self._picam.switch_mode(preview_config)
        return Camera(picam2)
    except ImportError:
        class Camera:
            def start_preview(self):
                print("[Mock] Camera preview started")
            def stop_preview(self):
                print("[Mock] Camera preview stopped")
            def take_photo(self, filename):
                print(f"[Mock] Photo taken and saved to {filename}")
                try:
                    img = Image.new('RGB', (640, 480), 'gray')
                    img.save(filename)
                except Exception:
                    open(filename, 'wb').close()
        return Camera()


def parse_time_value(time_str):
    """
    Parse strings like '1d 2h 30m 5s' into total seconds.
    """
    pattern = r"^\s*(?:(?P<days>\d+)\s*d)?\s*(?:(?P<hours>\d+)\s*h)?\s*(?:(?P<minutes>\d+)\s*m)?\s*(?:(?P<seconds>\d+)\s*s)?\s*$"
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

        # Hardware
        self.sb = get_sangaboard()
        try:
            self.sb.open()
        except Exception:
            pass
        self.cam = get_camera()
        # Note: Picamera2 controls can be set via picam2.set_controls({...}) if needed
        # Ensure LED off
        self.sb.illumination.cc_led = 0.0

        # State
        self.motor_increment_fine = DEFAULT_FINE_INCREMENT
        self.motor_increment_coarse = DEFAULT_COARSE_INCREMENT
        self.led_brightness = DEFAULT_LED_BRIGHTNESS
        self.previewing = False
        self.timelapse_running = False
        self.after_id = None
        self.folder = None

        # Container for motor controls and increment button
        self.motor_container = tk.Frame(self.root)
        self.motor_container.pack(padx=10, pady=5)

        # Build UI
        self.build_motor_controls()
        self.build_increment_button()
        self.build_led_control()
        self.build_preview_button()
        self.build_image_display()
        self.build_timelapse_controls()

        # Cleanup
        self.root.protocol('WM_DELETE_WINDOW', self.cleanup)

    def build_motor_controls(self):
        """Create motor control frames and buttons."""
        for attr in ('coarse_frame', 'fine_frame'):
            if hasattr(self, attr): getattr(self, attr).destroy()
        self.coarse_frame = tk.LabelFrame(
            self.motor_container,
            text=f"Coarse Motor Control (inc: {self.motor_increment_coarse})"
        )
        self.coarse_frame.pack(padx=5, pady=5)
        self.fine_frame = tk.LabelFrame(
            self.motor_container,
            text=f"Fine Motor Control (inc: {self.motor_increment_fine})"
        )
        self.fine_frame.pack(padx=5, pady=5)
        axes = [
            ('X+', (1, 0, 0)), ('Y+', (0, 1, 0)), ('Z+', (0, 0, 1)),
            ('X-', (-1, 0, 0)), ('Y-', (0, -1, 0)), ('Z-', (0, 0, -1))
        ]
        for idx, (label, d) in enumerate(axes):
            rel_c = tuple(d[i] * self.motor_increment_coarse for i in range(3))
            rel_f = tuple(d[i] * self.motor_increment_fine for i in range(3))
            tk.Button(self.coarse_frame, text=label,
                      command=lambda r=rel_c: self.move(r))
            tk.Button(self.coarse_frame, text=label,
                      command=lambda r=rel_c: self.move(r)).grid(row=idx//3, column=idx%3, padx=5, pady=5)
            tk.Button(self.fine_frame, text=label,
                      command=lambda r=rel_f: self.move(r)).grid(row=idx//3, column=idx%3, padx=5, pady=5)

    def build_increment_button(self):
        """Create 'Change increments' button under motor controls."""
        if hasattr(self, 'change_inc_btn'): self.change_inc_btn.destroy()
        self.change_inc_btn = tk.Button(
            self.motor_container, text="Change increments",
            command=self.change_increments
        )
        self.change_inc_btn.pack(pady=5)

    def change_increments(self):
        """Popup dialogs to adjust fine/coarse increments."""
        new_coarse = simpledialog.askinteger(
            "Coarse increment", "Enter coarse increment:",
            initialvalue=self.motor_increment_coarse, minvalue=1
        )
        if new_coarse is not None: self.motor_increment_coarse = new_coarse
        new_fine = simpledialog.askinteger(
            "Fine increment", "Enter fine increment:",
            initialvalue=self.motor_increment_fine, minvalue=1
        )
        if new_fine is not None: self.motor_increment_fine = new_fine
        self.build_motor_controls()
        self.build_increment_button()

    # Remaining UI builders and methods unchanged...

if __name__ == '__main__':
    root = tk.Tk()
    app = App(root)
    root.mainloop()