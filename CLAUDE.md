# CLAUDE.md

Guidance for AI agents (Claude Code) working in this repository. Read this fully before making changes.

## What this project is

**mr-radar** is an open-source weather radar display. An ESP32-S3 drives a round 240x240 TFT and shows live NEXRAD precipitation radar composited over a base map, centered on the owner's nearest radar station. The name is a nod to the radar scene in Mel Brooks' *Spaceballs* ("We ain't found shit!").

The defining product constraint: **a person must be able to flash the firmware, enter their WiFi credentials and their nearest NEXRAD station ID, and have a working device with no other infrastructure.** The firmware must never depend on a server that only the maintainer runs. Protect this constraint in every decision.

## Architecture (read this before writing any code)

The microcontroller should not decode or composite map tiles: there is no on-device PNG decoder, and fetching tiles directly from providers would violate OpenStreetMap's tile usage policy when fanned out across many devices. (The ESP32-S3 has 2 MB PSRAM, so RAM is no longer the binding constraint it was on the C3 — but the no-decoder and provider-ToS reasons stand on their own.) Therefore the work is split:

```
ESP32-S3 firmware  --HTTPS GET-->  stateless renderer  --tiles-->  RainViewer + OSM
   (dumb client)   <--image blob--   (does the heavy        (upstream data sources)
                                       lifting + cache)
```

- **The device is a dumb client.** It does WiFi + one HTTPS GET + blit-to-display + sleep, in a robust loop. It does NOT decode PNGs, composite layers, or talk to upstream providers.
- **The renderer is stateless and cache-friendly.** It fetches PNG tiles from RainViewer (radar) and OSM (base map), alpha-composites them, crops a 240×240 window centered on the requested station, and returns either raw RGB565 bytes or a small JPEG. It owns the relationship with upstream providers: caching, rate-limit politeness, and attribution.
- **A public default instance** runs at a maintainer-operated URL so the out-of-box experience needs zero setup. The same renderer ships with a Dockerfile so anyone can self-host. The firmware's endpoint URL is configurable at provisioning time. **The maintainer's homelab is never in the data path** — the default instance is a stateless public deployment, not a home server.

If a proposed change pushes tile decoding or compositing onto the device, or makes the firmware require a self-hosted server to function at all, it is wrong. Stop and flag it.

## Repository layout

```
mr-radar/
├── firmware/    # MicroPython for the ESP32-S3. This is what people flash.
├── renderer/    # Stateless image service (Node.js + sharp). Optionally self-hosted.
├── enclosure/   # OpenSCAD -> STL. NOT YET STARTED. Do not create files here
│                #   unless explicitly asked; it is handled in a separate effort.
├── CLAUDE.md
└── README.md
```

Keep firmware and renderer concerns strictly separated. They communicate only over the HTTP contract described below. Do not let renderer dependencies (sharp, Node.js, etc.) leak into firmware reasoning, and do not assume firmware capabilities (a real OS, gigabytes of RAM) when writing firmware.

## Hardware target

- **MCU:** Waveshare ESP32-S3-Zero. Dual-core Xtensa LX7 @ 240 MHz, 512 KB SRAM + 2 MB PSRAM, 4 MB flash, native USB-CDC serial. (We originally targeted an ESP32-C3 "super mini," but those boards have a notorious antenna/PA defect — a unit that refused WiFi association at any usable range, while a known-good board on the same network connected instantly, forced the switch. Avoid the C3 super mini; the S3-Zero's GPIO map keeps the same display pins.)
- **Display:** 240×240 round TFT, GC9A01 controller, SPI (write-only, no MISO). 1.28" diameter.
- **Default pin map** — uses the module's silkscreen labels (assign explicitly in code; labels are I2C-style but the interface is 4-wire SPI):

  | Module pin | Function | GPIO |
  | --- | --- | --- |
  | VCC | 3.3–5 V power (onboard XC6206 LDO) | 3V3 |
  | GND | Ground | GND |
  | SCL | SPI clock | 4 |
  | SDA | SPI data (MOSI) | 5 |
  | DC | Data/command | 6 |
  | CS | Chip select | 7 |
  | RST | Reset (onboard 10k pullup) | 8 |

  **No backlight pin:** this module's backlight is hardwired on (LEDA → 2Ω → 3.3 V), so PWM dimming is not possible without a hardware mod. On the ESP32-S3, GPIO8 is a plain GPIO (not a strapping pin, unlike the C3), so RST here is unconstrained and the display's onboard 10k pullup is harmless. Logic is 3.3 V, matching the S3 — no level shifting needed. Verified working with `SPI(1)` (its default `miso=13` is a free pin; avoid `SPI(2)`, whose default `miso=37` collides with PSRAM). See `firmware/WIRING.md` for the full pinout, schematic notes, and dimensions. Treat the pin map as configuration, not hard-coded magic numbers.

### ESP32-S3 flashing facts that bite people
- Flash offset is **`0x0`**, NOT `0x1000` (that's the classic ESP32). Getting this wrong produces a board that won't boot.
- Erase before flashing: `esptool.py --chip esp32s3 erase_flash`.
- Use the `ESP32_GENERIC_S3` MicroPython build.
- If auto-reset into download mode fails: hold BOOT, tap RST (or replug USB), release BOOT.
- Native USB-CDC re-enumerates after flashing/reset, so the serial device name (e.g. `/dev/ttyACM0`) can change — re-check it if a connection fails.

## The HTTP contract (firmware <-> renderer)

This is the seam between the two halves. It is **stable and implemented** — do not change it without updating both `firmware/` and `renderer/` and this document in the same change.

### `GET /frame`

The primary endpoint. Returns a ready-to-display image.

**Parameters:**

| Parameter | Required | Values | Default | Notes |
| --- | --- | --- | --- | --- |
| `station` | yes* | 4-letter NEXRAD ID, e.g. `KILN` | — | Preferred; resolves to station lat/lon |
| `lat` | yes* | decimal degrees | — | Fallback if `station` not provided |
| `lon` | yes* | decimal degrees | — | Fallback if `station` not provided |
| `fmt` | no | `jpeg` \| `rgb565` | `jpeg` | See formats below |
| `theme` | no | `modern` \| `vintage` | `modern` | See themes below |

*Either `station` or `lat`+`lon` must be provided.

**Formats:**

- `jpeg` — baseline JPEG, ~10–20 KB. Content-Type: `image/jpeg`. Use for browser preview and eventually for bandwidth-constrained firmware.
- `rgb565` — raw 240×240 pixels, big-endian RGB565, exactly 115,200 bytes. Content-Type: `application/octet-stream`. This is what the firmware blits directly to the GC9A01 display buffer.

**Themes:**

- `modern` — OSM base map at natural color, radar alpha-composited on top.
- `vintage` — Dark navy base map, radar colors boosted to resemble 1990s cable TV weather radar.

**Response headers:**

- `X-Radar-Timestamp` — Unix timestamp (seconds) of the RainViewer frame used. The firmware should track this to avoid re-blitting an unchanged frame.
- `X-Partial-Data: 1` — Set if any upstream tile fetch failed. The image is still returned with whatever data was available; firmware should show a stale/degraded indicator.

**Example:**

```text
GET /frame?station=KILN&fmt=rgb565&theme=modern
```

### `GET /stations`

Returns a JSON array of all known NEXRAD stations:

```json
[{ "id": "KILN", "lat": 39.4208, "lon": -83.8217, "name": "Wilmington", "state": "OH" }, ...]
```

158 WSR-88D stations covering CONUS, Alaska, Hawaii, Puerto Rico, and Guam. Useful for provisioning UIs.

### `GET /health`

Returns `{"ok": true, "ts": <unix-ms>}`. Use for load-balancer checks and deploy validation.

## Upstream data sources (constraints, current as of early 2026)

- **RainViewer Weather Maps API** — free for personal/educational use, asks for attribution with a link to rainviewer.com. As of Jan 1 2026: max zoom level 7, 100 requests/IP/min, "Universal Blue" color scheme only, past radar only (2h history, 10-min frames), PNG only. Refreshes every ~5 min. The renderer checks RainViewer's timestamp JSON and only re-composites when a genuinely new frame exists.
- **OpenStreetMap tiles** — subject to a tile usage policy that forbids bulk/automated abuse. This is precisely why devices must NOT hit OSM directly. The renderer caches aggressively and identifies itself with a proper `User-Agent`. Respect the policy; consider a base-map provider with terms friendlier to this use if scale grows.

Attribution for both providers must be preserved in the project (README, and ideally surfaced by the renderer).

## Renderer implementation (Node.js)

The renderer lives in `renderer/` and is implemented in Node.js (≥20) using `sharp` for image processing.

**Key modules:**

| File | Responsibility |
| --- | --- |
| `src/server.js` | Express entry point; routes `/frame`, `/stations`, `/health` |
| `src/handler.js` | Request parsing, validation, response headers |
| `src/composite.js` | Core pipeline: fetch → stitch → composite → crop → encode |
| `src/tileMath.js` | Web Mercator slippy-map math; computes 2×2 tile block |
| `src/rainviewer.js` | RainViewer timestamp API + tile URL resolution; 2-min cache |
| `src/tiles.js` | Tile fetch + in-memory LRU cache (OSM: 24h TTL, radar: 5min TTL) |
| `src/stations.js` | Static NEXRAD station database; `resolveStation(id)` |

**Caching layers (innermost to outermost):**

1. Raw tile cache in `tiles.js` (Map, 300-entry cap, per-provider TTL)
2. RainViewer frame metadata cache in `rainviewer.js` (2-min TTL)
3. Fully composited frame cache in `composite.js` (keyed by lat/lon + theme + fmt + radar path)

Do not add a database or filesystem cache. Stateless in-memory cache is sufficient and keeps the renderer trivially deployable.

**`sharp` note:** Uses prebuilt libvips binaries. Works on Debian/Ubuntu-based images (`node:20-slim`) without extra apt packages. Do not use Alpine — musl libc is incompatible with the prebuilt binaries.

## Cadence model

Decouple the two timers:
- **Renderer** refreshes its cached composite every ~2-3 min, re-compositing only when RainViewer publishes a new frame. One shared cache serves all devices, keeping upstream request volume flat regardless of device count.
- **Device** may poll every 1-2 min for a "live" feel, but it polls the renderer, not upstream. Since the cached image only changes when upstream does, frequent polling wastes nothing meaningful.

Do not have the device poll upstream providers. Do not have the renderer re-fetch upstream on every device request.

## Tile math note

At zoom 7 the owner's location often falls near a tile edge, so a centered 240×240 crop may span up to 4 adjacent tiles. The renderer fetches a 2×2 tile block (512×512 stitched), then crops the 240×240 window centered on the station's pixel position. See `src/tileMath.js` for the implementation. A naive single-tile fetch will put the location in a corner — don't do it.

## Firmware provisioning & settings

Configuration lives in `/config.json` on the device's LittleFS. There is no `secrets.py`; that pattern is retired.

**Boot sequence (`main.py`):** checks for `/config.json` with a non-empty `wifi_ssid`. If missing or blank → portal mode. Otherwise → radar mode.

**Portal mode (`portal.py` → `run()`):**

- Broadcasts a WPA2 AP: SSID `mr-radar-setup`, passphrase derived from `machine.unique_id()` (12 hex chars, unique per device, stable across reboots).
- Draws SSID, passphrase, and `192.168.4.1` on the round display so the user knows how to connect.
- Serves a settings form at `http://192.168.4.1/`. On submit, saves `/config.json` and reboots.
- To re-enter portal mode from the REPL: `import os; os.remove('/config.json')` then reset.

**Radar mode (`main.py` → `radar.main()`):**

- On startup, draws a "Connecting…" screen, then a "Connected" screen showing the settings URL (`http://<device-LAN-IP>`) and WiFi SSID. Holds for at least 20 seconds (or until first frame arrives, whichever is longer) so the user has time to note the settings URL.
- Runs `portal.serve()` in a background thread (24 KB stack) — the same settings form, now reachable at the device's LAN IP while radar runs. Saving reboots the device; the browser auto-redirects back to `/` once the server is back up.
- Station dropdown is populated from `GET /stations` on the renderer (HTTP/1.0 to avoid chunked encoding). Falls back to a text input if the renderer is unreachable.

**`/config.json` schema:**

```json
{
  "wifi_ssid": "your-network",
  "wifi_password": "your-password",
  "station": "KILN",
  "renderer_url": "https://mr-radar.fly.dev",
  "theme": "vintage",
  "poll_seconds": 60,
  "tz_offset": -5
}
```

`tz_offset` is a float, hours offset from UTC (e.g. -5 for Eastern, -8 for Pacific). Used for both the clock display and the wall-clock sweep position. Configurable from the settings form in both portal mode and STA mode.

**Display color notes (`radar.py`, `portal.py`):** The GC9A01 expects big-endian RGB565; `framebuf.FrameBuffer` on the ESP32 (little-endian) stores pixels little-endian. All colors passed to framebuf must be byte-swapped: `swapped = ((color & 0xFF) << 8) | (color >> 8)`. The pre-swapped constants in `radar.py` are named `_S_*` (e.g. `_S_GREEN = 0xE007` for big-endian `0x07E0`).

**Thread layout in radar mode:**

| Thread | Stack | Responsibility |
| --- | --- | --- |
| Main | default | Sweep animation + display ownership |
| Fetch | 16–32 KB | `fetch_loop`: pulls `/frame` every 60 s |
| Settings | 24 KB | `portal.serve`: HTTP settings server on :80 |

## Robustness expectations (non-negotiable for both halves)

- **Firmware:** never hard-fault to a black screen on a transient error. Wrap the network loop in try/except, keep a "last known good frame," show a small status indicator (e.g. a corner dot: green=fresh, yellow=stale, red=offline), and use a watchdog so a hang self-recovers. WiFi creds and all settings are stored in `/config.json`, provisioned via the captive portal or settings server — never hard-coded.
- **Renderer:** stateless, no database; cache in memory only. Tolerate upstream outages and partial data. Be a polite upstream client (caching, backoff, User-Agent). Must run identically on the public instance, a free-tier PaaS, or a Raspberry Pi.

## Working conventions for agents

- **Confirm before scaffolding large structures.** Propose the file/module layout and get agreement before generating many files.
- **Match the language to the half.** Firmware is MicroPython (assume no CPython-only stdlib; memory is scarce; prefer `const`, preallocated buffers, and streaming over large allocations). Renderer is Node.js ≥20 with `sharp` and Express.
- **Touch the enclosure directory only when explicitly asked.** It is intentionally deferred.
- **Keep the contract in sync.** Any HTTP-contract change updates firmware, renderer, and this document together.
- **Cite the constraints, don't relitigate them.** The architecture split exists for hard reasons (device RAM, no on-device PNG decode, provider ToS). Don't propose on-device compositing or homelab-dependence without explicitly raising it as a constraint change first.
- **Prefer small, reviewable changes.** This is hardware-adjacent; a bad firmware change costs a reflash. Favor incremental, testable steps.
- **Validate hardware assumptions cheaply.** When touching display code, prefer a test-pattern path that proves wiring before layering on network complexity.

## Firmware animation architecture

The firmware runs a classic PPI (Plan Position Indicator) sweep animation. Understanding this is essential before touching any display or fetch code.

**Two buffers, strict ownership:**

- `src` — the last successfully fetched frame (bytearray, 115,200 bytes). The fetch thread writes a fresh `src` under a lock; the main thread swaps it in at the rotation boundary. The clock overlay is baked directly into `src` (see below), so `src` is not purely read-only, but it is only written by the main thread.
- `fb` (inside `sweep.Sweep`) — the live framebuffer. The sweep overlays the radar image with the sweep line and trail glow. Never blit `src` directly to the display after the first frame; always go through `fb`.

**Per-frame render sequence** (`_render` in `radar.py`):

1. `restore_trail()` — undo the previous trail glow from `fb`, using saved pre-blend values (does NOT need `src`).
2. `restore_line(src)` — undo the previous AA sweep line from `fb` using `src`.
3. `paint_wedge(src, a0, a1)` — copy radar pixels from `src` into the newly swept wedge.
4. `paint_trail(az)` — blend the glow behind the sweep line into `fb`, saving pre-blend values for next frame's restore.
5. `sweep_line(az)` — draw the bright AA sweep line.
6. `blit_band(y0, y1)` — push only the dirty rectangle to the display via SPI.

**Sweep azimuth and wall-clock alignment:** The sweep is driven by `time.time()` with sub-second interpolation via `ticks_ms()` (see `_ntp_wall_sec` / `_ntp_sec_ms` in `main()`). The azimuth formula is `(seconds_within_minute * 6° + 270°) % 360°`, which maps second 0 to 270° (top / 12 o'clock) and proceeds clockwise. The rotation boundary (360°→0°, where `src` is swapped) falls at second 15 (3 o'clock). Without NTP the sweep falls back to a free-running `ticks_ms()` timer.

**Clock overlay:** `_paint_clock` bakes a 2×-scaled (16 px tall) HH:MM timestamp directly into `src` once per minute — no per-frame cost. The text has no background; radar imagery shows through the gaps. `_clock_str` adds 15 seconds to the wall time so the text updates at second 45 (180°, 9 o'clock), which is 15 seconds before the sweep reveals the 12 o'clock area at second 0. When a new frame arrives from the fetch thread, `_stamp_clock_pixels` re-bakes the current cached text into the new `src` immediately.

Frame swap (new `src` from the fetch thread) happens at the 360°→0° rotation boundary (second 15, 3 o'clock) so the sweep never reads a partially-coherent frame.

**SPI performance:** `SPI_BAUD = 40_000_000` (40 MHz). The GC9A01 supports 40–80 MHz. Do not lower this — it was briefly 20 MHz during bring-up and caused visible choppiness. `blit_band` blits only the dirty y-range (the trail bounding box) each frame, not the full 240×240.

**`paint_trail` trig optimization:** The trail glow calls `_blend_radial` for each of the 40 trail steps. Naively that is 80 `sin`/`cos` calls per frame. Instead, relative-angle tables (`_TRAIL_REL_COS`, `_TRAIL_REL_SIN`) are precomputed at module import and the angle-addition identity `sin(az+rel) = sin(az)cos(rel) + cos(az)sin(rel)` is used inside `paint_trail`, reducing the hot path to 2 trig calls per frame.

## MicroPython viper notes (hard-won)

These are non-obvious constraints that bit us. Read before writing any `@micropython.viper` code.

**`ptr32` + `array('i', ...)` is unreliable for storing data.** Using `ptr32` to write pixel offsets into an `array('i', ...)` and reading them back produces garbage in practice. Use `bytearray` and `ptr8` instead. If offsets are always even and fit in 16 bits (e.g., max `o//2 = 57599 < 65536` for a 240×240 RGB565 buffer), store them as little-endian uint16 pairs — two bytes per entry, read back with `px[i*2] | (px[i*2+1] << 8)`.

**Save/restore of per-pixel data must restore in REVERSE order.** When multiple adjacent radials (0.5° apart) map to the same display pixel due to integer rounding, each radial appends a new save entry with whatever is currently in `fb`. Restoring forward leaves the pixel at the intermediate blended value from the second-to-last visit. Restoring in reverse (`for i in range(n-1, -1, -1)`) means the earliest save — which holds the true original value — wins. This is the correct fix; forward iteration produces a subtle but catastrophic accumulation of the glow color over time.

**Performance split:** use `@micropython.native` for float trig (one `sin`/`cos` per radial, converted to 11-bit fixed-point integers), then pass those integers to a `@micropython.viper` inner loop that does pure integer arithmetic with `ptr8` raw buffer access. Float boxing inside a viper loop kills framerate. Module-level integer constants (e.g. `_MAX_TRAIL_PX`) are accessible in viper via `int(CONSTANT)`, but storing them as instance variables (`self._trail_cap`) is safer and equally fast.

**mpremote session chaining:** use `mpremote connect /dev/ttyACM0 cp a :a + cp b :b + run c.py` to upload multiple files and run in a single session. Separate `mpremote` invocations each open/close the port and are slower; if another process holds `/dev/ttyACM0`, use `fuser /dev/ttyACM0` to find and kill it.

## Build status & suggested next steps

**Done:**

1. ✅ Renderer MVP — fetch + composite + crop + serve RGB565/JPEG; station database; themes.
2. ✅ MicroPython flashed; REPL over serial verified (ESP32-S3-Zero).
3. ✅ Display bring-up: vendored GC9A01 driver (`gc9a01py.py`) + test pattern; wiring proven on the S3-Zero.
4. ✅ Firmware client loop (`radar.py`): WiFi + `GET /frame?station=KILN&fmt=rgb565` + blit + sleep, tested end-to-end against the renderer.
5. ✅ PPI sweep animation (`sweep.py`): clock-driven radial sweep with anti-aliased line, persistence glow trail (20° behind the sweep, quadratic alpha ramp), dirty-rect band blit. Tested at ~22 fps.
6. ✅ Provisioning: captive-portal AP (`portal.py`) on first boot; WPA2 passphrase derived from chip ID; settings drawn on display. Config stored in `/config.json`; `secrets.py` retired.
7. ✅ Boot status screen: "Connecting…" → "Connected" with settings URL and SSID; holds ≥20 s or until first frame.
8. ✅ In-radar settings server: `portal.serve()` runs on :80 in a background thread; station list populated as a dropdown from `/stations`; browser redirects back after reboot.
9. ✅ NTP clock overlay: HH:MM at 12 o'clock, 2× scaled (16 px), no background. Baked into `src` once per minute at second 45 so correct time is visible when the sweep crosses 12 o'clock at second 0. `tz_offset` (hours) configurable in the settings form.
10. ✅ Wall-clock sweep alignment: second 0 = 12 o'clock (top); sweep proceeds clockwise; rotation boundary (frame swap) at second 15 (3 o'clock). Sub-second interpolation via `ticks_ms()` boundary tracking for smooth motion.

**Remaining:**

1. Robustness pass: last-good-frame, status indicator (corner dot: green/yellow/red), watchdog timer.
2. Polish: JPEG transport, OTA. (Backlight dimming is *not* possible on the current display module — its backlight is hardwired on; would require a different module or a hardware mod.)

Enclosure is out of scope here.
