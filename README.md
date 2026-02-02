## LCI GUI

This code creates a GUI for the Openflexure microscope using the pysangaboard Python library, allowing configuring and running a timelapse capture.

## Setting up the Raspberry Pi and software dependencies

We would recommend starting with a fresh installation of the Raspberry Pi operating system (with desktop, 64 bit).

You'll need to connect to wi-fi for the following steps.

Once booted into the OS, you will need to enable the serial interface on the Raspberry Pi, either through the menu, or in the terminal by typing `sudo raspi-config`. You should _not_ enable the serial terminal, but _do_ enable the serial interface. The serial interface allows the Raspberry Pi to "talk" to the Arduino chip on-board the Sangaboard and in turn to control the motors, LED, etc.

You should install the picamzero Python library by typing `sudo apt update && sudo apt install python3-picamzero` in the terminal. This Python library allows you to control the Raspberry Pi camera with Python code.

The pysangaboard Python library allows control of the motors and LED, although the LED functionality is currently only in a separate branch, so that branch must be installed rather than the main branch. Type the following in the terminal to install the library: `sudo pip3 install --break-system-packages git+https://gitlab.com/filipayazi/pysangaboard.git@sangaboardv5`

Lastly, you should clone this GitHub repo by typing this in the terminal: `git clone https://github.com/uoy-research/LCI-GUI`

## Running the GUI

To run the GUI, make sure that you are in the directory containing the script (`cd LCI-GUI`) and then type `python3 lci-gui.py` to run the script.


