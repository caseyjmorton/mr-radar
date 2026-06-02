import sys
from pathlib import Path

_root = str(Path(__file__).resolve().parents[2])
if _root not in sys.path:
    sys.path.insert(0, _root)

import enclosure.common.main as main
from enclosure.params.main import params
from cadquery import Workplane


def board_mount(p: dict) -> Workplane:
    """ESP32-S3-Zero retention on the cabinet FLOOR. Four small standoffs
    raise the board off the floor (airflow + WiFi-antenna clearance) and
    two side retention tabs cap the long edges. The board's long axis is X;
    its short axis is Y with the USB-C connector on the -Y (back) edge.

    Board is installed BEFORE the back panel goes on: slide it in from the
    open back, push down onto the standoffs between the tabs."""
    W, D, wall = p["width"], p["depth"], p["wall"]
    bl, bs, bt = p["board_long"], p["board_short"], p["board_thickness"]
    floor_h = p["board_floor_height"]
    slip = p["slip_tol"]
    panel_t = p["panel_thickness"]
    back_lip_d = p["back_lip_depth"]
    back_clear = p["board_back_clearance"]

    # Y placement: board's back edge sits just past the back lip's front face
    # so the board doesn't collide with the lip and the USB-C connector pokes
    # forward of the back panel hole into the cable plug's path.
    board_y_back = -D / 2 + panel_t + back_lip_d + back_clear
    board_y_front = board_y_back + bs
    board_y_center = (board_y_back + board_y_front) / 2
    board_z_bottom = wall + floor_h
    board_z_top = board_z_bottom + bt

    parts: list[Workplane] = []

    # Four corner standoffs: short bumps raising the board off the floor.
    standoff = 2.5
    for sx in (-1, 1):
        for sy_y in (board_y_back + standoff / 2, board_y_front - standoff / 2):
            sx_x = sx * (bl / 2 - standoff / 2)
            parts.append(main.box_at(
                x=sx_x, y=sy_y, z=wall + floor_h / 2,
                lx=standoff, ly=standoff, lz=floor_h,
            ))

    # Two retention tabs at the board's long edges, centered on Y.
    tab_w = p["board_tab_width"]
    tab_h = p["board_tab_height"]
    tab_y_len = min(bs - 6.0, 10.0)
    cap_overlap = 1.0
    post_x_inner = bl / 2 + slip
    post_x_outer = post_x_inner + tab_w

    for x_sign in (-1, 1):
        post_x_center = x_sign * (post_x_inner + post_x_outer) / 2
        post = main.box_at(
            x=post_x_center, y=board_y_center,
            z=(wall + board_z_top) / 2,
            lx=tab_w, ly=tab_y_len, lz=board_z_top - wall,
        )
        # Cap that overhangs the board's top by cap_overlap. Flat rectangular
        # cap with a small (<= 1 mm) horizontal overhang — well within what a
        # 0.6 mm nozzle bridges without explicit support material.
        cap_inner_x = x_sign * (post_x_inner - cap_overlap)
        cap_outer_x = x_sign * post_x_outer
        cap_x_center = (cap_inner_x + cap_outer_x) / 2
        cap_lx = abs(cap_outer_x - cap_inner_x)
        cap = main.box_at(
            x=cap_x_center, y=board_y_center,
            z=board_z_top + tab_h / 2,
            lx=cap_lx, ly=tab_y_len, lz=tab_h,
        )
        parts.append(post.union(cap))

    return main.combine(parts)

result = board_mount(params)