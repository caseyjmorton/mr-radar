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

import sys
from pathlib import Path

import cadquery as cq

sys.path.insert(0, str(Path(__file__).parent))
from version import __version__  # noqa: E402

PARAMS = {
    # --- Print compensation (FDM, 0.6 mm nozzle, 0.3 mm layer height) --------
    # Holes print smaller than designed because the slicer's inner-perimeter
    # path is inset by ~nozzle_width/2 from the model surface, plus arc-
    # resolution rounding. With a 0.6 mm nozzle this loss is ~0.5 mm in
    # diameter; all functional holes below have it pre-added so the *printed*
    # hole hits the intended size. Retune for a different nozzle.
    "hole_oversize":  0.5,
    "slip_tol":       0.4,   # XY clearance for slip-fit mating surfaces
    "nozzle_dia":     0.6,   # informational; not consumed by geometry
    "layer_height":   0.3,   # informational; not consumed by geometry

    # Cabinet outer shell. 2.4 mm wall = 4 perimeters of a 0.6 nozzle = solid.
    "width":  80.0,
    "height": 110.0,
    "depth":  45.0,
    "wall":   2.4,

    # GC9A01 round display
    "display_face_dia":     38.1,
    "display_window_dia":   35.6,    # bright/backlit area; informational
    "display_clearance":    0.4,     # design clearance; hole_oversize is added on top
    "display_pcb_w":        38.0,
    "display_pcb_h":        45.5,
    "display_center_z_from_top": 38.0,  # screen center below cabinet top
    "display_post_dia":         6.0,    # post OD
    "display_post_pilot_target": 1.5,   # printed M2 self-tap pilot; geometry adds oversize
    "display_post_spacing":     28.0,   # estimated; tune after first print
    "display_post_z_offset_below_center": 22.0,  # mount holes are on the bottom tab

    # Decorative buttons on front face (raised discs)
    "button_dia":      6.0,            # 1.5 mm taller than 4 nozzle widths
    "button_height":   1.5,            # 5 layers at 0.3 mm
    "button_rows":     2,
    "button_cols":     6,
    "button_row_pitch": 9.0,
    "button_col_pitch": 9.5,
    "button_panel_center_z_from_top": 78.0,

    # LED indicator column (raised dots to the right of the display)
    "led_dia":     3.0,                # 5 nozzle widths; smaller dots smear at 0.6 mm
    "led_height":  0.9,                # 3 layers
    "led_count":   10,
    "led_pitch":   3.8,
    "led_column_x_offset_from_center": 28.0,
    "led_column_center_z_from_top": 38.0,

    # MR. RADAR label. font_size big enough that letter strokes are >= 2 nozzle
    # widths; smaller and the slicer drops the thin strokes entirely.
    "label_text":      "MR. RADAR",
    "label_font_size": 8.0,
    "label_extrude":   0.9,            # 3 layers
    "label_z_from_top": 12.0,

    # Removable panels (back + top). Both panels are the same thickness and
    # share the M2 screw geometry. All "_target" diameters are the printed
    # result we want; the geometry adds hole_oversize before cutting.
    "panel_thickness":              2.4,
    "back_lip_depth":               3.0,
    "top_lip_depth":                3.0,
    "lip_thickness":                1.8,    # how far the lip protrudes from the wall
    "screw_clearance_target":       2.4,    # M2 clearance through a panel
    "screw_boss_dia":               6.5,    # solid boss OD inside the cabinet
    "screw_boss_pilot_target":      1.5,    # M2 self-tap pilot in a boss
    "back_screw_boss_inset":        6.0,    # X-corner inset for back-bottom bosses
    "top_screw_boss_inset":         6.0,    # X-corner inset for top-front bosses

    # Dev board snap-fit channel on the back panel (Waveshare ESP32-S3-Zero).
    # Board dims include a small inflate so the slot accommodates real boards.
    "board_w":             24.0,
    "board_h":             18.5,
    "board_thickness":     1.6,
    "board_floor_height":  1.4,
    "board_tab_height":    2.0,
    "board_tab_width":     3.0,
    "board_z_center_from_top": 92.0,
    "board_usb_cutout_w":  10.5,       # USB-C body ~9 mm + margin, then -0.5 print = 10
    "board_usb_cutout_h":  5.5,        # USB-C body ~3.3 mm + margin
    "board_usb_protrude":  1.5,

    # Output
    "version":    __version__,
    "output_dir": str(Path(__file__).parent / "build"),
}


def _hole_dia(p: dict, designed: float) -> float:
    """Add per-print hole compensation to a designed diameter."""
    return designed + p["hole_oversize"]


# ----- placement helpers ---------------------------------------------------
# Everything is positioned by world coordinates to avoid the XZ-plane normal
# direction confusion that bites with `Workplane("XZ").workplane(offset=...)`.

def _cyl_y(x: float, z: float, y_start: float, radius: float, length: float) -> cq.Workplane:
    """Cylinder of given radius and length, axis along +Y, base at (x, y_start, z)."""
    return (
        cq.Workplane("XY")
        .cylinder(length, radius, centered=(True, True, False))
        .rotate((0, 0, 0), (1, 0, 0), -90)        # +Z -> +Y
        .translate((x, y_start, z))
    )


def _cyl_z(x: float, y: float, z_start: float, radius: float, length: float) -> cq.Workplane:
    """Cylinder of given radius and length, axis along +Z, base at (x, y, z_start)."""
    return (
        cq.Workplane("XY")
        .cylinder(length, radius, centered=(True, True, False))
        .translate((x, y, z_start))
    )


def _box_at(x: float, y: float, z: float, lx: float, ly: float, lz: float) -> cq.Workplane:
    """Box of full extents (lx, ly, lz), centered at world (x, y, z)."""
    return (
        cq.Workplane("XY")
        .box(lx, ly, lz, centered=(True, True, True))
        .translate((x, y, z))
    )


def _combine(parts: list[cq.Workplane]) -> cq.Workplane:
    """Union a non-empty list of solids."""
    out = parts[0]
    for p in parts[1:]:
        out = out.union(p)
    return out


# ----- subassemblies -------------------------------------------------------

def _cabinet_shell(p: dict) -> cq.Workplane:
    """4 walls (front + sides + bottom); open at TOP and BACK."""
    W, D, H, wall = p["width"], p["depth"], p["height"], p["wall"]
    outer = cq.Workplane("XY").box(W, D, H, centered=(True, True, False))
    # Cavity spans:
    #   X: full interior width (W - 2*wall), centered.
    #   Y: from back exterior (-D/2) to interior of front wall (D/2 - wall).
    #   Z: from interior of bottom wall (z = wall) to past the cabinet top
    #      (z = H + 1) so no top wall exists.
    cavity_y_len = D - wall
    cavity_y_center = -wall / 2
    cavity_z_lo = wall
    cavity_z_hi = H + 1.0
    cavity = _box_at(
        x=0,
        y=cavity_y_center,
        z=(cavity_z_lo + cavity_z_hi) / 2,
        lx=W - 2 * wall,
        ly=cavity_y_len,
        lz=cavity_z_hi - cavity_z_lo,
    )
    return outer.cut(cavity)


def _display_window(p: dict) -> cq.Workplane:
    """Cylinder cutting through the front wall for the round display face."""
    D, H, wall = p["depth"], p["height"], p["wall"]
    z = H - p["display_center_z_from_top"]
    target_dia = p["display_face_dia"] + p["display_clearance"]
    r = _hole_dia(p, target_dia) / 2
    # Start the cutting cylinder just outside the front face and run it through
    # the wall + a margin so the cut is unambiguous.
    margin = 1.0
    return _cyl_y(
        x=0, z=z,
        y_start=D / 2 - wall - margin,
        radius=r,
        length=wall + 2 * margin,
    )


def _back_screw_bosses(p: dict) -> cq.Workplane:
    """Two posts at the back-BOTTOM corners. They start just BEHIND the back
    panel (at y = -D/2 + panel_thickness) so the panel and boss don't fight
    for the same Y space; the screw passes through the panel's clearance hole
    and bites into the boss."""
    W, D, wall = p["width"], p["depth"], p["wall"]
    inset = p["back_screw_boss_inset"]
    t = p["panel_thickness"]
    boss_r = p["screw_boss_dia"] / 2
    pilot_r = _hole_dia(p, p["screw_boss_pilot_target"]) / 2
    boss_h = p["back_lip_depth"] + 6.0
    y_start = -D / 2 + t
    xs = [-W / 2 + inset, W / 2 - inset]
    z = wall + inset - 1.0     # sit on top of bottom wall, slightly tucked in
    parts: list[cq.Workplane] = []
    for x in xs:
        boss = _cyl_y(x, z, y_start=y_start, radius=boss_r, length=boss_h)
        # Pilot extends from the panel face (so the screw threads start biting
        # immediately once they exit the panel) through and past the boss.
        pilot = _cyl_y(x, z, y_start=-D / 2 - 0.5, radius=pilot_r, length=t + boss_h + 1.0)
        parts.append(boss.cut(pilot))
    return _combine(parts)


def _top_screw_bosses(p: dict) -> cq.Workplane:
    """Two posts at the top-FRONT corners. They start just BELOW the top
    panel (at z = H - panel_thickness) so the panel and boss don't share Z."""
    W, D, H, wall = p["width"], p["depth"], p["height"], p["wall"]
    inset = p["top_screw_boss_inset"]
    t = p["panel_thickness"]
    boss_r = p["screw_boss_dia"] / 2
    pilot_r = _hole_dia(p, p["screw_boss_pilot_target"]) / 2
    boss_h = p["top_lip_depth"] + 6.0
    z_top_of_boss = H - t
    xs = [-W / 2 + inset, W / 2 - inset]
    y = D / 2 - wall - inset + 1.0
    parts: list[cq.Workplane] = []
    for x in xs:
        boss = _cyl_z(x, y, z_start=z_top_of_boss - boss_h, radius=boss_r, length=boss_h)
        pilot = _cyl_z(x, y, z_start=z_top_of_boss - boss_h - 0.5, radius=pilot_r,
                       length=t + boss_h + 1.0)
        parts.append(boss.cut(pilot))
    return _combine(parts)


def _back_lip(p: dict) -> cq.Workplane:
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
    bottom = _box_at(
        x=0, y=y_center, z=wall + lip_t / 2,
        lx=W - 2 * wall, ly=lip_d, lz=lip_t,
    )
    left = _box_at(
        x=-W / 2 + wall + lip_t / 2, y=y_center, z=side_z_center,
        lx=lip_t, ly=lip_d, lz=side_z_len,
    )
    right = _box_at(
        x=W / 2 - wall - lip_t / 2, y=y_center, z=side_z_center,
        lx=lip_t, ly=lip_d, lz=side_z_len,
    )
    return _combine([bottom, left, right])


def _top_lip(p: dict) -> cq.Workplane:
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
    front = _box_at(
        x=0, y=D / 2 - wall - lip_t / 2, z=z_center,
        lx=W - 2 * wall, ly=lip_t, lz=lip_d,
    )
    left = _box_at(
        x=-W / 2 + wall + lip_t / 2, y=side_y_center, z=z_center,
        lx=lip_t, ly=side_y_len, lz=lip_d,
    )
    right = _box_at(
        x=W / 2 - wall - lip_t / 2, y=side_y_center, z=z_center,
        lx=lip_t, ly=side_y_len, lz=lip_d,
    )
    return _combine([front, left, right])


def _display_mount_posts(p: dict) -> cq.Workplane:
    """Two posts behind the front wall to screw the GC9A01 PCB to."""
    D, H, wall = p["depth"], p["height"], p["wall"]
    spacing = p["display_post_spacing"]
    post_r = p["display_post_dia"] / 2
    pilot_r = _hole_dia(p, p["display_post_pilot_target"]) / 2
    post_h = 4.0
    z = H - p["display_center_z_from_top"] - p["display_post_z_offset_below_center"]
    # Posts attach to the inside of the front wall and protrude into the cavity.
    # Base of the post is at y = D/2 - wall (interior surface of front wall);
    # tip is at y = D/2 - wall - post_h (deeper into the cavity, in -Y).
    y_tip = D / 2 - wall - post_h
    parts: list[cq.Workplane] = []
    for x in (-spacing / 2, spacing / 2):
        post = _cyl_y(x, z, y_start=y_tip, radius=post_r, length=post_h)
        pilot = _cyl_y(x, z, y_start=y_tip - 0.1, radius=pilot_r, length=post_h + 0.2)
        parts.append(post.cut(pilot))
    return _combine(parts)


def _front_decor(p: dict) -> cq.Workplane:
    """Buttons + LEDs + MR. RADAR label, all raised outward from the front face."""
    D, H = p["depth"], p["height"]
    parts: list[cq.Workplane] = []

    # Button grid
    rows, cols = p["button_rows"], p["button_cols"]
    rp, cp = p["button_row_pitch"], p["button_col_pitch"]
    btn_center_z = H - p["button_panel_center_z_from_top"]
    btn_r = p["button_dia"] / 2
    btn_h = p["button_height"]
    for r in range(rows):
        z = btn_center_z + (r - (rows - 1) / 2) * rp
        for c in range(cols):
            x = (c - (cols - 1) / 2) * cp
            parts.append(_cyl_y(x, z, y_start=D / 2, radius=btn_r, length=btn_h))

    # LED column
    led_x = p["led_column_x_offset_from_center"]
    led_center_z = H - p["led_column_center_z_from_top"]
    led_r = p["led_dia"] / 2
    led_h = p["led_height"]
    led_n = p["led_count"]
    led_p = p["led_pitch"]
    for i in range(led_n):
        z = led_center_z + (i - (led_n - 1) / 2) * led_p
        parts.append(_cyl_y(led_x, z, y_start=D / 2, radius=led_r, length=led_h))

    # MR. RADAR label: extrude on the XZ plane (normal -Y, so extrude(positive)
    # goes -Y); we want it raised in +Y from the front face, so we extrude in
    # the natural direction and then translate to land on the outside of the
    # front face.
    label_z = H - p["label_z_from_top"]
    label_extrude = p["label_extrude"]
    label = (
        cq.Workplane("XZ")
        .center(0, label_z)
        .text(
            p["label_text"],
            p["label_font_size"],
            label_extrude,                 # solid extends in -Y by label_extrude
            halign="center",
            valign="center",
        )
        # Move so the bottom of the text sits on the front face (y = D/2).
        .translate((0, D / 2 + label_extrude, 0))
    )
    parts.append(label)

    return _combine(parts)


def build_body(p: dict) -> cq.Workplane:
    body = _cabinet_shell(p)
    body = body.cut(_display_window(p))
    body = body.union(_back_lip(p))
    body = body.union(_top_lip(p))
    body = body.union(_back_screw_bosses(p))
    body = body.union(_top_screw_bosses(p))
    body = body.union(_display_mount_posts(p))
    body = body.union(_front_decor(p))
    return body


def build_back_panel(p: dict) -> cq.Workplane:
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
    panel = _box_at(
        x=0, y=-D / 2 + t / 2, z=plate_z_center,
        lx=plate_w, ly=t, lz=plate_h,
    )

    # Screw clearance holes through the panel, lined up with the body's
    # back-bottom bosses (2 screws only).
    inset = p["back_screw_boss_inset"]
    screw_r = _hole_dia(p, p["screw_clearance_target"]) / 2
    xs = [-W / 2 + inset, W / 2 - inset]
    z_screw = wall + inset - 1.0
    for x in xs:
        hole = _cyl_y(x, z_screw, y_start=-D / 2 - 0.5, radius=screw_r, length=t + 1.0)
        panel = panel.cut(hole)

    # USB-C cutout. Slot punched through the panel at the dev board's Y plane.
    board_z = H - p["board_z_center_from_top"]
    usb_w = p["board_usb_cutout_w"] + p["hole_oversize"]
    usb_h = p["board_usb_cutout_h"] + p["hole_oversize"]
    usb = _box_at(
        x=0, y=-D / 2 + t / 2, z=board_z,
        lx=usb_w, ly=t + 1.0, lz=usb_h,
    )
    panel = panel.cut(usb)

    # Snap-fit shelf for the ESP32-S3-Zero. Board sits flat against the inside
    # of the panel; a low rim around its footprint locates it laterally, and two
    # overhanging tabs hold it down. USB-C points OUT through the panel cutout.
    bw, bh, bt = p["board_w"], p["board_h"], p["board_thickness"]
    floor_h = p["board_floor_height"]
    tab_h = p["board_tab_height"]
    tab_w = p["board_tab_width"]
    snap_clearance = p["slip_tol"]

    # Floor: solid pad on the inside (+Y face) of the panel, then we punch a
    # central hole so the board sits on a rim and the antenna has airflow.
    floor_y_start = -D / 2 + t                          # inside face of panel
    floor_outer_w = bw + 2 * snap_clearance
    floor_outer_h = bh + 2 * snap_clearance
    floor = _box_at(
        x=0, y=floor_y_start + floor_h / 2, z=board_z,
        lx=floor_outer_w, ly=floor_h, lz=floor_outer_h,
    )
    floor_hollow = _box_at(
        x=0, y=floor_y_start + floor_h / 2, z=board_z,
        lx=max(floor_outer_w - 4.0, 0.1),
        ly=floor_h + 0.2,
        lz=max(floor_outer_h - 4.0, 0.1),
    )
    floor = floor.cut(floor_hollow)

    # Retention tabs flank the board's long edges. Each tab is a thin upright
    # whose top half cantilevers inward over the board to clamp it in place.
    tab_post_y_thickness = bt + 0.4                       # vertical section flush w/ board side
    tab_x = bw / 2 + snap_clearance + tab_w / 2           # center of tab in X
    tab_y_center = floor_y_start + floor_h + tab_post_y_thickness / 2

    tabs: list[cq.Workplane] = []
    for x_sign in (-1, 1):
        # Vertical post next to the board edge
        post = _box_at(
            x=x_sign * tab_x, y=tab_y_center, z=board_z,
            lx=tab_w, ly=tab_post_y_thickness, lz=bh - 2.0,
        )
        # Overhanging cap that sticks INWARD over the top of the board
        cap_x_overlap = 1.0
        cap_lx = tab_w + cap_x_overlap
        cap_x_center = x_sign * (tab_x - cap_x_overlap / 2)
        cap = _box_at(
            x=cap_x_center,
            y=floor_y_start + floor_h + tab_post_y_thickness + tab_h / 2,
            z=board_z,
            lx=cap_lx, ly=tab_h, lz=bh - 2.0,
        )
        tabs.append(post.union(cap))

    return _combine([panel, floor] + tabs)


def build_top_panel(p: dict) -> cq.Workplane:
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
    panel = _box_at(
        x=0, y=(y_lo + y_hi) / 2, z=H - t / 2,
        lx=plate_w, ly=y_hi - y_lo, lz=t,
    )

    # Screw clearance holes at the front-top corners, lined up with the top
    # screw bosses below.
    inset = p["top_screw_boss_inset"]
    screw_r = _hole_dia(p, p["screw_clearance_target"]) / 2
    xs = [-W / 2 + inset, W / 2 - inset]
    y_screw = D / 2 - wall - inset + 1.0
    for x in xs:
        hole = _cyl_z(x, y_screw, z_start=H - t - 0.5, radius=screw_r, length=t + 1.0)
        panel = panel.cut(hole)

    return panel


# ----- entry point ---------------------------------------------------------

def main() -> int:
    p = PARAMS
    out_dir = Path(p["output_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"mr-radar enclosure v{p['version']}")
    print(f"  cabinet: {p['width']} x {p['height']} x {p['depth']} mm")
    print(f"  output:  {out_dir}")

    parts = [
        ("body", build_body),
        ("back", build_back_panel),
        ("top",  build_top_panel),
    ]
    for suffix, builder in parts:
        solid = builder(p)
        out_path = out_dir / f"mr-radar-enclosure-v{p['version']}-{suffix}.stl"
        cq.exporters.export(solid, str(out_path))
        print(f"  wrote   {out_path.name}  ({out_path.stat().st_size // 1024} KiB)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
