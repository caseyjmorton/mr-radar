import sys
from pathlib import Path

_root = str(Path(__file__).resolve().parents[2])
if _root not in sys.path:
    sys.path.insert(0, _root)

import enclosure.common.main as main
from enclosure.params.main import params
from cadquery import Workplane


def back_screw_bosses(p: dict) -> Workplane:
    """Two posts at the back-BOTTOM corners. They start just BEHIND the back
    panel (at y = -D/2 + panel_thickness) so the panel and boss don't fight
    for the same Y space; the screw passes through the panel's clearance hole
    and bites into the boss."""
    W, D, wall = p["width"], p["depth"], p["wall"]
    inset = p["back_screw_boss_inset"]
    t = p["panel_thickness"]
    boss_r = p["screw_boss_dia"] / 2
    pilot_r = main.hole_dia(p, p["screw_boss_pilot_target"]) / 2
    boss_h = p["back_lip_depth"] + 6.0
    y_start = -D / 2 + t
    xs = [-W / 2 + inset, W / 2 - inset]
    z = wall + inset - 1.0     # sit on top of bottom wall, slightly tucked in
    parts: list[Workplane] = []
    for x in xs:
        boss = main.cyl_y(x, z, y_start=y_start, radius=boss_r, length=boss_h)
        # Filler toward the side wall: box from the boss's diametric line (at x)
        # out to the cabinet interior side face, spanning the full boss circle in Z.
        x_side = (W / 2 - wall) * (1 if x > 0 else -1)
        boss = boss.union(main.box_at(
            x=(x + x_side) / 2, y=y_start + boss_h / 2, z=z,
            lx=abs(x_side - x), ly=boss_h, lz=p["screw_boss_dia"],
        ))
        # Filler toward the cabinet floor: box from the boss's diametric line (at z)
        # down to the floor interior, spanning the full boss circle in X.
        boss = boss.union(main.box_at(
            x=x, y=y_start + boss_h / 2, z=(wall + z) / 2,
            lx=p["screw_boss_dia"], ly=boss_h, lz=z - wall,
        ))
        # Pilot extends from the panel face (so the screw threads start biting
        # immediately once they exit the panel) through and past the boss.
        pilot = main.cyl_y(x, z, y_start=-D / 2 - 0.5, radius=pilot_r, length=t + boss_h + 1.0)
        parts.append(boss.cut(pilot))
    return main.combine(parts)

result = back_screw_bosses(params)