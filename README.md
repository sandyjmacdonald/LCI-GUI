## Openflexure microscope example

This short example script demonstrates using the Openflexure microscope with the pysangaboard Python library, to configure and run a timelapse capture.

## Setting up the Raspberry Pi and software dependencies

I would recommend starting with a fresh installation of the Raspberry Pi operating system (with desktop, 64 bit).

You'll need to connect to wi-fi for the following steps.

Once booted into the OS, you will need to enable the serial interface on the Raspberry Pi, either through the menu, or in the terminal by typing `sudo raspi-config`. You should _not_ enable the serial terminal, but _do_ enable the serial interface. The serial interface allows the Raspberry Pi to "talk" to the Arduino chip on-board the Sangaboard and in turn to control the motors, LED, etc.

You should install the picamzero Python library by typing `sudo apt update && sudo apt install python3-picamzero` in the terminal. This Python library allows you to control the Raspberry Pi camera with Python code.

The pysangaboard Python library allows control of the motors and LED, although the LED functionality is currently only in a separate branch, so that branch must be installed rather than the main branch. Type the following in the terminal to install the library: `sudo pip3 install --break-system-packages git+https://gitlab.com/filipayazi/pysangaboard.git@sangaboardv5`

Lastly, you should clone this GitHub repo by typing this in the terminal: `git clone https://github.com/sandyjmacdonald/openflexure-example`

## Running the example script

To run the example script, make sure that you are in the directory containing the script (`cd openflexure-example`) and then type `python3 openflexure-example.py` to run the script.

When the script runs, it should illuminate the LED and pop up the camera preview to show the microscope image. To position the microscope, you can use the A and D keys to control the X-axis, the W and S keys to control the Y-axis, and the Z and X keys to control the Z axis. Once you are happy with the positioning, you can press `C` to confirm, and then set up the time lapse settings.

You can specify the length of the timelapse by entering a time such as `1d 4h 30s` for 1 day, 4 hours, and 30 seconds, or `6h` for 6 hours. You should press `enter` to proceed.

You can then specify the frequency at which images should be captured, again with the same notation, e.g. `1m` to capture once image every minute, or `10s` to capture one image every 10 seconds. Before the image is captured, the LED will illuminate and then turn off again when the image has be captured. Note that the image will take a couple of seconds to capture, so you may get slightly fewer images captured than you would expect, e.g. a 1 minute timelapse with images captured every 10 seconds may not have exactly 6 images captured.

Images will be saved to a directory with a date and time stamp corresponding to when the timelapse started, and each image captured will have a date and time stamp of exactly when the individual image was captured.