import sys
from pathlib import Path

_root = str(Path(__file__).resolve().parents[2])
if _root not in sys.path:
    sys.path.insert(0, _root)

import enclosure.common.main as main
from enclosure.params.main import params
from cadquery import Workplane


def cabinet_shell(p: dict) -> Workplane:
    """4 walls (front + sides + bottom); open at TOP and BACK."""
    W, D, H, wall = p["width"], p["depth"], p["height"], p["wall"]
    outer = Workplane("XY").box(W, D, H, centered=(True, True, False))
    # Cavity spans:
    #   X: full interior width (W - 2*wall), centered.
    #   Y: from back exterior (-D/2) to interior of front wall (D/2 - wall).
    #   Z: from interior of bottom wall (z = wall) to past the cabinet top
    #      (z = H + 1) so no top wall exists.
    cavity_y_len = D - wall
    cavity_y_center = -wall / 2
    cavity_z_lo = wall
    cavity_z_hi = H + 1.0
    cavity = main.box_at(
        x=0,
        y=cavity_y_center,
        z=(cavity_z_lo + cavity_z_hi) / 2,
        lx=W - 2 * wall,
        ly=cavity_y_len,
        lz=cavity_z_hi - cavity_z_lo,
    )
    return outer.cut(cavity)