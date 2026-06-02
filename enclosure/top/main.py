import sys
from pathlib import Path

_root = str(Path(__file__).resolve().parents[2])
if _root not in sys.path:
    sys.path.insert(0, _root)

from enclosure.params.main import params
import enclosure.common.main as main
from cadquery import Workplane

def top(p: dict) -> Workplane:
    """Plate sitting on the top lip; flush with the cabinet top face (z = H).
    Extends from y = -D/2 (open-back edge) to y = D/2 - wall - slip_tol (just
    short of the front wall interior). Two screws fix it to the top bosses at
    the front corners; the back edge meets the top edge of the back panel."""
    W, D, H, wall = p["width"], p["depth"], p["height"], p["wall"]
    tol = p["slip_tol"]
    t = p["panel_thickness"]

    plate_w = W - 2 * wall - 2 * tol
    y_lo = -D / 2
    y_hi = D / 2 - wall - tol
    panel = main.box_at(
        x=0, y=(y_lo + y_hi) / 2, z=H - t / 2,
        lx=plate_w, ly=y_hi - y_lo, lz=t,
    )

    # Screw clearance holes at the front-top corners, lined up with the top
    # screw bosses below.
    inset = p["top_screw_boss_inset"]
    screw_r = main.hole_dia(p, p["screw_clearance_target"]) / 2
    xs = [-W / 2 + inset, W / 2 - inset]
    y_screw = D / 2 - wall - inset + 1.0
    for x in xs:
        hole = main.cyl_z(x, y_screw, z_start=H - t - 0.5, radius=screw_r, length=t + 1.0)
        panel = panel.cut(hole)

    return panel


result = top(params)
