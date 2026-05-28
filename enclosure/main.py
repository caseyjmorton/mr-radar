# /// script
# requires-python = ">=3.11,<3.13"
# dependencies = ["cadquery>=2.4,<3"]
# ///
"""mr-radar enclosure -- parametric 3D-printable shell.

A nod to the Mr. Radar machine from Spaceballs: rectangular cabinet, large
window for the round display near the top, decorative button rows below,
a small column of LED-style bumps next to the screen, and MR. RADAR
embossed across the top.

Three-part assembly so every piece prints cleanly on a 0.6 mm nozzle FDM:

  body  - 4 walls (front, left, right, bottom). Open at both TOP and BACK so
          the body prints upright (bottom on the bed) with no bridges. Front
          decor protrudes horizontally; small features print fine without
          supports on a vertical face.
  back  - slip-fit rear panel with a snap-fit shelf for the dev board and a
          USB-C cutout. Prints flat.
  top   - slip-fit top panel. Prints flat.

Each piece is screwed in with M2 self-tapping screws into integrated bosses.

Designed around:
  - 1.28" GC9A01 round TFT: 38x45.5 mm PCB, 38.1 mm display face, 32.4 mm
    active LCD, two PCB mount holes on the bottom breakout tab.
  - Waveshare ESP32-S3-Zero, ~23.8x18 mm, USB-C on one short edge, no PCB
    mounting holes (snap-fit shelf only).

Coordinate convention:
  x = width  (cabinet left/right, centered on 0)
  y = depth  (front of cabinet is +y, back is -y; front face at y = +depth/2)
  z = height (cabinet bottom at z = 0, top at z = height)

All dimensions are millimetres. Tune PARAMS at the top; geometry is split
into small functions so you can replace any piece without rewriting the rest.

Usage:
  uv run enclosure/build.py
  # or:
  pip install -r enclosure/requirements.txt && python enclosure/build.py
"""

from __future__ import annotations

from pathlib import Path
import sys

_root = str(Path(__file__).resolve().parents[1])
if _root not in sys.path:
    sys.path.insert(0, _root)

from cadquery import exporters
from enclosure.params.main import params
from enclosure.top.main import top
from enclosure.back.main import back
from enclosure.body.main import body

def main() -> int:
    out_dir = Path(params["output_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"mr-radar enclosure v{params['version']}")
    print(f"  cabinet: {params['width']} x {params['height']} x {params['depth']} mm")
    print(f"  output:  {out_dir}")

    parts = [
        ("body", body),
        ("back", back),
        ("top",  top),
    ]
    for suffix, builder in parts:
        solid = builder(params)
        out_path = out_dir / f"mr-radar-enclosure-v{params['version']}-{suffix}.stl"
        exporters.export(solid, str(out_path))
        print(f"  wrote   {out_path.name}  ({out_path.stat().st_size // 1024} KiB)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
