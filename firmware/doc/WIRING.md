# Wiring: XIAO ESP32S3 → GC9A01 1.28" round TFT

Hardware wiring reference for mr-radar. Source of truth for the firmware pin
map; mirrors the summary in the repo-root `CLAUDE.md`.

> Board note: the **Seeed XIAO ESP32S3** (8 MB flash, 8 MB octal PSRAM) is the
> only supported board. This project originally targeted an ESP32-C3 super mini,
> but those boards have a notorious antenna/PA defect (a unit here refused WiFi
> association at any usable range); it then ran on a Waveshare ESP32-S3-Zero
> (4 MB flash, 2 MB PSRAM). Both were dropped for memory headroom — neither can
> hold the 115,200-byte framebuffer alongside WiFi without fragmentation stalls,
> and the sweep animation misses its frame budget on both. The pin map below is
> the same as the S3-Zero's, but only the XIAO's 8 MB flash matches the released
> binary's embedded filesystem.

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

> **XIAO silkscreen trap:** the table above is raw **GPIO numbers**, which are
> *not* the XIAO's `D` labels. On a XIAO ESP32S3 the display lands on `D3`,
> `D4`, `D5`, `D8`, `D9` — wiring to the identically-named `D4`–`D8` pads
> instead puts every line on the wrong GPIO. A carrier PCB laid out against the
> silkscreen rather than the GPIO numbers will look correct on paper and fail
> silently, since the display is write-only and reports nothing back.
>
> | Function | GPIO | XIAO label |
> | --- | --- | --- |
> | SCL | GPIO4 | D3 |
> | SDA | GPIO5 | D4 |
> | DC | GPIO6 | D5 |
> | CS | GPIO7 | D8 |
> | RST | GPIO8 | D9 |
>
> To verify a build without eyeballing the screen: the module has an onboard
> 10k pull-up on RST, so configure the RST GPIO as an input with the internal
> pull-**down** and read it. It reads `1` when the display is powered and RST is
> connected, and follows the pull (`0`) when it is not. The other four lines are
> high-impedance inputs with no pull-ups and cannot be probed this way.

## Gotchas (why the choices above are safe)

- **`SCL`/`SDA` are SPI, not I2C.** The silkscreen uses I2C-style labels, but
  this is 4-wire SPI: `SCL` = clock, `SDA` = MOSI. Data is latched on the rising
  edge of `SCL`.
- **No level shifting needed.** Logic is 3.3 V, matching the ESP32-S3. Wire every
  signal direct. The onboard XC6206 LDO only regulates panel power, so `VCC`
  tolerates 3.3–5 V; 5 V gives the LDO cleaner headroom, but 3V3 works fine.
- **`RST` on GPIO8 is fine on the S3.** GPIO8 is a plain GPIO on the ESP32-S3 —
  no boot constraint. The module's onboard 10k pullup on `RST` is harmless here,
  and is in fact useful: it's the only line the MCU can probe to confirm the
  display is powered and connected (see the RST pull-up note above).
- **No backlight control.** The backlight LED is hardwired on inside the module
  (`LEDA → 2Ω → 3.3 V`). It is **not** broken out to the header, so PWM dimming
  is impossible without a hardware mod. Don't plan firmware around dimming on
  this part.
- **Reserved S3 pins to avoid:** strapping = GPIO0/3/45/46; native USB-CDC =
  GPIO19/20; UART0 = GPIO43/44; onboard WS2812 RGB LED = GPIO21; PSRAM =
  GPIO33–37 (not broken out). Our pins (4–8) steer clear of all of these.

## SPI bring-up notes

- Use **`SPI(1)`** — verified working, and its default `miso=13` is a free pin.
  Avoid `SPI(2)`, whose default `miso=37` collides with the module's PSRAM.
  (The display is write-only, so MISO is never wired; this only matters because
  the bus claims the pin.)
- Mode 0, MSB-first, single data line (MOSI only).
- Start conservative (~20–27 MHz) on jumper wiring; GC9A01 can run faster
  (~40–80 MHz) once the link is proven stable. 40 MHz is verified working from
  cold power-up on a custom carrier PCB. If the panel is lit but blank, drop to
  1 MHz and re-run `firmware/util/test_pattern.py`: if it renders at 1 MHz but
  not at 40 MHz, the wiring is correct and the problem is signal integrity.
- Keep SCK/MOSI leads short — long dupont jumpers garble pixels at high clock.
- A weak/missing common ground is the most common cause of SPI flakiness here,
  not the code.

## Flashing reminders

- Flash offset is **`0x0`**, not `0x1000`.
- Erase first: `esptool --chip esp32s3 erase-flash`.
- Use the `ESP32_GENERIC_S3-SPIRAM_OCT` MicroPython build, not plain `GENERIC_S3` — the
  plain build doesn't enable PSRAM, leaving only ~226 KB of internal SRAM as heap, which
  reliably fails the 115,200-byte display framebuffer allocation in `portal.py` with
  `MemoryError`. Verified on the XIAO ESP32S3 (8 MB embedded octal PSRAM): free heap
  went from 226 KB to 8.3 MB after switching builds, same MicroPython version.
- If auto-reset into download mode fails: hold BOOT, tap RST (or replug USB), release BOOT.
- **A board that won't boot is not bricked.** Download mode is in mask ROM and can't be
  erased. Note that a freshly erased board boot-loops (no valid image → reset → repeat,
  roughly every 2 s), so the serial port flickers; `esptool --before default-reset
  --connect-attempts 5` connects through it. `dmesg` is usually root-only, but
  `journalctl -k` works unprivileged and shows the enumeration churn.

## Physical dimensions (for the deferred enclosure)

- PCB: 38.0 mm dia (round portion) × 45.5 mm tall including the header tab.
- Active display: 32.4 mm dia circle; visible glass ~35.6 mm.
- Thickness: PCB 1.6 mm + TFT 1.5 mm; rear SMD parts max 1.2 mm tall (header pins protrude further).
- Mounting: 2× Ø2.0 mm holes.
