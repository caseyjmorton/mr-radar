import sys
from pathlib import Path

_root = str(Path(__file__).resolve().parents[2])
if _root not in sys.path:
    sys.path.insert(0, _root)

from enclosure.params.main import params
from cadquery import Workplane

from enclosure.body.cabinet_shell import cabinet_shell
from enclosure.body.display_window import display_window
from enclosure.body.back_lip import back_lip
from enclosure.body.top_lip import top_lip
from enclosure.body.back_screw_bosses import back_screw_bosses
from enclosure.body.top_screw_bosses import top_screw_bosses
from enclosure.body.display_mount_posts import display_mount_posts
from enclosure.body.board_mount import board_mount
from enclosure.body.front_decor import front_decor

def body(p: dict) -> Workplane:
    return (
        cabinet_shell(p)
            .cut(display_window(p))
            .union(back_lip(p))
            .union(top_lip(p))
            .union(back_screw_bosses(p))
            .union(top_screw_bosses(p))
            .union(display_mount_posts(p))
            .union(board_mount(p))
            .union(front_decor(p))
    )

result = body(params)
