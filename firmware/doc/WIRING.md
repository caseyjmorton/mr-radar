# Wiring: ESP32-S3-Zero / ESP32-C3 → GC9A01 1.28" round TFT

Hardware wiring reference for mr-radar. Source of truth for the firmware pin
map; mirrors the summary in the repo-root `CLAUDE.md`.

> Board note: this project originally targeted an ESP32-C3 super mini, but those
> boards have a notorious antenna/PA defect (a unit here refused WiFi association
> at any usable range). We switched to the Waveshare ESP32-S3-Zero as the
> primary target. `firmware/src/config.py` now also supports the C3 at the
> source level (see the C3 pinout below) for anyone who already has C3
> hardware — but the antenna/PA defect is a hardware problem, not a firmware
> one. **Before flashing a whole batch of C3 super minis, test one board's
> WiFi association at your actual install distance first.** If your C3 isn't
> a "super mini" (e.g. a DevKitM-1 or another vendor's board), the defect may
> not apply.

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

## Connection table — ESP32-C3

`firmware/src/config.py` detects the chip at runtime (`os.uname().machine`)
and switches pin maps automatically, so the same `firmware/src` tree runs on
either board. The C3 map differs from the S3 map because GPIO2/8/9 are
strapping pins on the C3 (they aren't on the S3), and most "super mini"-style
C3 boards also wire an onboard WS2812 LED to GPIO8.

| Pin | Module label | Function | ESP32-C3 GPIO |
| --- | --- | --- | --- |
| 1 | VCC | Power (3.3–5 V, regulated on-board) | 3V3 (or 5V) |
| 2 | GND | Ground | GND |
| 3 | SCL | SPI clock | GPIO4 |
| 4 | SDA | SPI data (MOSI) | GPIO5 |
| 5 | DC | Data/command select | GPIO6 |
| 6 | CS | Chip select (active low) | GPIO7 |
| 7 | RST | Reset (active low) | GPIO10 |

MISO is unused (the display is write-only) but is pinned explicitly to
GPIO1 in code rather than left to a per-chip default — `machine.SPI` falls
back to a hardware default MISO pin when the kwarg is omitted, which is
exactly what caused the SPI(2)/PSRAM collision noted below for the S3. That
default hasn't been verified against real C3 hardware, so pinning it
explicitly avoids relying on it.

**GPIO2, GPIO8, GPIO9 are reserved — do not use them for anything:**
GPIO9 is the classic BOOT-mode strap (pull low at reset to enter download
mode); GPIO2 must read high at boot for normal SPI-flash boot; GPIO8 carries
the onboard addressable LED on most C3 "super mini" boards. This is why RST
moved from GPIO8 (its S3 pin) to GPIO10 on the C3.

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
- On the C3, `config.py` uses `SPI(1)` as well but pins MISO explicitly to
  GPIO1 rather than trusting an unverified default — **this has not been
  hardware-verified yet**; if the display doesn't come up, check this first.
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

## Flashing reminders (ESP32-C3)

- Flash offset is **`0x0`**, same as the S3.
- Erase first: `esptool.py --chip esp32c3 erase_flash`.
- Use the `ESP32_GENERIC_C3` MicroPython build.
- If auto-reset into download mode fails: hold BOOT, tap RST (or replug USB), release BOOT.
- `_thread` (used for the fetch and settings-server background threads) is
  expected to work on the single-core C3 via FreeRTOS time-slicing, same as
  on the S3, but this project hasn't verified it on real C3 hardware yet.

## Physical dimensions (for the deferred enclosure)

- PCB: 38.0 mm dia (round portion) × 45.5 mm tall including the header tab.
- Active display: 32.4 mm dia circle; visible glass ~35.6 mm.
- Thickness: PCB 1.6 mm + TFT 1.5 mm; rear SMD parts max 1.2 mm tall (header pins protrude further).
- Mounting: 2× Ø2.0 mm holes.
