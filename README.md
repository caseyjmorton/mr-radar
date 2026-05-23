# mr-radar

A tiny weather radar display. An ESP32-S3 drives a round 240×240 TFT and continuously shows live NEXRAD precipitation radar composited over a base map, centered on your nearest radar station.

The name is a nod to the radar scene in Mel Brooks' *Spaceballs*. We hope you find *something* on it.

> **Status:** early development. Renderer complete; firmware in progress.

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
├── firmware/    # MicroPython for the ESP32-S3 — this is what you flash
├── renderer/    # Stateless image service (Node.js + sharp) — optional to self-host
├── enclosure/   # 3D-printable case (OpenSCAD → STL) — coming later
├── CLAUDE.md    # guidance for AI-assisted development
└── README.md
```

## Hardware

- **Waveshare ESP32-S3-Zero** dev board (we tried the ESP32-C3 "super mini" first, but its antenna/PA is unreliable — skip it)
- **240×240 round TFT**, GC9A01 controller, SPI, 1.28" diameter

Default wiring (configurable in firmware; pins use the module's silkscreen labels):

| Module pin | ESP32-S3 GPIO |
| --- | --- |
| VCC | 3V3 |
| GND | GND |
| SCL | 4 |
| SDA | 5 |
| DC | 6 |
| CS | 7 |
| RST | 8 |

`SCL`/`SDA` are I2C-style labels but the interface is 4-wire SPI (`SCL` = clock, `SDA` = MOSI). The GC9A01 is write-only, so no MISO is needed, and the backlight is hardwired on (no control pin). Logic is 3.3 V, matching the ESP32-S3 — no level shifting. See [`firmware/WIRING.md`](firmware/WIRING.md) for the full pinout, schematic notes, and dimensions.

## Getting started

### 1. Find your NEXRAD station

Look up the four-letter WSR-88D station ID nearest to you. The renderer's `/stations` endpoint lists all 158 stations, or search the [NWS radar site](https://www.weather.gov/ridge/). Example: `KILN` covers the Cincinnati/Dayton area from Wilmington, OH.

### 2. Flash the firmware

1. Install tooling: `pip install esptool mpremote`
2. Download a current MicroPython `ESP32_GENERIC_S3` build from [micropython.org/download](https://micropython.org/download/).
3. Erase and flash (note the `0x0` offset — the S3 is **not** `0x1000`):

   ```bash
   esptool.py --chip esp32s3 --port /dev/ttyACM0 erase_flash
   esptool.py --chip esp32s3 --port /dev/ttyACM0 --baud 460800 \
       write_flash -z 0x0 ESP32_GENERIC_S3-<version>.bin
   ```

4. Confirm the REPL: `mpremote connect /dev/ttyACM0 repl` (Ctrl-] to exit).
5. Copy the firmware files and provision WiFi credentials, station ID, and renderer URL.

> If the board won't enter download mode: hold **BOOT**, tap **RST**, release **BOOT**, then retry.

### 3. Run the renderer (optional)

The default device experience uses the public instance, so this step is only needed if you want to self-host.

```bash
cd renderer
npm install
npm start          # listens on :3000
```

Or with Docker:

```bash
docker build -t mr-radar-renderer renderer/
docker run -p 3000:3000 mr-radar-renderer
```

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

Returns `{"ok": true, "ts": <unix-ms>}`.

## Data sources & attribution

- **Radar:** [RainViewer](https://www.rainviewer.com/) Weather Maps API — free for personal and educational use. As of early 2026 it serves past radar (2-hour history, ~10-minute frames) at up to zoom level 7, refreshed roughly every 5 minutes.
- **Base map:** OpenStreetMap contributors. Map data © OpenStreetMap contributors, available under the Open Database License.

Radar data is provided by RainViewer; this project is not affiliated with or endorsed by RainViewer. Please honor each provider's terms of use when self-hosting the renderer.

## A note on accuracy & timing

Radar updates roughly every 5 minutes upstream, and at the supported zoom level the view shows regional precipitation patterns rather than street-level detail. This is a glanceable "is it about to rain on me" object, not a meteorological instrument. Do not use it for safety-critical or severe-weather decisions — consult official sources such as the National Weather Service.

## Contributing

Early days — issues and discussion welcome. If you're using AI-assisted tooling, read [`CLAUDE.md`](CLAUDE.md) first; it captures the architecture constraints that keep the device server-independent.

## Acknowledgements

- Display driver: [gc9a01py](https://github.com/russhughes/gc9a01py) by Russ Hughes (MIT) — vendored in `firmware/`; license preserved at [`firmware/LICENSE.gc9a01py`](firmware/LICENSE.gc9a01py).

## License

TBD.
