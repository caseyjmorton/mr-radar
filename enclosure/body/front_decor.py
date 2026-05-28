import sys
from pathlib import Path

_root = str(Path(__file__).resolve().parents[2])
if _root not in sys.path:
    sys.path.insert(0, _root)

import enclosure.common.main as main
from enclosure.params.main import params
from cadquery import Workplane, Plane, Vector


def front_decor(p: dict) -> Workplane:
    """Buttons + LEDs + MR. RADAR label, all raised outward from the front face."""
    D, H = p["depth"], p["height"]
    parts: list[Workplane] = []

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
            parts.append(main.cyl_y(x, z, y_start=D / 2, radius=btn_r, length=btn_h))

    # LED column
    led_x = p["led_column_x_offset_from_center"]
    led_center_z = H - p["led_column_center_z_from_top"]
    led_r = p["led_dia"] / 2
    led_h = p["led_height"]
    led_n = p["led_count"]
    led_p = p["led_pitch"]
    for i in range(led_n):
        z = led_center_z + (i - (led_n - 1) / 2) * led_p
        parts.append(main.cyl_y(led_x, z, y_start=D / 2, radius=led_r, length=led_h))

    # MR. RADAR label. Built on an explicit +Y-normal plane so the letters are
    # right-readable from the front (the stock XZ plane has -Y normal, which
    # made the text render mirrored when viewed from outside). xDir = -X keeps
    # the plane's local Y pointing up in world coordinates so letters print
    # the right way up; reading direction (local +X) maps to world -X, which
    # is the camera's right when looking at the cabinet from the front.
    label_z = H - p["label_z_from_top"]
    label_extrude = p["label_extrude"]
    front_plane = Plane(
        origin=Vector(0, D / 2, label_z),
        xDir=Vector(-1, 0, 0),
        normal=Vector(0, 1, 0),
    )
    label = (
        Workplane(front_plane)
        .text(
            p["label_text"],
            p["label_font_size"],
            label_extrude,
            halign="center",
            valign="center",
        )
    )
    parts.append(label)

    return main.combine(parts)

result = front_decor(params)