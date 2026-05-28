from pathlib import Path
from enclosure.version import __version__

params = {
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
    "led_column_x_offset_from_center": -28.0,    # negative = viewer's right when facing front
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

    # Dev board (Waveshare ESP32-S3-Zero). Mounted to the cabinet FLOOR, long
    # axis along X, short axis along Y, USB-C on the -Y (back) edge so the
    # connector pokes through the back panel's cutout.
    "board_long":             24.0,    # X dimension (long edge), with small inflate
    "board_short":            18.5,    # Y dimension (short edge, USB-C on -Y end)
    "board_thickness":        1.6,     # Z dimension
    "board_floor_height":     2.0,     # standoff height: gap between cabinet floor and board
    "board_tab_height":       1.5,     # cap height above the board's top surface
    "board_tab_width":        3.0,     # tab post X thickness
    "board_back_clearance":   0.6,     # gap between board back edge and back lip front face
    "board_usb_cutout_w":     10.5,    # X dim of USB-C cutout (target print 10mm)
    "board_usb_cutout_h":     5.5,     # Z dim of USB-C cutout (target print 5mm)
    "board_usb_z_above_top":  1.5,     # USB-C center is this far above the board's top surface

    # Output
    "version":    __version__,
    "output_dir": str(Path(__file__).parent.parent / "build"),
}