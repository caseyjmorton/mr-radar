import sys
from pathlib import Path

_root = str(Path(__file__).resolve().parents[2])
if _root not in sys.path:
    sys.path.insert(0, _root)

import enclosure.common.main as main
from enclosure.params.main import params
from cadquery import Workplane

def top_screw_bosses(p: dict) -> Workplane:
    """Two posts at the top-FRONT corners with a 45 degree tapered fin running
    from each boss down to the inside of the front wall. The fin removes the
    need for support material when the body is printed upright: each layer of
    the fin extends just 0.3 mm (= layer height) farther from the wall, which
    is the 45 degree printable limit.

    Boss layout:
      - Boss center sits a comfortable distance back from the front wall.
      - Fin sits BELOW the boss (z < boss_bottom) on the front-wall side, so
        as the print rises, the fin gradually thickens until it merges with
        the boss bottom. The boss itself is then supported continuously."""
    W, D, H, wall = p["width"], p["depth"], p["height"], p["wall"]
    inset = p["top_screw_boss_inset"]
    t = p["panel_thickness"]
    boss_r = p["screw_boss_dia"] / 2
    pilot_r = main.hole_dia(p, p["screw_boss_pilot_target"]) / 2
    boss_h = p["top_lip_depth"] + 6.0
    z_top_of_boss = H - t
    z_boss_bottom = z_top_of_boss - boss_h
    xs = [-W / 2 + inset, W / 2 - inset]
    # Boss y center: inset a bit from the front wall so the fin has room.
    y_front_inner = D / 2 - wall
    y_boss = y_front_inner - inset + 1.0
    # Distance from boss's BACK edge to the front wall:
    fin_y_run = y_front_inner - (y_boss - boss_r)
    # Vertical taper depth: 45 degrees -> dz = dy. The fin starts at the boss
    # bottom and runs DOWN by fin_y_run, where it merges with the front wall.
    fin_z_run = fin_y_run
    fin_x_width = p["screw_boss_dia"]

    parts: list[Workplane] = []
    for x in xs:
        boss = main.cyl_z(x, y_boss, z_start=z_boss_bottom, radius=boss_r, length=boss_h)
        # Filler toward the front wall: box from the boss's diametric line (at y_boss)
        # forward to the front wall interior, spanning the full boss circle in X and
        # the full boss height in Z.
        boss = boss.union(main.box_at(
            x=x, y=(y_boss + y_front_inner) / 2, z=z_boss_bottom + boss_h / 2,
            lx=p["screw_boss_dia"], ly=y_front_inner - y_boss, lz=boss_h,
        ))
        pilot = main.cyl_z(x, y_boss, z_start=z_boss_bottom - 0.5, radius=pilot_r,
                       length=t + boss_h + 1.0)
        boss = boss.cut(pilot)

        # 45 degree fin conforming to the boss's round profile.
        # Build the full triangular prism (same depth and slope as before), then clip
        # it so the back face follows the boss's cylindrical arc rather than being a
        # flat wall.  The clipping solid is the boss cylinder extended below
        # z_boss_bottom (which rounds off the back) unioned with a rectangular cover
        # for the filler region (y >= y_boss) so that portion keeps full boss-dia width.
        fin_profile = (
            Workplane("YZ")
            .moveTo(y_boss - boss_r, z_boss_bottom)
            .lineTo(y_front_inner, z_boss_bottom)
            .lineTo(y_front_inner, z_boss_bottom - fin_z_run)
            .close()
        )
        _prism = fin_profile.extrude(fin_x_width).translate((x - fin_x_width / 2, 0, 0))
        _ext_cyl = main.cyl_z(x, y_boss, z_start=z_boss_bottom - fin_z_run - 1.0,
                              radius=boss_r, length=fin_z_run + 1.0)
        _filler_cover = main.box_at(
            x=x, y=(y_boss + y_front_inner) / 2, z=z_boss_bottom - fin_z_run / 2,
            lx=fin_x_width, ly=y_front_inner - y_boss, lz=fin_z_run + 2.0,
        )
        fin = _prism.intersect(_ext_cyl.union(_filler_cover))
        parts.append(boss.union(fin))
    return main.combine(parts)

result = top_screw_bosses(params)