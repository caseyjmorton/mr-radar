import sys
from pathlib import Path

_root = str(Path(__file__).resolve().parents[2])
if _root not in sys.path:
    sys.path.insert(0, _root)

import enclosure.common.main as main
from enclosure.params.main import params
from cadquery import Workplane

def back(p: dict) -> Workplane:
    """Plate that fits the rear opening, plus snap-fit board shelf + USB cutout."""
    W, D, H, wall = p["width"], p["depth"], p["height"], p["wall"]
    tol = p["slip_tol"]
    t = p["panel_thickness"]
    top_t = p["panel_thickness"]   # top panel thickness — the back panel's top edge
                                    # meets the top panel's back edge at this Z.

    # Plate sits IN the rear opening. Width slip-fits between the side walls;
    # height spans from above the bottom wall to just below the top panel.
    plate_w = W - 2 * wall - 2 * tol
    plate_z_lo = wall + tol
    plate_z_hi = H - top_t                       # leave room for the top panel above
    plate_h = plate_z_hi - plate_z_lo
    plate_z_center = (plate_z_lo + plate_z_hi) / 2
    panel = main.box_at(
        x=0, y=-D / 2 + t / 2, z=plate_z_center,
        lx=plate_w, ly=t, lz=plate_h,
    )

    # Screw clearance holes through the panel, lined up with the body's
    # back-bottom bosses (2 screws only).
    inset = p["back_screw_boss_inset"]
    screw_r = main.hole_dia(p, p["screw_clearance_target"]) / 2
    xs = [-W / 2 + inset, W / 2 - inset]
    z_screw = wall + inset - 1.0
    for x in xs:
        hole = main.cyl_y(x, z_screw, y_start=-D / 2 - 0.5, radius=screw_r, length=t + 1.0)
        panel = panel.cut(hole)

    # USB-C cutout aligned with the board on the cabinet floor. Board sits
    # at z = wall + board_floor_height with its top at +board_thickness; the
    # USB-C connector's center is `board_usb_z_above_top` above the board top.
    usb_center_z = (
        wall
        + p["board_floor_height"]
        + p["board_thickness"]
        + p["board_usb_z_above_top"]
    )
    usb_w = p["board_usb_cutout_w"] + p["hole_oversize"]
    usb_h = p["board_usb_cutout_h"] + p["hole_oversize"]
    usb = main.box_at(
        x=0, y=-D / 2 + t / 2, z=usb_center_z,
        lx=usb_w, ly=t + 1.0, lz=usb_h,
    )
    panel = panel.cut(usb)

    return panel

result = back(params)
