# Enclosure

Parametric 3D-printable shell for mr-radar. A nod to the Mr. Radar machine
from *Spaceballs* — rectangular cabinet, round display window near the top,
decorative button rows below, a column of LED-style bumps next to the screen,
and `MR. RADAR` embossed across the top.

The cabinet is a **3-part assembly** so every piece prints with no support
material on a 0.6 mm-nozzle FDM:

| File | What it is |
| --- | --- |
| `mr-radar-enclosure-v0.1.0-body.stl` | 4-walled shell (front, left, right, bottom) — open at TOP and BACK. Holds the integrated display mount posts, screw bosses, and all front-face decor. |
| `mr-radar-enclosure-v0.1.0-back.stl` | Slip-fit rear panel with the dev board snap-fit shelf and USB-C cutout. |
| `mr-radar-enclosure-v0.1.0-top.stl` | Slip-fit top panel that caps the open top. |

The body prints upright with no bridges (open top), the back and top panels
print flat. Four M2 self-tapping screws hold the assembly together: two into
the back-bottom corners (back panel) and two into the front-top corners
(top panel).

## Render

The build script uses [CadQuery](https://cadquery.readthedocs.io/).

```bash
# uv handles the cadquery install via PEP 723 inline metadata:
uv run enclosure/build.py

# fallback without uv:
pip install -r enclosure/requirements.txt
python enclosure/build.py
```

Outputs land in `enclosure/build/`.

## Hardware target

Designed around:

- **Waveshare 1.28" GC9A01 round TFT.** 38 × 45.5 mm PCB, 38.1 mm display face,
  32.4 mm active LCD, two PCB mount holes on the bottom breakout tab. The
  display face is held flush against the inside of the cabinet front; two
  posts behind the front wall accept M2 self-tapping screws through the PCB
  mount holes. See `firmware/WIRING.md` for the full module dimensions.
- **Waveshare ESP32-S3-Zero.** ~23.8 × 18 mm board, USB-C on one short edge,
  no PCB mounting holes. Retained by a snap-fit channel on the back panel;
  the USB-C connector pokes through the panel's cutout for access without
  opening the cabinet.

## Assembly

1. Drop the dev board into the snap-fit channel on the **back panel** —
   USB-C connector pointed at the panel's cutout.
2. Slide the **back panel** into the cabinet's rear opening; the 3-sided
   inner lip (left, right, bottom) catches it. Two M2 screws into the
   back-bottom bosses.
3. Mount the GC9A01 display PCB to the two internal posts behind the front
   wall (M2 self-tapping screws through the PCB's mount holes). The display
   face sits flush against the inside of the round front-face window.
4. Wire the display to the dev board per `firmware/WIRING.md`.
5. Drop the **top panel** into the top opening; the 3-sided inner lip
   (left, right, front) catches it. Two M2 screws into the top-front bosses.
   The back edge of the top panel meets the top edge of the back panel at the
   back-top corner.

## Print settings

The geometry has print compensation baked in for the maintainer's printer:

| | |
| --- | --- |
| Nozzle | 0.6 mm |
| Layer height | 0.3 mm |
| Hole oversize | +0.5 mm Ø (added to every functional hole) |
| Slip-fit tolerance | 0.4 mm per side |

All "target" diameters in `PARAMS` are the **printed** result we want; the
geometry adds `hole_oversize` before cutting. To retune for a finer nozzle,
adjust `PARAMS["hole_oversize"]` and `PARAMS["slip_tol"]` at the top of
`build.py` and re-render — every functional hole picks up the change.

### Recommended print orientation

- **body**: print **upright**, cabinet bottom on the bed. The 4 walls extrude
  vertically; both top and back are open, so there are no bridges. Front-face
  decor (buttons, LEDs, MR. RADAR) protrudes horizontally; at 1.5 mm / 0.9 mm
  the overhangs are well within what a slicer can print clean.
- **back**: print flat, back-exterior side down on the bed. Snap-fit shelf
  and USB cutout face up. No supports.
- **top**: print flat, top-exterior side down on the bed. No supports.

## Tweaking the geometry

Every dimension lives in the `PARAMS` dict at the top of `build.py`. The
geometry is split into small functions — `_cabinet_shell`, `_display_window`,
`_back_lip` / `_top_lip`, `_back_screw_bosses` / `_top_screw_bosses`,
`_display_mount_posts`, `_front_decor`, etc. — so you can rewrite any one
piece without touching the rest.

A few likely tuning points after the first print:

- `display_post_spacing` — the GC9A01 mount-hole spacing is estimated from
  the drawing; measure your unit and update.
- `display_post_z_offset_below_center` — same: the mount holes sit on the
  bottom breakout tab, so the exact offset depends on your PCB.
- `board_w` / `board_h` — measure your ESP32-S3-Zero, add a hair of clearance.
- `button_cols` / `button_rows` / `button_col_pitch` — pure aesthetics, change
  freely.

## Future

A tag-driven `release-enclosure.yml` workflow will run this script in CI on
`enclosure-v*` tags and attach the STLs to a GitHub Release. Not wired yet;
see the project's release pipeline plan.
