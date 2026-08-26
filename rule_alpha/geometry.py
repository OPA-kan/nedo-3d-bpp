"""Analytic model of one ULD: cut-corner cross section, zones, slope pocket.

The competition ULD is a pentagonal prism.  ``write_open_cut_corner_cup_obj``
in the simulator builds it by chamfering one corner of a rectangle with
``cut_x`` / ``cut_y`` and extruding along the depth axis.  Everything rule-alpha
needs about that shape is re-derived here analytically from
``length / width / height / thickness / cut_x / cut_y``, which is what the spec
asks for, and which also lets scenarios synthesize containers without booting
PyBullet.

World frame (matching the simulator, per container, before the X offset):

    +X   container length,  -X is the chamfered / small-shelf side
    +Y   container depth,   +Y is the BACK wall, -Y is the OPENING
    +Z   container height,  Z = thickness + buffer is the floor surface

The chamfer therefore runs along the bottom-left edge for the full depth, and
the small shelf sits directly above it at mid height.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from ._reuse import AABB, container_requires_shelf, shelf_aabbs


# ---------------------------------------------------------------------------
# Cross section
# ---------------------------------------------------------------------------
def _offset_convex_polygon_ccw(poly, offset):
    """Shrink a CCW convex polygon by ``offset`` along every inward normal.

    Same construction as ``simulator/src/ground_handling/utils.py`` so that the
    planes derived here match the ones the official validator tests against.
    """
    lines = []
    n = len(poly)
    for i in range(n):
        ax, ay = poly[i]
        bx, by = poly[(i + 1) % n]
        ex, ey = bx - ax, by - ay
        length = math.hypot(ex, ey)
        if length < 1e-12:
            raise ValueError("degenerate polygon edge")
        nx, ny = -ey / length, ex / length
        lines.append(((ax + nx * offset, ay + ny * offset), (ex, ey)))

    inner = []
    for i in range(n):
        (p1x, p1y), (d1x, d1y) = lines[i - 1]
        (p2x, p2y), (d2x, d2y) = lines[i]
        cross = d1x * d2y - d1y * d2x
        if abs(cross) < 1e-12:
            raise ValueError("parallel offset lines")
        t = ((p2x - p1x) * d2y - (p2y - p1y) * d2x) / cross
        inner.append((p1x + t * d1x, p1y + t * d1y))
    return inner


def cut_corner_planes(length, width, height, thickness, cut_x, cut_y, buffer=0.0,
                      offset_x=0.0):
    """Return ``(points, n_vecs)`` in world coordinates, simulator-compatible.

    The simulator builds the cross section in an object frame whose ``x`` is the
    container length and whose ``y`` is the container height, extrudes it along
    the object ``z`` (the container depth), then rotates +90 deg about X so that
    ``(x, y, z)_obj -> (x, -z, y)_world`` and lifts it by ``height/2 + buffer``.
    """
    outer = [
        (cut_x, 0.0),
        (length, 0.0),
        (length, height),
        (0.0, height),
        (0.0, cut_y),
    ]
    inner = _offset_convex_polygon_ccw(outer, thickness)
    cx, cy = length / 2.0, height / 2.0
    inner = [(x - cx, y - cy) for x, y in inner]

    lift = height / 2.0 + buffer
    points, normals = [], []
    n = len(inner)
    for i in range(n):
        ax, ay = inner[i]
        bx, by = inner[(i + 1) % n]
        ex, ey = bx - ax, by - ay
        norm = math.hypot(ex, ey)
        # object-space outward normal of a CCW polygon edge
        points.append([ax + offset_x, 0.0, ay + lift])
        normals.append([ey / norm, 0.0, -ex / norm])

    half_depth = width / 2.0
    # opening face (no wall) and back wall
    points.append([offset_x, -half_depth, lift])
    normals.append([0.0, -1.0, 0.0])
    points.append([offset_x, half_depth - thickness, lift])
    normals.append([0.0, 1.0, 0.0])
    return points, normals


# ---------------------------------------------------------------------------
# Container model
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Rect:
    """Axis aligned rectangle on the container floor (local XY)."""

    x_min: float
    x_max: float
    y_min: float
    y_max: float

    @property
    def area(self) -> float:
        return max(0.0, self.x_max - self.x_min) * max(0.0, self.y_max - self.y_min)

    def overlap_area(self, other: "Rect") -> float:
        dx = min(self.x_max, other.x_max) - max(self.x_min, other.x_min)
        dy = min(self.y_max, other.y_max) - max(self.y_min, other.y_min)
        return max(0.0, dx) * max(0.0, dy)

    def as_tuple(self):
        return (self.x_min, self.x_max, self.y_min, self.y_max)


class ContainerModel:
    """Derived geometry and zone layout for a single container."""

    def __init__(self, container: dict, config):
        self.raw = container
        self.config = config
        self.index = int(container.get("index", 0))
        self.length = float(container["length"])
        self.width = float(container["width"])
        self.height = float(container["height"])
        self.thickness = float(container["thickness"])
        self.buffer = float(container.get("buffer", 0.0))
        self.cut_x = float(container.get("cut_x", 0.0))
        self.cut_y = float(container.get("cut_y", 0.0))
        self.has_shelf = bool(container_requires_shelf(container))
        self.is_prioritized = bool(container.get("is_prioritized", False))

        # --- planes -----------------------------------------------------
        points, normals = cut_corner_planes(
            self.length, self.width, self.height, self.thickness,
            self.cut_x, self.cut_y, self.buffer,
        )
        self.plane_points = np.asarray(points, dtype=np.float64)
        self.plane_normals = np.asarray(normals, dtype=np.float64)

        # --- basic bounds ----------------------------------------------
        self.z_floor = self.thickness + self.buffer
        self.z_ceiling = self.height + self.buffer - self.thickness
        self.x_wall_min = -self.length / 2.0 + self.thickness
        self.x_wall_max = self.length / 2.0 - self.thickness
        self.y_opening = -self.width / 2.0
        self.y_back = self.width / 2.0 - self.thickness

        # --- chamfer ----------------------------------------------------
        self._chamfer = self._find_chamfer_plane()
        self.x_floor_min = self.x_limit_at_height(self.z_floor)
        self.z_chamfer_top = self._chamfer_top_height()

        clr = float(config.inclusion_clearance)
        self.floor_rect = Rect(
            self.x_floor_min + clr,
            self.x_wall_max - clr,
            self.y_opening + clr,
            self.y_back - clr,
        )
        self.usable_floor_area = self.floor_rect.area

        # --- shelves ----------------------------------------------------
        self.shelves = list(shelf_aabbs(container))
        self.small_shelf = next(
            (s for s in self.shelves if s.name == "small_shelf"), None
        )
        self.main_shelf = next(
            (s for s in self.shelves if s.name == "main_shelf"), None
        )
        self.shelf_bottom_z = (
            self.height / 2.0 + self.buffer if self.shelves else self.z_ceiling
        )

        # --- zones ------------------------------------------------------
        # Zone widths scale with declared demand.  Until a manifest is seen the
        # strips are full width, which is the conservative reservation.
        self.soft_zone_scale = 1.0
        self.priority_zone_scale = 1.0
        self._build_zones()

    def set_zone_scales(self, soft_scale: float, priority_scale: float) -> None:
        """Resize the reserved edge strips to the demand actually declared.

        The environment hands the whole manifest to ``optimize()``, so sizing a
        reservation from it is reading a *given* list, not guessing at unseen
        items.  A stream with no soft cargo gets no soft strip.
        """
        self.soft_zone_scale = max(0.0, min(1.0, float(soft_scale)))
        self.priority_zone_scale = max(0.0, min(1.0, float(priority_scale)))
        self._build_zones()

    # -- chamfer helpers -------------------------------------------------
    def _find_chamfer_plane(self):
        """The one plane whose normal has both an X and a Z component."""
        best = None
        for point, normal in zip(self.plane_points, self.plane_normals):
            if abs(normal[0]) > 1e-9 and abs(normal[2]) > 1e-9:
                best = (np.asarray(point), np.asarray(normal))
                break
        return best

    def x_limit_at_height(self, z: float) -> float:
        """Leftmost X a box corner may occupy at height ``z``.

        Above the chamfer this is simply the left wall; inside the chamfer band
        it follows the slope, which is what makes the pocket a pocket.
        """
        if self._chamfer is None:
            return self.x_wall_min
        point, normal = self._chamfer
        # normal . (p - point) <= 0  with normal_x < 0  =>  x >= ...
        rhs = normal[2] * (z - point[2])
        x_limit = point[0] - rhs / normal[0]
        return max(self.x_wall_min, float(x_limit))

    def _chamfer_top_height(self) -> float:
        """Height at which the chamfer meets the left wall."""
        if self._chamfer is None:
            return self.z_floor
        point, normal = self._chamfer
        # solve x_limit(z) == x_wall_min
        rhs = (point[0] - self.x_wall_min) * normal[0]
        z = point[2] + rhs / normal[2]
        return float(max(self.z_floor, z))

    # -- zones -----------------------------------------------------------
    def _build_zones(self):
        cfg = self.config
        rect = self.floor_rect
        usable_len = rect.x_max - rect.x_min
        depth = rect.y_max - rect.y_min

        back_depth = cfg.back_band_fraction * depth
        edge_w = cfg.edge_band_fraction * usable_len
        corridor_w = cfg.corridor_width_fraction * usable_len
        corridor_d = cfg.corridor_depth_fraction * depth
        # The chamfer is on the -X side, so the slope wall front and the soft
        # edge both want the left strip.  The wall front gets the outermost
        # band (it has to touch the chamfer foot); soft starts just inside it.
        wall_strip = cfg.wall_front_strip_fraction * usable_len

        self.back_band = Rect(rect.x_min, rect.x_max, rect.y_max - back_depth, rect.y_max)
        self.front_band = Rect(rect.x_min, rect.x_max, rect.y_min, rect.y_max - back_depth)
        self.wall_front_strip = Rect(
            rect.x_min, rect.x_min + wall_strip, rect.y_min, rect.y_max
        )
        soft_w = edge_w * self.soft_zone_scale
        priority_w = edge_w * self.priority_zone_scale
        self.left_edge = Rect(
            rect.x_min + wall_strip, rect.x_min + wall_strip + soft_w,
            rect.y_min, rect.y_max,
        )
        self.right_edge = Rect(
            rect.x_max - priority_w, rect.x_max, rect.y_min, rect.y_max
        )

        self.soft_zone = Rect(
            rect.x_min + wall_strip,
            rect.x_min + wall_strip + soft_w,
            rect.y_min,
            rect.y_max - back_depth,
        )
        self.priority_zone = Rect(
            rect.x_max - priority_w, rect.x_max, rect.y_min, rect.y_max - back_depth
        )
        centre = 0.5 * (rect.x_min + rect.x_max)
        self.corridor = Rect(
            centre - corridor_w / 2.0,
            centre + corridor_w / 2.0,
            rect.y_min,
            rect.y_min + corridor_d,
        )
        self.centre_band = Rect(
            self.left_edge.x_max, self.right_edge.x_min, rect.y_min, rect.y_max
        )

        # The slope pocket is the wedge left of the floor limit, under the small
        # shelf.  Nothing whose bottom rests on the floor can reach it.
        pocket_ceiling = min(self.shelf_bottom_z, self.z_ceiling)
        self.slope_pocket = {
            "x_min": self.x_wall_min,
            "x_max": self.x_floor_min,
            "z_min": self.z_floor,
            "z_max": pocket_ceiling,
            "z_chamfer_top": self.z_chamfer_top,
            "y_min": self.y_opening,
            "y_max": self.y_back,
        }
        # Cross-sectional area of the wedge that a floor layer can never use.
        self.slope_wedge_area = 0.5 * max(
            0.0, (self.x_floor_min - self.x_wall_min)
        ) * max(0.0, (self.z_chamfer_top - self.z_floor))

    # -- surfaces --------------------------------------------------------
    def floor_surface(self) -> AABB:
        return AABB(
            center=(0.0, 0.0, self.z_floor),
            size=(self.length, self.width, 0.0),
            name="floor",
        )

    def shelf_rect(self, shelf: AABB) -> Rect:
        return Rect(
            float(shelf.minimum[0]),
            float(shelf.maximum[0]),
            float(shelf.minimum[1]),
            float(shelf.maximum[1]),
        )

    # -- queries ---------------------------------------------------------
    @property
    def floor_plane_index(self) -> int:
        """Index of the downward-facing plane, i.e. the floor surface."""
        if not hasattr(self, "_floor_plane_index"):
            normals = self.plane_normals
            candidates = np.nonzero(normals[:, 2] < -0.99)[0]
            self._floor_plane_index = int(candidates[0]) if len(candidates) else -1
        return self._floor_plane_index

    def inside(self, box: AABB, clearance: float | None = None,
               floor_clearance: float | None = None) -> bool:
        """All eight corners inside every container plane, with clearance.

        ``floor_clearance`` overrides the margin on the floor plane alone.  A
        settled item rests *on* the floor, so it needs a zero margin there even
        though it must keep a real margin from every wall.
        """
        clr = self.config.inclusion_clearance if clearance is None else clearance
        centre = np.asarray(box.center, dtype=np.float64)
        half = np.asarray(box.size, dtype=np.float64) / 2.0
        signed = (
            np.sum(self.plane_normals * (centre - self.plane_points), axis=1)
            + np.abs(self.plane_normals) @ half
        )
        limits = np.full(signed.shape, -clr, dtype=np.float64)
        if floor_clearance is not None and self.floor_plane_index >= 0:
            limits[self.floor_plane_index] = -floor_clearance
        return bool(np.all(signed <= limits + 1e-9))

    def touches_slope_pocket(self, box: AABB) -> bool:
        """True when part of the footprint reaches left of the floor limit."""
        return float(box.minimum[0]) < self.x_floor_min - 1e-6

    def wall_front_line(self) -> float:
        return self.x_floor_min

    def describe(self) -> dict:
        return {
            "index": self.index,
            "length": self.length,
            "width": self.width,
            "height": self.height,
            "thickness": self.thickness,
            "cut_x": self.cut_x,
            "cut_y": self.cut_y,
            "has_shelf": self.has_shelf,
            "is_prioritized": self.is_prioritized,
            "z_floor": round(self.z_floor, 4),
            "z_ceiling": round(self.z_ceiling, 4),
            "x_floor_min": round(self.x_floor_min, 4),
            "x_wall_min": round(self.x_wall_min, 4),
            "x_wall_max": round(self.x_wall_max, 4),
            "y_opening": round(self.y_opening, 4),
            "y_back": round(self.y_back, 4),
            "z_chamfer_top": round(self.z_chamfer_top, 4),
            "shelf_bottom_z": round(self.shelf_bottom_z, 4),
            "usable_floor_area": round(self.usable_floor_area, 4),
            "slope_wedge_cross_area": round(self.slope_wedge_area, 5),
            "slope_wedge_volume": round(
                self.slope_wedge_area * (self.y_back - self.y_opening), 5
            ),
            "floor_rect": [round(v, 4) for v in self.floor_rect.as_tuple()],
            "back_band": [round(v, 4) for v in self.back_band.as_tuple()],
            "wall_front_strip": [round(v, 4) for v in self.wall_front_strip.as_tuple()],
            "soft_zone_scale": round(self.soft_zone_scale, 3),
            "priority_zone_scale": round(self.priority_zone_scale, 3),
            "soft_zone": [round(v, 4) for v in self.soft_zone.as_tuple()],
            "priority_zone": [round(v, 4) for v in self.priority_zone.as_tuple()],
            "corridor": [round(v, 4) for v in self.corridor.as_tuple()],
        }


def box_rect(box: AABB) -> Rect:
    return Rect(
        float(box.minimum[0]),
        float(box.maximum[0]),
        float(box.minimum[1]),
        float(box.maximum[1]),
    )


def make_container_dict(
    index: int,
    length: float,
    width: float,
    height: float,
    thickness: float = 0.04,
    cut_x: float = 0.44,
    cut_y: float = 0.40,
    buffer: float = 0.0,
    require_shelf: bool = False,
    is_prioritized: bool = False,
    offset_x: float = 0.0,
) -> dict:
    """Build an observation-shaped container dict for offline scenarios."""
    points, normals = cut_corner_planes(
        length, width, height, thickness, cut_x, cut_y, buffer, offset_x
    )
    inner_length = length - 2 * thickness
    inner_width = width - 2 * thickness
    inner_height = height - thickness - buffer
    base_volume = inner_length * inner_width * inner_height
    cut_volume = 0.5 * (cut_x - thickness) * (cut_y - thickness) * inner_width
    small_shelf_volume = cut_x * thickness * inner_width
    shelf_volume = 0.0
    if require_shelf:
        shelf_volume = inner_length * thickness * ((width / 2.0) - 2 * thickness)
    volume = base_volume - cut_volume - small_shelf_volume - shelf_volume

    return {
        # raw kwargs the official ``Container`` dataclass accepts, kept so a
        # scenario can be replayed inside the real simulator
        "_spec": {
            "index": index,
            "length": length,
            "width": width,
            "height": height,
            "thickness": thickness,
            "buffer": buffer,
            "cut_x": cut_x,
            "cut_y": cut_y,
            "packed_items": [],
            "require_shelf": require_shelf,
            "is_prioritized": is_prioritized,
        },
        "index": index,
        "length": length,
        "width": width,
        "height": height,
        "thickness": thickness,
        "buffer": buffer,
        "cut_x": cut_x,
        "cut_y": cut_y,
        "shelf": require_shelf,
        "require_shelf": require_shelf,
        "is_prioritized": is_prioritized,
        "volume": volume,
        "center": (offset_x, 0.0, height / 2.0 + buffer),
        "points": points,
        "n_vecs": normals,
        "packed_items": [],
    }
