from cadquery import Workplane

def hole_dia(p: dict, designed: float) -> float:
    """Add per-print hole compensation to a designed diameter."""
    return designed + p["hole_oversize"]

# ----- placement helpers ---------------------------------------------------
# Everything is positioned by world coordinates to avoid the XZ-plane normal
# direction confusion that bites with `Workplane("XZ").workplane(offset=...)`.

def cyl_y(x: float, z: float, y_start: float, radius: float, length: float) -> Workplane:
    """Cylinder of given radius and length, axis along +Y, base at (x, y_start, z)."""
    return (
        Workplane("XY")
        .cylinder(length, radius, centered=(True, True, False))
        .rotate((0, 0, 0), (1, 0, 0), -90)        # +Z -> +Y
        .translate((x, y_start, z))
    )


def cyl_z(x: float, y: float, z_start: float, radius: float, length: float) -> Workplane:
    """Cylinder of given radius and length, axis along +Z, base at (x, y, z_start)."""
    return (
        Workplane("XY")
        .cylinder(length, radius, centered=(True, True, False))
        .translate((x, y, z_start))
    )


def box_at(x: float, y: float, z: float, lx: float, ly: float, lz: float) -> Workplane:
    """Box of full extents (lx, ly, lz), centered at world (x, y, z)."""
    return (
        Workplane("XY")
        .box(lx, ly, lz, centered=(True, True, True))
        .translate((x, y, z))
    )


def combine(parts: list[Workplane]) -> Workplane:
    """Union a non-empty list of solids."""
    out = parts[0]
    for p in parts[1:]:
        out = out.union(p)
    return out
