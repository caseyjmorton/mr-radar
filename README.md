# mr-radar

A tiny weather radar display. An ESP32-S3 drives a round 240×240 TFT and continuously shows live NEXRAD precipitation radar composited over a base map, centered on your nearest radar station.

The name is a nod to the radar scene in Mel Brooks' *Spaceballs*. We hope you find *something* on it.

> **Status:** v0.1.0 — renderer, firmware, and enclosure all at initial release.

## What it is

A small, always-on desk object that shows you what the weather radar is doing right now near you, on a circular screen that looks the part. Flash it, give it your WiFi credentials and your nearest NEXRAD station ID (e.g. `KILN`), and it works — no server of your own required.

## How it works

The device deliberately doesn't decode or composite map imagery itself (no on-device PNG decoder), and having many devices pull tiles directly from public providers would abuse those providers' usage policies. So the work is split in two:

```text
ESP32-S3 firmware  --HTTPS GET-->  stateless renderer  --tiles-->  RainViewer + OSM
   (dumb client)   <--image blob--   (does the heavy        (radar + base map)
                                       lifting + caching)
```

- **The device** does almost nothing: connect to WiFi, fetch one image from a URL, draw it to the screen, wait, repeat.
- **The renderer** does the real work: it pulls radar tiles and base-map tiles, composites them, crops a view centered on your station, shrinks it to fit the round screen, and serves it as a ready-to-display image. It caches results so upstream providers aren't hammered.

You can use the **public default renderer** (no setup) or **self-host your own** (a Dockerfile is included). Either way, the firmware just points at a URL — it never depends on any one person's home server.

## Repository layout

```text
mr-radar/
├── firmware/
│   ├── src/   # MicroPython source — this is what you flash
│   ├── util/  # Developer utilities (not flashed)
│   └── doc/   # Wiring and hardware notes
├── renderer/  # Stateless image service (Node.js + sharp) — optional to self-host
├── enclosure/ # CadQuery parametric 3D-printable case — STLs in GitHub Releases
├── CLAUDE.md  # guidance for AI-assisted development
└── README.md
```

## Hardware

- **Seeed XIAO ESP32S3** dev board — the only supported board. 8 MB flash, 8 MB octal PSRAM. **Flash size matters:** the released binary embeds a filesystem sized for 8 MB flash and will not boot correctly on a 4 MB board.

  Earlier revisions also ran on the ESP32-C3 and the 4 MB Waveshare ESP32-S3-Zero. Both were dropped: neither has the memory headroom to hold the 115,200-byte framebuffer alongside WiFi without fragmentation stalls, and the sweep animation misses its frame budget on both. (The C3 "super mini" boards additionally have a notorious antenna/PA defect — WiFi wouldn't associate at any usable range.)
- **240×240 round TFT**, GC9A01 controller, SPI, 1.28" diameter

Default wiring (configurable in firmware; the display's pins use its own silkscreen labels). The GPIO column is **raw GPIO numbers, not the XIAO's `D` labels** — wiring to the same-numbered `D` pads puts every line on the wrong pin:

| Module pin | GPIO | XIAO pad |
| --- | --- | --- |
| VCC | 3V3 | 3V3 |
| GND | GND | GND |
| SCL | 4 | D3 |
| SDA | 5 | D4 |
| DC | 6 | D5 |
| CS | 7 | D8 |
| RST | 8 | D9 |

`SCL`/`SDA` are I2C-style labels but the interface is 4-wire SPI (`SCL` = clock, `SDA` = MOSI). The GC9A01 is write-only, so no MISO is needed, and the backlight is hardwired on (no control pin) — which means an unlit panel indicates no power reaching the module, not a software fault. Logic is 3.3 V — no level shifting. See [`firmware/doc/WIRING.md`](firmware/doc/WIRING.md) for the full pinout, schematic notes, and dimensions.

## Getting started

### 1. Find your NEXRAD station

Look up the four-letter WSR-88D station ID nearest to you. The renderer's `/stations` endpoint lists all 158 stations, or search the [NWS radar site](https://www.weather.gov/ridge/). Example: `KILN` covers the Cincinnati/Dayton area from Wilmington, OH.

### 2. Flash the firmware

The easiest path uses a pre-built binary from the [latest firmware release](https://github.com/caseyjmorton/mr-radar/releases/latest), which bundles MicroPython and all source files into a single image. There's a separate binary per chip — pick the one matching your board.

1. Install tooling: `pip install esptool`
2. Download `mr-radar-firmware-s3-vX.Y.Z.bin` from the latest release. It targets the **Seeed XIAO ESP32S3 (8 MB flash)**; the filesystem is baked into the image at a fixed size, so flashing it to a 4 MB board produces a device that powers on but never starts — MicroPython can't mount the mismatched filesystem, reformats it, and lands at an empty REPL with no display and no setup AP.
3. Erase and flash (note the `0x0` offset — **not** `0x1000`):

   ```bash
   esptool --chip esp32s3 --port /dev/ttyACM0 erase-flash
   esptool --chip esp32s3 --port /dev/ttyACM0 --baud 460800 write-flash 0x0 mr-radar-firmware-s3-vX.Y.Z.bin
   ```

   The port name varies by OS: `/dev/ttyACM0` on Linux, `/dev/tty.usbmodem*` on macOS, `COM#` on Windows.

4. The device boots into portal mode on first power-up — connect to the `mr-radar-setup` WiFi network. The passphrase is unique to your device and shown on the display. Enter your WiFi credentials, NEXRAD station, and renderer URL. If you're using the public instance, the renderer URL is `https://mr-radar.fly.dev`.

> If the board won't enter download mode: hold **BOOT**, tap **RST**, release **BOOT**, then retry.
>
> **You cannot brick the board this way.** Download mode lives in mask ROM and can't be erased or overwritten, so a device that won't boot is always recoverable with `erase-flash` and a re-flash at `0x0`. Note that a freshly erased board *boot-loops* — the ROM finds no valid image and resets every couple of seconds, so the serial port flickers in and out. That's normal; esptool connects through it.

**Manual flash (development):** If you prefer to use your own MicroPython build, install `mpremote`, flash an `ESP32_GENERIC_S3-SPIRAM_OCT` binary from [micropython.org/download](https://micropython.org/download/), then copy each file from `firmware/src/` to the device: `mpremote connect /dev/ttyACM0 cp firmware/src/<file> :<file>`. Use the `SPIRAM_OCT` variant, not plain `GENERIC_S3` — the plain build doesn't enable PSRAM, and the 115,200-byte display framebuffer allocation reliably fails with `MemoryError` without it.

> **Bringing up new hardware?** Run `firmware/util/test_pattern.py` to prove the SPI wiring before layering on network code. If the panel stays dark, check whether the backlight is lit: it's hardwired on, so an unlit panel means the module isn't getting power at all.

### 3. Run the renderer (optional)

The default device experience uses the public instance at `https://mr-radar.fly.dev`, so this step is only needed if you want to self-host.

**Docker (recommended):**

```bash
docker pull ghcr.io/caseyjmorton/mr-radar-renderer:latest
docker run -p 3000:3000 ghcr.io/caseyjmorton/mr-radar-renderer:latest
```

**From source:**

```bash
cd renderer
npm install
npm start          # listens on :3000
```

## Clock & timezone

Along with the radar, the display shows the current time as **HH:MM** at the top of the dial (the 12 o'clock position, just as the sweep passes it). The time is kept accurate over NTP, so you never set it by hand — you only tell the device your timezone.

Two related settings, both configurable in the device's setup page (the `mr-radar-setup` WiFi portal on first boot, and the device's own address on your network after that):

- **UTC offset** — your timezone as hours from UTC. With DST auto-adjust **off**, this is the exact offset you want. With it **on**, use your *standard-time* offset (−5 Eastern, −6 Central, −7 Mountain, −8 Pacific).
- **Daylight Saving Time** — when enabled, the device adds an hour automatically while US daylight saving is in effect (02:00 on the 2nd Sunday of March through 02:00 on the 1st Sunday of November) and rolls the clock over on its own at each transition — no reboot needed. Leave it off where DST isn't observed (Arizona, Hawaii, Puerto Rico, Guam) and just set the offset directly.

The timezone affects only the displayed clock; the radar sweep is aligned to real wall-clock seconds and looks the same regardless.

## Renderer API

### `GET /frame`

Returns a 240×240 radar image ready to blit to the display.

| Parameter | Required | Values | Default |
| --- | --- | --- | --- |
| `station` | yes* | NEXRAD ID, e.g. `KILN` | — |
| `lat` / `lon` | yes* | decimal degrees | — |
| `fmt` | no | `jpeg` \| `rgb565` | `jpeg` |
| `theme` | no | `modern` \| `vintage` | `modern` |

*Either `station` or `lat`+`lon` must be provided.

**Formats:**

- `jpeg` — baseline JPEG, ~10–20 KB (`image/jpeg`). Opens directly in a browser.
- `rgb565` — raw big-endian RGB565, exactly 115,200 bytes (`application/octet-stream`). This is what the firmware blits to the GC9A01 frame buffer.

**Themes:**

- `modern` — OSM street map base with radar overlay.
- `vintage` — Dark navy background with boosted radar colors, resembling 1990s cable TV weather radar.

**Response headers:**

- `X-Radar-Timestamp` — Unix seconds of the RainViewer frame used. Firmware uses this to skip re-blitting unchanged frames.
- `X-Partial-Data: 1` — One or more upstream tiles failed; image is best-effort.

**Examples:**

```text
# JPEG for browser preview
GET /frame?station=KILN&fmt=jpeg&theme=vintage

# Raw bytes for firmware
GET /frame?station=KILN&fmt=rgb565&theme=modern
```

### `GET /stations`

Returns a JSON array of all 158 WSR-88D NEXRAD stations (CONUS, Alaska, Hawaii, Puerto Rico, Guam):

```json
[{ "id": "KILN", "lat": 39.4208, "lon": -83.8217, "name": "Wilmington", "state": "OH" }]
```

### `GET /health`

Returns `{"ok": true, "ts": <unix-ms>, "version": "<X.Y.Z>"}`.

## Data sources & attribution

- **Radar:** [RainViewer](https://www.rainviewer.com/) Weather Maps API — free for personal and educational use. As of early 2026 it serves past radar (2-hour history, ~10-minute frames) at up to zoom level 7, refreshed roughly every 5 minutes.
- **Base map:** OpenStreetMap contributors. Map data © OpenStreetMap contributors, available under the Open Database License.

Radar data is provided by RainViewer; this project is not affiliated with or endorsed by RainViewer. Please honor each provider's terms of use when self-hosting the renderer.

## A note on accuracy & timing

Radar updates roughly every 5 minutes upstream, and at the supported zoom level the view shows regional precipitation patterns rather than street-level detail. This is a glanceable "is it about to rain on me" object, not a meteorological instrument. Do not use it for safety-critical or severe-weather decisions — consult official sources such as the National Weather Service.

## Enclosure

A parametric 3D-printable case is in `enclosure/`. It's a three-part assembly (body, back panel, top panel) designed to print cleanly on a 0.6 mm nozzle FDM printer without supports. STL files are published with each [enclosure release](https://github.com/caseyjmorton/mr-radar/releases).

> **Careful with the display screws:** the GC9A01 module is thin glass on a small PCB, mounted to the front panel with screws through its corner holes. Snug is enough — do not overtighten. Over-torquing them can crack or otherwise damage the display. Hand-tighten only, and stop as soon as the panel is seated.

## Contributing

Early days — issues and discussion welcome. If you're using AI-assisted tooling, read [`CLAUDE.md`](CLAUDE.md) first; it captures the architecture constraints that keep the device server-independent.

## Acknowledgements

- Display driver: [gc9a01py](https://github.com/russhughes/gc9a01py) by Russ Hughes (MIT) — vendored in `firmware/`; license preserved at [`firmware/LICENSE.gc9a01py`](firmware/LICENSE.gc9a01py).

## License

TBD.
