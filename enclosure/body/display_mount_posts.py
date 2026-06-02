import sys
from pathlib import Path

_root = str(Path(__file__).resolve().parents[2])
if _root not in sys.path:
    sys.path.insert(0, _root)

import enclosure.common.main as main
from enclosure.params.main import params
from cadquery import Workplane

_NEAR_ZERO = 1e-6  # avoids degenerate (zero-area) geometry in OCC; must exceed Precision.Confusion (1e-7)


def display_mount_posts(p: dict) -> Workplane:
    """Two horizontal posts behind the front wall, axis along Y, tapped for
    M2 self-tap screws through the GC9A01 PCB's mount holes."""
    D, H, wall = p["depth"], p["height"], p["wall"]
    spacing = p["display_post_spacing"]
    post_r = p["display_post_dia"] / 2
    pilot_r = main.hole_dia(p, p["display_post_pilot_target"]) / 2
    post_h = 4.0
    z = H - p["display_center_z_from_top"] - p["display_post_z_offset_below_center"]
    y_front_inner = D / 2 - wall
    y_tip = y_front_inner - post_h
    y_mid = (y_tip + y_front_inner) / 2

    parts: list[Workplane] = []
    for x in (-spacing / 2, spacing / 2):
        post = main.cyl_y(x, z, y_start=y_tip, radius=post_r, length=post_h)

        # Box filling the lower half of the post cross-section.
        lower_box = main.box_at(x=x, y=y_mid, z=z - post_r / 2,
                                lx=2 * post_r, ly=post_h, lz=post_r)

        # 45° tapered chamfer below lower_box: wide at the top (matching the
        # box bottom face), narrows to a line going down — self-supporting ramp.
        taper_depth = post_h
        support_taper = (
            Workplane("XY")
            .rect(2 * post_r, post_h)
            .extrude(taper_depth)
            .edges("|X and >Y and >Z")
            .chamfer(taper_depth - _NEAR_ZERO)
            .rotate((0, 0, 0), (1, 0, 0), 180)
            .translate((x, y_mid, z - post_r))
        )

        post = post.union(lower_box).union(support_taper)

        pilot = main.cyl_y(x, z, y_start=y_tip - 0.1, radius=pilot_r, length=post_h + 0.2)
        post = post.cut(pilot)
        parts.append(post)
    return main.combine(parts)

result = display_mount_posts(params)
