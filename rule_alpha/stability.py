"""Will it stay where it was put?

The competition has no support-ratio rule.  ``place_item`` warps the item to the
target pose, runs 300 steps of physics, and accepts it unless it moved more than
0.30 m or rotated more than 45 degrees.  So the question a planner has to answer
is mechanical, not bureaucratic: *does this box topple when released?*

For a rigid body resting on contacts, it does not topple exactly when the
vertical projection of its centre of mass falls inside the **support polygon** —
the convex hull of the contact patches.  That single statement covers both of
the shapes rule-alpha cares about, and covers them correctly:

* a **cantilever** off one support of width ``w`` overhanging by ``o`` has its
  centre at ``w/2 - o`` from the support edge, so it is stable exactly while
  ``o <= w/2``.  Measured on the simulator: clean up to ``o/w = 0.50``, tips at
  0.60.  The criterion predicts the observation rather than being fitted to it.
* a **bridge** across two piers has its centre between them, inside the hull,
  and is stable however small either individual contact is.  Measured: accepted
  down to a single contact of 0.24 of the footprint.

The older rule -- largest single contact patch at least 0.6 of the footprint --
gets the cantilever roughly right by accident and the bridge completely wrong,
which is why bridges were impossible before.

Contacts come from the floor, the shelves, and packed *hard* items.  Soft and
priority cargo is excluded, as it is everywhere else: it deforms, so it is not
structure.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from ._reuse import AABB, packed_aabbs_local, shelf_aabbs
from .geometry import Rect


@dataclass(frozen=True)
class Stability:
    """Where the centre of mass sits relative to the support polygon."""

    margin: float
    """Distance from the centre of mass projection to the polygon boundary.
    Positive inside, negative outside, in metres."""

    contact_area: float
    contact_count: int
    polygon: tuple

    @property
    def supported(self) -> bool:
        return self.contact_count > 0 and self.margin > 0.0


def contact_patches(box: AABB, container: dict, tolerance: float) -> list[Rect]:
    """Rectangles where the underside of ``box`` meets something solid."""
    bottom = float(box.minimum[2])
    surfaces = [
        AABB(
            center=(0.0, 0.0, float(container["thickness"])
                    + float(container.get("buffer", 0.0))),
            size=(float(container["length"]), float(container["width"]), 0.0),
            name="floor",
        )
    ]
    surfaces.extend(shelf_aabbs(container))
    for packed, is_soft, is_prioritized in packed_aabbs_local(container):
        if is_soft or is_prioritized:
            continue  # deforms under load, so it is not structure
        surfaces.append(packed)

    patches = []
    for surface in surfaces:
        if abs(bottom - float(surface.maximum[2])) > tolerance:
            continue
        x_min = max(float(box.minimum[0]), float(surface.minimum[0]))
        x_max = min(float(box.maximum[0]), float(surface.maximum[0]))
        y_min = max(float(box.minimum[1]), float(surface.minimum[1]))
        y_max = min(float(box.maximum[1]), float(surface.maximum[1]))
        if x_max - x_min <= 1e-9 or y_max - y_min <= 1e-9:
            continue
        patches.append(Rect(x_min, x_max, y_min, y_max))
    return patches


def convex_hull(points) -> list[tuple[float, float]]:
    """Andrew's monotone chain.  Small inputs, so clarity beats cleverness."""
    unique = sorted(set((round(x, 9), round(y, 9)) for x, y in points))
    if len(unique) <= 2:
        return unique

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: list[tuple[float, float]] = []
    for point in unique:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], point) <= 0:
            lower.pop()
        lower.append(point)
    upper: list[tuple[float, float]] = []
    for point in reversed(unique):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], point) <= 0:
            upper.pop()
        upper.append(point)
    return lower[:-1] + upper[:-1]


def point_margin(polygon, point) -> float:
    """Signed distance from ``point`` to the boundary; positive inside.

    Convex polygon in counter-clockwise order, so a point is inside when it is
    left of every edge, and the margin is the smallest of those distances.
    """
    if len(polygon) < 3:
        if len(polygon) == 2:
            # a degenerate line of contact supports nothing on its own
            return -_segment_distance(polygon[0], polygon[1], point)
        if len(polygon) == 1:
            return -math.dist(polygon[0], point)
        return -float("inf")

    best = float("inf")
    count = len(polygon)
    for index in range(count):
        ax, ay = polygon[index]
        bx, by = polygon[(index + 1) % count]
        ex, ey = bx - ax, by - ay
        length = math.hypot(ex, ey)
        if length < 1e-12:
            continue
        # positive when the point is to the left of a -> b
        signed = ((point[0] - ax) * ey - (point[1] - ay) * ex) / -length
        best = min(best, signed)
    return best


def _segment_distance(a, b, point) -> float:
    ax, ay = a
    bx, by = b
    ex, ey = bx - ax, by - ay
    denom = ex * ex + ey * ey
    if denom < 1e-18:
        return math.dist(a, point)
    t = max(0.0, min(1.0, ((point[0] - ax) * ex + (point[1] - ay) * ey) / denom))
    return math.dist((ax + t * ex, ay + t * ey), point)


def evaluate(box: AABB, container: dict, config) -> Stability:
    """Support polygon of ``box`` and how far its centre of mass sits inside it.

    The centre of mass is taken as the box centre: cargo density is not given,
    and assuming it is uniform is the only assumption available.
    """
    patches = contact_patches(box, container, config.contact_tolerance)
    if not patches:
        return Stability(-float("inf"), 0.0, 0, ())

    corners = []
    area = 0.0
    for rect in patches:
        area += rect.area
        corners.extend(
            [
                (rect.x_min, rect.y_min), (rect.x_max, rect.y_min),
                (rect.x_max, rect.y_max), (rect.x_min, rect.y_max),
            ]
        )
    polygon = convex_hull(corners)
    centre = (float(box.center[0]), float(box.center[1]))
    return Stability(
        margin=point_margin(polygon, centre),
        contact_area=area,
        contact_count=len(patches),
        polygon=tuple(polygon),
    )


def is_stable(box: AABB, container: dict, config) -> tuple[bool, float]:
    """``(stable, margin)`` under the configured safety margin."""
    state = evaluate(box, container, config)
    return state.margin >= config.com_margin, state.margin


def support_area_ratio(box: AABB, container: dict, config) -> float:
    """Kept for diagnostics only: contact area over footprint.

    Reported so the tables can show what the old rule would have said, never
    used to accept or refuse a placement.
    """
    state = evaluate(box, container, config)
    footprint = float(box.size[0]) * float(box.size[1])
    if footprint <= 1e-12:
        return 0.0
    return min(1.0, state.contact_area / footprint)


def hull_area(polygon) -> float:
    if len(polygon) < 3:
        return 0.0
    total = 0.0
    for index in range(len(polygon)):
        ax, ay = polygon[index]
        bx, by = polygon[(index + 1) % len(polygon)]
        total += ax * by - bx * ay
    return abs(total) / 2.0


__all__ = [
    "Stability", "contact_patches", "convex_hull", "evaluate", "hull_area",
    "is_stable", "point_margin", "support_area_ratio",
]
