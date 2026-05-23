# Wiring: ESP32-S3-Zero → GC9A01 1.28" round TFT

Hardware wiring reference for mr-radar. Source of truth for the firmware pin
map; mirrors the summary in the repo-root `CLAUDE.md`.

> Board note: this project originally targeted an ESP32-C3 super mini, but those
> boards have a notorious antenna/PA defect (a unit here refused WiFi association
> at any usable range). We switched to the Waveshare ESP32-S3-Zero, which uses
> the same display GPIOs. Avoid the C3 super mini.

## Display module

- **Part:** 1.28" round IPS TFT, 240×240, driver IC **GC9A01**, board rev "1.28'TFT 240*240 VER1.0".
- **Interface:** 4-wire SPI (write-only — single `SDA` data line, no MISO).
- **Header:** 7-pin, 2.54 mm pitch, 15.24 mm span.
- **Onboard parts that matter:** XC6206P332MR 3.3 V LDO on `VCC`; 10k pullup (R11) on `RST`; backlight LED hardwired on via `LEDA → 2Ω (R6) → 3.3 V`, `LEDK → GND`.

## Connection table

Pins listed in physical header order (pin 1 = `VCC`).

| Pin | Module label | Function | ESP32-S3 GPIO |
| --- | --- | --- | --- |
| 1 | VCC | Power (3.3–5 V, regulated on-board) | 3V3 (or 5V) |
| 2 | GND | Ground | GND |
| 3 | SCL | SPI clock | GPIO4 |
| 4 | SDA | SPI data (MOSI) | GPIO5 |
| 5 | DC | Data/command select | GPIO6 |
| 6 | CS | Chip select (active low) | GPIO7 |
| 7 | RST | Reset (active low) | GPIO8 |

The pin map is configuration, not magic numbers — assign it explicitly in code.

## Gotchas (why the choices above are safe)

- **`SCL`/`SDA` are SPI, not I2C.** The silkscreen uses I2C-style labels, but
  this is 4-wire SPI: `SCL` = clock, `SDA` = MOSI. Data is latched on the rising
  edge of `SCL`.
- **No level shifting needed.** Logic is 3.3 V, matching the ESP32-S3. Wire every
  signal direct. The onboard XC6206 LDO only regulates panel power, so `VCC`
  tolerates 3.3–5 V; 5 V gives the LDO cleaner headroom, but 3V3 works fine.
- **`RST` on GPIO8 is fine on the S3.** Unlike the C3 (where GPIO8 is a strapping
  pin), GPIO8 is a plain GPIO on the ESP32-S3 — no boot constraint. The module's
  onboard 10k pullup on `RST` is simply harmless here.
- **No backlight control.** The backlight LED is hardwired on inside the module
  (`LEDA → 2Ω → 3.3 V`). It is **not** broken out to the header, so PWM dimming
  is impossible without a hardware mod. Don't plan firmware around dimming on
  this part.
- **Reserved S3 pins to avoid:** strapping = GPIO0/3/45/46; native USB-CDC =
  GPIO19/20; UART0 = GPIO43/44; onboard WS2812 RGB LED = GPIO21; PSRAM =
  GPIO33–37 (not broken out). Our pins (4–8) steer clear of all of these.

## SPI bring-up notes

- Use **`SPI(1)`** on the S3-Zero — verified working, and its default `miso=13`
  is a free pin. Avoid `SPI(2)`, whose default `miso=37` collides with the
  module's PSRAM. (The display is write-only, so MISO is never wired; this only
  matters because the bus claims the pin.)
- Mode 0, MSB-first, single data line (MOSI only).
- Start conservative (~20–27 MHz) on jumper wiring; GC9A01 can run faster
  (~40–80 MHz) once the link is proven stable.
- Keep SCK/MOSI leads short — long dupont jumpers garble pixels at high clock.
- A weak/missing common ground is the most common cause of SPI flakiness here,
  not the code.

## Flashing reminders (ESP32-S3)

- Flash offset is **`0x0`**, not `0x1000`.
- Erase first: `esptool.py --chip esp32s3 erase_flash`.
- Use the `ESP32_GENERIC_S3` MicroPython build.
- If auto-reset into download mode fails: hold BOOT, tap RST (or replug USB), release BOOT.

## Physical dimensions (for the deferred enclosure)

- PCB: 38.0 mm dia (round portion) × 45.5 mm tall including the header tab.
- Active display: 32.4 mm dia circle; visible glass ~35.6 mm.
- Thickness: PCB 1.6 mm + TFT 1.5 mm; rear SMD parts max 1.2 mm tall (header pins protrude further).
- Mounting: 2× Ø2.0 mm holes.
