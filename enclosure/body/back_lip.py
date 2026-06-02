import sys
from pathlib import Path

_root = str(Path(__file__).resolve().parents[2])
if _root not in sys.path:
    sys.path.insert(0, _root)

import enclosure.common.main as main
from enclosure.params.main import params
from cadquery import Workplane


def back_lip(p: dict) -> Workplane:
    """3-sided frame (left + right + bottom) inside the back opening, sitting
    immediately BEHIND the back panel (y = -D/2 + panel_thickness onward).
    Acts as a backstop the panel seats against; the screws hold it firm."""
    W, D, H, wall = p["width"], p["depth"], p["height"], p["wall"]
    lip_d = p["back_lip_depth"]
    lip_t = p["lip_thickness"]
    t = p["panel_thickness"]
    y_lo = -D / 2 + t                         # behind the panel
    y_hi = y_lo + lip_d
    y_center = (y_lo + y_hi) / 2
    # Vertical span of side rails: from interior of bottom wall up to top of
    # the cabinet (overlap with top lip on the side walls is harmless).
    z_side_lo = wall
    z_side_hi = H
    side_z_center = (z_side_lo + z_side_hi) / 2
    side_z_len = z_side_hi - z_side_lo
    bottom = main.box_at(
        x=0, y=y_center, z=wall + lip_t / 2,
        lx=W - 2 * wall, ly=lip_d, lz=lip_t,
    )
    left = main.box_at(
        x=-W / 2 + wall + lip_t / 2, y=y_center, z=side_z_center,
        lx=lip_t, ly=lip_d, lz=side_z_len,
    )
    right = main.box_at(
        x=W / 2 - wall - lip_t / 2, y=y_center, z=side_z_center,
        lx=lip_t, ly=lip_d, lz=side_z_len,
    )
    return main.combine([bottom, left, right])

result = back_lip(params)