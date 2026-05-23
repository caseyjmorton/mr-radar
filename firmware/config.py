# Pin map + display factory for the GC9A01 round TFT.
# Pins mirror firmware/WIRING.md - keep the two in sync.

from machine import Pin, SPI
import gc9a01py

# GC9A01 module header -> ESP32-C3 GPIO (labels are I2C-style but it's SPI)
PIN_SCL = 4   # SPI clock
PIN_SDA = 5   # SPI data (MOSI)
PIN_DC = 6    # data/command select
PIN_CS = 7    # chip select
PIN_RST = 8   # reset (module has an onboard 10k pullup -> safe on strapping pin)

# Conservative bring-up clock. GC9A01 can run 40-80 MHz once wiring is proven.
SPI_BAUD = 20_000_000


def make_display(rotation=0):
    """Build and initialize the GC9A01 display driver."""
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
