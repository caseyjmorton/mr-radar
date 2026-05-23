# Display bring-up test pattern. Proves GC9A01 wiring before any network code.
#
# Usage: flash MicroPython, copy gc9a01py.py + config.py + this file to the
# board, then at the REPL run:
#     import test_pattern
#
# Expected sequence on screen:
#   1. Full-screen RED, GREEN, BLUE, WHITE (1s each) - init + SPI + color order.
#   2. Four quadrants R/G/B/Y (2s)                   - addressing + orientation.
#   3. White crosshair through center (2s)           - panel is centered.
#   4. Top->bottom blue->red gradient                - the exact blit path /frame uses.
#
# If the screen stays black: re-check wiring per firmware/WIRING.md. The usual
# culprits are a weak common ground or swapped SCL/SDA (they're SPI, not I2C).

import time
import gc9a01py as gc
import config


def run():
    tft = config.make_display()

    # 1. Solid color cycle.
    for name, color in (
        ("RED", gc.RED),
        ("GREEN", gc.GREEN),
        ("BLUE", gc.BLUE),
        ("WHITE", gc.WHITE),
    ):
        print("fill", name)
        tft.fill(color)
        time.sleep(1)

    # 2. Quadrants.
    print("quadrants")
    tft.fill(gc.BLACK)
    h = 120
    tft.fill_rect(0, 0, h, h, gc.RED)       # top-left
    tft.fill_rect(h, 0, h, h, gc.GREEN)     # top-right
    tft.fill_rect(0, h, h, h, gc.BLUE)      # bottom-left
    tft.fill_rect(h, h, h, h, gc.YELLOW)    # bottom-right
    time.sleep(2)

    # 3. Center crosshair.
    print("crosshair")
    tft.fill(gc.BLACK)
    tft.hline(0, 120, 240, gc.WHITE)
    tft.vline(120, 0, 240, gc.WHITE)
    time.sleep(2)

    # 4. Full-frame RGB565 blit, line by line (matches the renderer's
    #    big-endian RGB565 output; reuses one 240px row buffer to stay light).
    print("gradient blit")
    row = bytearray(240 * 2)
    for y in range(240):
        c = gc.color565(y, 0, 255 - y)
        hi = c >> 8
        lo = c & 0xFF
        for x in range(240):
            row[x * 2] = hi
            row[x * 2 + 1] = lo
        tft.blit_buffer(row, 0, y, 240, 1)

    print("test pattern complete")


run()
