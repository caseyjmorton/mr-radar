# Pin map + display factory for the GC9A01 round TFT.
# Pins mirror firmware/doc/WIRING.md - keep the two in sync.
#
# One supported board: the Seeed XIAO ESP32S3 (8 MB flash, 8 MB octal PSRAM).
# The ESP32-C3 and the 4 MB / 2 MB-PSRAM ESP32-S3-Zero were dropped - neither
# has the memory headroom to hold the 115,200-byte framebuffer alongside WiFi
# without fragmentation stalls, and the sweep animation misses its frame budget
# on both.

from machine import Pin, SPI
import gc9a01py

SPI_BAUD = 40_000_000

# Raw GPIO numbers - NOT the XIAO's silkscreen D-labels. On a XIAO ESP32S3
# these land on D3/D4/D5/D8/D9 respectively; wiring to the same-numbered D pads
# puts every line on the wrong GPIO, and the display is write-only so nothing
# reports the mistake back.
PIN_SCL = 4   # SPI clock            (XIAO D3)
PIN_SDA = 5   # SPI data (MOSI)      (XIAO D4)
PIN_DC = 6    # data/command select  (XIAO D5)
PIN_CS = 7    # chip select          (XIAO D8)
PIN_RST = 8   # reset                (XIAO D9) - the module's onboard 10k
              # pullup is harmless; GPIO8 is a plain GPIO on the S3, not a
              # strapping pin as it is on the C3.


def make_display(rotation=0):
    """Build and initialize the GC9A01 display driver."""
    # SPI(1), not SPI(2): the display is write-only so no MISO is wired, and
    # machine.SPI falls back to a per-chip default MISO pin when the kwarg is
    # omitted. SPI(1)'s default (GPIO13) is free; SPI(2)'s (GPIO37) collides
    # with the octal PSRAM.
    spi = SPI(
        1,
        baudrate=SPI_BAUD,
        polarity=0,
        phase=0,
        sck=Pin(PIN_SCL),
        mosi=Pin(PIN_SDA),
    )
    return gc9a01py.GC9A01(
        spi,
        dc=Pin(PIN_DC, Pin.OUT),
        cs=Pin(PIN_CS, Pin.OUT),
        reset=Pin(PIN_RST, Pin.OUT),
        backlight=None,  # backlight is hardwired on; no control pin exists
        rotation=rotation,
    )
