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
├── firmware/
│   ├── src/     # MicroPython source files — what gets flashed to the device.
│   ├── util/    # Developer utilities (test_pattern.py, etc.); not flashed.
│   ├── doc/     # Hardware docs (WIRING.md, pinout notes).
│   └── test/    # Unit tests (future).
├── renderer/    # Stateless image service (Node.js + sharp). Optionally self-hosted.
├── enclosure/   # CadQuery parametric enclosure; STLs built by CI.
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

  **No backlight pin:** this module's backlight is hardwired on (LEDA → 2Ω → 3.3 V), so PWM dimming is not possible without a hardware mod. On the ESP32-S3, GPIO8 is a plain GPIO (not a strapping pin, unlike the C3), so RST here is unconstrained and the display's onboard 10k pullup is harmless. Logic is 3.3 V, matching the S3 — no level shifting needed. Verified working with `SPI(1)` (its default `miso=13` is a free pin; avoid `SPI(2)`, whose default `miso=37` collides with PSRAM). See `firmware/doc/WIRING.md` for the full pinout, schematic notes, and dimensions. Treat the pin map as configuration, not hard-coded magic numbers.

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
- `X-Renderer-Version` — semver of the renderer that served the frame (matches `renderer/package.json`). Useful for fleet-side debugging.

**Request headers (expected from firmware):**

- `User-Agent: mr-radar-fw/<X.Y.Z>` — semver of the firmware that issued the request (matches `firmware/src/version.py`). Renderer access logs key on this to see firmware version distribution across the fleet.

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

Returns `{"ok": true, "ts": <unix-ms>, "version": "<X.Y.Z>"}`. Use for load-balancer checks and deploy validation; `version` echoes `renderer/package.json` so you can confirm what's actually running.

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
- **Device** polls the renderer (not upstream) once per minute. The fetch is kicked off when the wall clock hits `FETCH_TRIGGER_SEC` (second 45 = sweep at 9 o'clock / 180°), giving ~30 s to download before the rotation-boundary frame swap at second 15. Since the cached image only changes when upstream does, this polling wastes nothing meaningful.

Do not have the device poll upstream providers. Do not have the renderer re-fetch upstream on every device request.

**Keep-alive fetch (firmware):** the TLS handshake costs ~600–800 ms of GIL-held crypto on this MCU, which would freeze the sweep once per poll. So `fetch_loop` opens the (TLS) connection **once** (`open_conn`, during startup before the sweep runs) and reuses it for every subsequent poll via HTTP keep-alive (`fetch_over` sends `Connection: keep-alive` and reads exactly one frame, capping the body read so it never consumes into the next response). A stale socket (server closed it during the idle gap) is detected on use and reopened once. Verified that the public renderer holds the idle connection across the ~50 s between polls, so steady-state fetches do zero handshakes. The body read is throttled (`FETCH_THROTTLE_MS`, sleep between `FETCH_CHUNK`-byte reads) to spread the ~115 KB over ~10 s so it never starves the render thread. `open_conn` prints `conn: opened in N ms`, which only fires on startup or a reconnect — useful as a reconnect signal.

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
  "tz_offset": -5,
  "dst": true
}
```

`tz_offset` is a float, hours offset from UTC. When `dst` is `false` it is the actual offset you want; when `dst` is `true` it is the **standard-time** offset (e.g. -5 Eastern, -8 Pacific, -7 Mountain) and the firmware adds one hour automatically while US daylight saving is in effect.

`dst` (boolean, default `false`) enables automatic US DST adjustment (02:00 on the 2nd Sunday of March → 02:00 on the 1st Sunday of November). NEXRAD is US-only so US rules are the right scope; regions that don't observe DST (Arizona, Hawaii, Puerto Rico, Guam) simply leave it off. The adjustment is recomputed every minute in `_clock_str` (`_is_us_dst` / `_nth_sunday`), so the clock rolls over at the transition without a reboot. **DST only affects the displayed clock, never the sweep** — the sweep keys off seconds-within-minute, which a whole-hour shift leaves unchanged.

Both are configurable from the settings form in portal mode and STA mode.

**Display color notes (`radar.py`, `portal.py`):** The GC9A01 expects big-endian RGB565; `framebuf.FrameBuffer` on the ESP32 (little-endian) stores pixels little-endian. All colors passed to framebuf must be byte-swapped: `swapped = ((color & 0xFF) << 8) | (color >> 8)`. The pre-swapped constants in `radar.py` are named `_S_*` (e.g. `_S_GREEN = 0xE007` for big-endian `0x07E0`).

**Thread layout in radar mode:**

| Thread | Stack | Responsibility |
| --- | --- | --- |
| Main | default | Sweep animation + display ownership |
| Fetch | 16–32 KB | `fetch_loop`: keep-alive `/frame` poll, kicked off at second 45 |
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
- **Keep the device in sync with local firmware.** Whenever possible, after editing a firmware file, copy it to the device so the on-device code matches the working tree (e.g. `mpremote connect /dev/ttyACM0 cp <file> :<file>`). A stale device silently tests old code. Before relying on a device test, confirm every firmware file you changed has been uploaded; when validating viper changes specifically, force a fresh import (`del sys.modules['sweep']` then re-import, or soft-reset) since `import` returns the cached old module otherwise.

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

`_stamp_clock_pixels` always saves the original `src` values at each clock pixel position into `_CLOCK_SAVE_BUF` before overwriting them. When the minute changes, `_unstamp_clock_pixels` restores those saved values first, erasing the old text cleanly before the new text is stamped. This prevents ghosting (old digit pixels persisting under new ones) across minute boundaries. Because `_stamp_clock_pixels` is also called on each new radar frame, `_CLOCK_SAVE_BUF` always reflects the current frame's radar data at the clock positions.

Frame swap (new `src` from the fetch thread) happens at the 360°→0° rotation boundary (second 15, 3 o'clock) so the sweep never reads a partially-coherent frame.

**Frame rate:** `TARGET_MS = 40` in `radar.py` caps the loop at ~25 fps (the sweep speed itself is wall-clock driven, so the cap only bounds how often it redraws). The loop sleeps only the remainder after the render, so render work below 40 ms costs nothing extra. It was 100 ms (~10 fps) during bring-up; 40 ms is comfortably within the render budget after the viper work below.

**SPI performance:** `SPI_BAUD = 40_000_000` (40 MHz). The GC9A01 supports 40–80 MHz. Do not lower this — it was briefly 20 MHz during bring-up and caused visible choppiness. `blit_band` blits only the dirty y-range (the trail bounding box) each frame, not the full 240×240.

**`paint_trail` trig optimization:** The trail glow covers 40 radials. Relative-angle tables (`_TRAIL_REL_COS`, `_TRAIL_REL_SIN`) are precomputed at module import and the angle-addition identity `sin(az+rel) = sin(az)cos(rel) + cos(az)sin(rel)` reduces the per-frame trig to 2 calls. `paint_trail` (native) packs each step's direction vector (`sa_fp+2048`, `ca_fp+2048` as LE uint16 pairs) into `_trail_dirs`, then a single `_blend_trail_all_viper()` call paints all 40 radials in one pass — collapsing what used to be ~40 native→viper transitions per frame into one.

**AA sweep line (`_aa_radial` + `_aa_line_viper`):** `_aa_radial` (native) does the float prep — trig, one divide for the slope, and `pscale` (the perpendicular-distance normalizer, which is exactly `|cos|` for an x-major line and `|sin|` for a y-major one, so **no `sqrt` is needed**) — stashes the prepped fixed-point values on `self`, then calls the viper loop. `_aa_line_viper` does the per-pixel coverage in pure integer math: coverage is prescaled to a 0–256 alpha range (`av = _AA_C0 - perp_dist*256`), and the fp16 minor-axis distance is dropped to fp8 before multiplying by `pscale` (fp8) so the product stays inside 32-bit signed. Touched offsets are recorded as `o//2` LE uint16 pairs in `_line_px` for `restore_line()`.

## MicroPython viper notes (hard-won)

These are non-obvious constraints that bit us. Read before writing any `@micropython.viper` code.

**`ptr32` + `array('i', ...)` is unreliable for storing data.** Using `ptr32` to write pixel offsets into an `array('i', ...)` and reading them back produces garbage in practice. Use `bytearray` and `ptr8` instead. If offsets are always even and fit in 16 bits (e.g., max `o//2 = 57599 < 65536` for a 240×240 RGB565 buffer), store them as little-endian uint16 pairs — two bytes per entry, read back with `px[i*2] | (px[i*2+1] << 8)`.

**Save/restore of per-pixel data must restore in REVERSE order.** When multiple adjacent radials (0.5° apart) map to the same display pixel due to integer rounding, each radial appends a new save entry with whatever is currently in `fb`. Restoring forward leaves the pixel at the intermediate blended value from the second-to-last visit. Restoring in reverse (`for i in range(n-1, -1, -1)`) means the earliest save — which holds the true original value — wins. This is the correct fix; forward iteration produces a subtle but catastrophic accumulation of the glow color over time.

**Performance split:** use `@micropython.native` for float trig (one `sin`/`cos` per radial, converted to fixed-point integers), then pass those integers to a `@micropython.viper` inner loop that does pure integer arithmetic with `ptr8` raw buffer access. Float boxing inside a viper loop kills framerate. Module-level integer constants (e.g. `_MAX_TRAIL_PX`) are accessible in viper via `int(CONSTANT)`, but storing them as instance variables (`self._trail_cap`) is safer and equally fast.

**Batch native→viper transitions; keep viper arg counts low.** Calling a viper function in a tight Python loop (e.g. once per trail radial) pays the native→viper transition cost every iteration. Prefer packing the per-iteration inputs into a buffer (native loop) and doing the whole batch in one viper call (see `paint_trail` → `_blend_trail_all_viper`). When a viper function needs many inputs, stash them as instance attributes and read them with `int(self._x)` at the top of the function rather than passing a long argument list — the existing viper functions all take 0–3 args, and that is the proven-safe shape on this port.

**Pack signed fixed-point into unsigned slots with a bias.** `ptr8`/`ptr16` reads are unsigned. To carry a signed fixed-point value (e.g. `sin*2048` in [-2048, 2048]) through a `ptr8` buffer, add a bias on the way in (`+2048`, giving [0, 4096], fits in uint16 LE pairs) and subtract it back inside the viper. See `paint_trail`/`_blend_trail_all_viper`.

**mpremote session chaining:** use `mpremote connect /dev/ttyACM0 cp a :a + cp b :b + run c.py` to upload multiple files and run in a single session. Separate `mpremote` invocations each open/close the port and are slower; if another process holds `/dev/ttyACM0`, use `fuser /dev/ttyACM0` to find and kill it.

**Validating viper without booting the app:** `mpremote ... cp sweep.py :sweep.py + exec "<test>"` runs a quick smoke test. Force a fresh import first (`import sys; [sys.modules.pop(x) for x in [k for k in sys.modules if 'sweep' in k]]`) or `import` returns the cached old module and you silently test stale code. Constructing the object and calling each viper path once at several angles surfaces compile/type/overflow errors immediately.

**`mpremote soft-reset` parks at the REPL — it does NOT run `main.py`.** After a soft-reset, mpremote holds the board in the REPL so `main.py` cannot interfere; to actually cold-boot the app standalone, use `mpremote connect /dev/ttyACM0 reset` (hardware reset). Note that a hardware reset re-enumerates USB-CDC, so `/dev/ttyACM0` may briefly change. To capture serial from a running app, prefer `mpremote exec` (synchronous, captures prints) over opening the raw port with pyserial — pyserial toggles DTR/RTS on open, which can disturb the board.

## Build status & suggested next steps

**Done:**

1. ✅ Renderer MVP — fetch + composite + crop + serve RGB565/JPEG; station database; themes.
2. ✅ MicroPython flashed; REPL over serial verified (ESP32-S3-Zero).
3. ✅ Display bring-up: vendored GC9A01 driver (`gc9a01py.py`) + test pattern; wiring proven on the S3-Zero.
4. ✅ Firmware client loop (`radar.py`): WiFi + `GET /frame?station=KILN&fmt=rgb565` + blit + sleep, tested end-to-end against the renderer.
5. ✅ PPI sweep animation (`sweep.py`): clock-driven radial sweep with anti-aliased line, persistence glow trail (20° behind the sweep, quadratic alpha ramp), dirty-rect band blit.
6. ✅ Provisioning: captive-portal AP (`portal.py`) on first boot; WPA2 passphrase derived from chip ID; settings drawn on display. Config stored in `/config.json`; `secrets.py` retired.
7. ✅ Boot status screen: "Connecting…" → "Connected" with settings URL and SSID; holds ≥20 s or until first frame.
8. ✅ In-radar settings server: `portal.serve()` runs on :80 in a background thread; station list populated as a dropdown from `/stations`; browser redirects back after reboot.
9. ✅ NTP clock overlay: HH:MM at 12 o'clock, 2× scaled (16 px), no background. Baked into `src` once per minute at second 45 so correct time is visible when the sweep crosses 12 o'clock at second 0. `tz_offset` (hours) configurable in the settings form.
10. ✅ Wall-clock sweep alignment: second 0 = 12 o'clock (top); sweep proceeds clockwise; rotation boundary (frame swap) at second 15 (3 o'clock). Sub-second interpolation via `ticks_ms()` boundary tracking for smooth motion.
11. ✅ Sweep smoothness pass: frame cap raised to ~25 fps (`TARGET_MS = 40`); trail glow batched into one viper call per frame (`_blend_trail_all_viper`); AA sweep line moved to a fixed-point viper loop (`_aa_line_viper`, no `sqrt`).
12. ✅ Keep-alive fetch: one TLS handshake at startup, reused across polls; fetch kicked off at second 45 (9 o'clock) and throttled across ~10 s — eliminates the once-per-minute ~700 ms handshake freeze.

**Remaining:**

1. Robustness pass: last-good-frame, status indicator (corner dot: green/yellow/red), watchdog timer.
2. Polish: JPEG transport, OTA. (Backlight dimming is *not* possible on the current display module — its backlight is hardwired on; would require a different module or a hardware mod.)

Enclosure is out of scope here.
