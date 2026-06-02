import sys
from pathlib import Path

_root = str(Path(__file__).resolve().parents[2])
if _root not in sys.path:
    sys.path.insert(0, _root)

import enclosure.common.main as main
from enclosure.params.main import params
from cadquery import Workplane


def display_window(p: dict) -> Workplane:
    """Cylinder cutting through the front wall for the round display face."""
    D, H, wall = p["depth"], p["height"], p["wall"]
    z = H - p["display_center_z_from_top"]
    target_dia = p["display_face_dia"] + p["display_clearance"]
    r = main.hole_dia(p, target_dia) / 2
    # Start the cutting cylinder just outside the front face and run it through
    # the wall + a margin so the cut is unambiguous.
    margin = 1.0
    return main.cyl_y(
        x=0, z=z,
        y_start=D / 2 - wall - margin,
        radius=r,
        length=wall + 2 * margin,
    )

result = display_window(params)