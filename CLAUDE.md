# CLAUDE.md

Guidance for AI agents (Claude Code) working in this repository. Read this fully before making changes.

## What this project is

**mr-radar** is an open-source weather radar display. An ESP32-C3 drives a round 240x240 TFT and shows live NEXRAD precipitation radar composited over a base map, centered on the owner's nearest radar station. The name is a nod to the radar scene in Mel Brooks' *Spaceballs* ("We ain't found shit!").

The defining product constraint: **a person must be able to flash the firmware, enter their WiFi credentials and their nearest NEXRAD station ID, and have a working device with no other infrastructure.** The firmware must never depend on a server that only the maintainer runs. Protect this constraint in every decision.

## Architecture (read this before writing any code)

The ESP32-C3 cannot decode or composite map tiles — it has ~400KB RAM and no PNG decoder, and a single decoded zoom-7 tile is ~512KB. Fetching tiles directly from providers would also violate OpenStreetMap's tile usage policy when fanned out across many devices. Therefore the work is split:

```
ESP32-C3 firmware  --HTTPS GET-->  stateless renderer  --tiles-->  RainViewer + OSM
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
├── firmware/    # MicroPython for the ESP32-C3. This is what people flash.
├── renderer/    # Stateless image service (Node.js + sharp). Optionally self-hosted.
├── enclosure/   # OpenSCAD -> STL. NOT YET STARTED. Do not create files here
│                #   unless explicitly asked; it is handled in a separate effort.
├── CLAUDE.md
└── README.md
```

Keep firmware and renderer concerns strictly separated. They communicate only over the HTTP contract described below. Do not let renderer dependencies (sharp, Node.js, etc.) leak into firmware reasoning, and do not assume firmware capabilities (a real OS, gigabytes of RAM) when writing firmware.

## Hardware target

- **MCU:** ESP32-C3 "super mini" dev board. Single-core RISC-V, ~400KB usable RAM, native USB-CDC serial.
- **Display:** 240×240 round TFT, GC9A01 controller, SPI (write-only, no MISO). 1.28" diameter.
- **Default pin map** (assign explicitly in code; do not trust board silkscreen):
  | Display | GPIO |
  |---|---|
  | SCK | 4 |
  | MOSI | 5 |
  | DC | 6 |
  | CS | 7 |
  | RST | 8 |
  | BLK | 3V3 (or a GPIO for dimming) |

  Treat the pin map as configuration, not hard-coded magic numbers.

### ESP32-C3 flashing facts that bite people
- Flash offset is **`0x0`**, NOT `0x1000` (that's the classic ESP32). Getting this wrong produces a board that won't boot.
- Erase before flashing: `esptool.py --chip esp32c3 erase_flash`.
- If auto-reset into download mode fails on a clone: hold BOOT, tap RST, release BOOT.
- Native USB-CDC can be flaky on clones; serial drops are usually the cause, not the code.

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

## Robustness expectations (non-negotiable for both halves)

- **Firmware:** never hard-fault to a black screen on a transient error. Wrap the network loop in try/except, keep a "last known good frame," show a small status indicator (e.g. a corner dot: green=fresh, yellow=stale, red=offline), and use a watchdog so a hang self-recovers. WiFi creds, station ID, and endpoint URL are provisioned (e.g. captive-portal or config file), not hard-coded.
- **Renderer:** stateless, no database; cache in memory only. Tolerate upstream outages and partial data. Be a polite upstream client (caching, backoff, User-Agent). Must run identically on the public instance, a free-tier PaaS, or a Raspberry Pi.

## Working conventions for agents

- **Confirm before scaffolding large structures.** Propose the file/module layout and get agreement before generating many files.
- **Match the language to the half.** Firmware is MicroPython (assume no CPython-only stdlib; memory is scarce; prefer `const`, preallocated buffers, and streaming over large allocations). Renderer is Node.js ≥20 with `sharp` and Express.
- **Touch the enclosure directory only when explicitly asked.** It is intentionally deferred.
- **Keep the contract in sync.** Any HTTP-contract change updates firmware, renderer, and this document together.
- **Cite the constraints, don't relitigate them.** The architecture split exists for hard reasons (device RAM, no on-device PNG decode, provider ToS). Don't propose on-device compositing or homelab-dependence without explicitly raising it as a constraint change first.
- **Prefer small, reviewable changes.** This is hardware-adjacent; a bad firmware change costs a reflash. Favor incremental, testable steps.
- **Validate hardware assumptions cheaply.** When touching display code, prefer a test-pattern path that proves wiring before layering on network complexity.

## Build status & suggested next steps

**Done:**

1. ✅ Renderer MVP — fetch + composite + crop + serve RGB565/JPEG; station database; themes.

**Remaining:**

1. Flash MicroPython; verify REPL over serial.
2. Display bring-up: GC9A01 driver + a test pattern. Prove wiring before anything networked.
3. Firmware client loop: WiFi + `GET /frame?station=KILN&fmt=rgb565` + blit + sleep.
4. Robustness pass: last-good-frame, status indicator, watchdog, provisioning.
5. Polish: JPEG transport, backlight dimming, OTA, animated loop (renderer-driven).

Enclosure is out of scope here.
