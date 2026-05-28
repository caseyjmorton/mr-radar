import sys
from pathlib import Path

_root = str(Path(__file__).resolve().parents[2])
if _root not in sys.path:
    sys.path.insert(0, _root)

import enclosure.common.main as main
from enclosure.params.main import params
from cadquery import Workplane

def top_lip(p: dict) -> Workplane:
    """3-sided frame (left + right + front) inside the top opening, sitting
    immediately BELOW the top panel (z = H - panel_thickness and downward)."""
    W, D, H, wall = p["width"], p["depth"], p["height"], p["wall"]
    lip_d = p["top_lip_depth"]
    lip_t = p["lip_thickness"]
    t = p["panel_thickness"]
    z_hi = H - t                              # below the panel
    z_lo = z_hi - lip_d
    z_center = (z_lo + z_hi) / 2
    # Side rails span the full interior depth (open back).
    y_lo = -D / 2
    y_hi = D / 2 - wall
    side_y_center = (y_lo + y_hi) / 2
    side_y_len = y_hi - y_lo
    front = main.box_at(
        x=0, y=D / 2 - wall - lip_t / 2, z=z_center,
        lx=W - 2 * wall, ly=lip_t, lz=lip_d,
    )
    left = main.box_at(
        x=-W / 2 + wall + lip_t / 2, y=side_y_center, z=z_center,
        lx=lip_t, ly=side_y_len, lz=lip_d,
    )
    right = main.box_at(
        x=W / 2 - wall - lip_t / 2, y=side_y_center, z=z_center,
        lx=lip_t, ly=side_y_len, lz=lip_d,
    )
    return main.combine([front, left, right])

result = top_lip(params)