# Pin map + display factory for the GC9A01 round TFT.
# Pins mirror firmware/doc/WIRING.md - keep the two in sync.
#
# Same source ships to both supported boards; the pin map is selected at
# runtime from os.uname().machine so one firmware/src tree serves both.

import os
from machine import Pin, SPI
import gc9a01py

SPI_BAUD = 40_000_000


def _chip():
    machine_str = os.uname().machine
    if 'C3' in machine_str:
        return 'C3'
    return 'S3'


_CHIP = _chip()

if _CHIP == 'C3':
    # ESP32-C3: GPIO2/8/9 are strapping pins, and GPIO8 also drives the
    # onboard WS2812 LED on most "super mini"-style boards - avoid all three.
    PIN_SCL = 4    # SPI clock
    PIN_SDA = 5    # SPI data (MOSI)
    PIN_DC = 6     # data/command select
    PIN_CS = 7     # chip select
    PIN_RST = 10   # reset
    # Display is write-only (no MISO wired), but machine.SPI falls back to a
    # per-chip default MISO pin when the kwarg is omitted (this is what bit
    # the S3 on SPI(2), whose default MISO collided with PSRAM). Pin it
    # explicitly to a free GPIO instead of trusting an unverified C3 default.
    PIN_MISO = 1
else:
    # ESP32-S3-Zero (primary target)
    PIN_SCL = 4   # SPI clock
    PIN_SDA = 5   # SPI data (MOSI)
    PIN_DC = 6    # data/command select
    PIN_CS = 7    # chip select
    PIN_RST = 8   # reset (module's onboard 10k pullup is harmless; GPIO8 is
                  # a plain GPIO on the S3, not a strapping pin)
    PIN_MISO = None


def make_display(rotation=0):
    """Build and initialize the GC9A01 display driver."""
    spi_kwargs = dict(
        baudrate=SPI_BAUD,
        polarity=0,
        phase=0,
        sck=Pin(PIN_SCL),
        mosi=Pin(PIN_SDA),
    )
    if PIN_MISO is not None:
        spi_kwargs['miso'] = Pin(PIN_MISO)
    spi = SPI(1, **spi_kwargs)
    return gc9a01py.GC9A01(
        spi,
        dc=Pin(PIN_DC, Pin.OUT),
        cs=Pin(PIN_CS, Pin.OUT),
        reset=Pin(PIN_RST, Pin.OUT),
        backlight=None,  # backlight is hardwired on; no control pin exists
        rotation=rotation,
    )
