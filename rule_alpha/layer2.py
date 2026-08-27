"""Layer 2 v0: grow hard support from hard support.

Layer 1 leaves a *back-connected hard foundation* -- not a finished terrace.
Layer 2's job is to turn that seed into large, reachable, connected hard
plateaus, and the wedge is not a special case of anything: it is the same
mechanism applied where the container happens to be triangular.

Three behaviours, all normal-hard for now:

**terrace extension** -- put the box on an existing hard top so its own top
joins that plateau, or sits one step above it.  The cheapest way to make a
plateau bigger is to make it wider at the same height.

**plateau merge / bridge** -- put one box across *two or more* separated hard
supports.  The gap under it was unusable to anything resting on the floor, and
the box's own top is a single plateau wider than either support below it.  This
is the move that makes a surface flatter as it gets higher, and it is only
legal because stability is the support polygon: the centre of mass lands
between the supports even when neither contact is large.

**wedge bridge** -- the same merge aimed at the chamfer.  A wide, low box rests
on wedge-side supports and reaches out over the bevel as far as the support
polygon allows.  The point is not to fill the triangle.  A thin void underneath
is fine if what sits above it is a large reachable hard plateau, because from
then on that plateau is ordinary Layer 2 terrain.

The families exist as *families* on purpose.  Layer 1's shortlist sorts every
candidate by depth and truncates, which is how five separate rules ended up
being no-ops there: they were written downstream of a decision the shortlist had
already made.  Here each family keeps its own quota and they are unioned only at
the end, so a bridge never has to out-depth a floor candidate to be considered.
"""

from __future__ import annotations

import numpy as np

from ._reuse import packed_aabbs_local
from .geometry import ContainerModel, Rect, box_rect


FAMILY_FLOOR = "floor"
FAMILY_TERRACE = "terrace-extension"
FAMILY_BRIDGE = "plateau-merge"
FAMILY_WEDGE_BRIDGE = "wedge-bridge"
FAMILY_SHELF = "shelf"
FAMILY_WEDGE_STEP = "wedge-step"

ALL_FAMILIES = (
    FAMILY_FLOOR, FAMILY_SHELF, FAMILY_WEDGE_STEP, FAMILY_TERRACE,
    FAMILY_BRIDGE, FAMILY_WEDGE_BRIDGE,
)

ROLE_TERRACE = "terrace"
ROLE_BRIDGE = "bridge"
ROLE_WEDGE_BRIDGE = "wedge-bridge"


# ---------------------------------------------------------------------------
# Hard tops available to build on
# ---------------------------------------------------------------------------
def hard_tops(container: dict, model: ContainerModel, config) -> list[tuple[Rect, float]]:
    """``(footprint, top z)`` of every packed hard item.

    Soft and priority cargo is excluded for the same reason it is excluded from
    the support polygon: it deforms, so it is not structure.
    """
    out = []
    for box, is_soft, is_prioritized in packed_aabbs_local(container):
        if is_soft or is_prioritized:
            continue
        top = float(box.maximum[2])
        if top >= model.z_ceiling - config.contact_tolerance:
            continue
        out.append((box_rect(box), top))
    return out


def level_groups(tops, tolerance: float) -> list[tuple[float, list]]:
    """Group hard tops into working heights.

    The group's level is the *highest* member, because that is the one a flat
    underside actually rests on.  Each member keeps its own top so callers can
    tell a true bridge (two supports in contact) from a span over a lower
    neighbour (one support, and a cantilever).
    """
    groups: list[list] = []
    for rect, top in sorted(tops, key=lambda item: item[1], reverse=True):
        for members in groups:
            if abs(members[0][1] - top) <= tolerance:
                members.append((rect, top))
                break
        else:
            groups.append([(rect, top)])
    return [(members[0][1], members) for members in groups]


# ---------------------------------------------------------------------------
# Anchors, per family
# ---------------------------------------------------------------------------
def terrace_anchors(rect: Rect, dx: float, dy: float, gap: float) -> list[tuple[float, float]]:
    """Centres that put the box flush with one edge of an existing top.

    Flush, not centred: the whole point is that the new top continues the old
    one instead of leaving a lip that nothing can bridge later.
    """
    return [
        (rect.x_min + dx / 2.0, rect.y_min + dy / 2.0),
        (rect.x_min + dx / 2.0, rect.y_max - dy / 2.0),
        (rect.x_max - dx / 2.0, rect.y_min + dy / 2.0),
        (rect.x_max - dx / 2.0, rect.y_max - dy / 2.0),
        (0.5 * (rect.x_min + rect.x_max), rect.y_max - dy / 2.0),
        (0.5 * (rect.x_min + rect.x_max), rect.y_min + dy / 2.0),
        # continuing the plateau past its far edge, still overlapping it
        (rect.x_max + dx / 2.0 - gap, 0.5 * (rect.y_min + rect.y_max)),
        (rect.x_min - dx / 2.0 + gap, 0.5 * (rect.y_min + rect.y_max)),
        (0.5 * (rect.x_min + rect.x_max), rect.y_max + dy / 2.0 - gap),
    ]


def bridge_anchors(members: list[tuple[Rect, float]], dx: float,
                   dy: float) -> list[tuple[float, float]]:
    """Centres that span the gap between two hard tops.

    Only pairs whose gap the box can actually cross are offered, and the centre
    goes over the middle of the gap, so that when the two tops really are level
    the centre of mass lands between them rather than on one.  When they are
    not level the box rests on the higher one alone and this is a cantilever;
    the support polygon decides, not this function.
    """
    out = []
    for i in range(len(members)):
        for j in range(i + 1, len(members)):
            a, b = members[i][0], members[j][0]
            for axis in (0, 1):
                lo, hi = (a, b) if _low(a, axis) <= _low(b, axis) else (b, a)
                gap_lo, gap_hi = _high(lo, axis), _low(hi, axis)
                if gap_hi <= gap_lo:
                    continue  # they already touch or overlap on this axis
                span = gap_hi - gap_lo
                reach = dx if axis == 0 else dy
                if reach <= span:
                    continue  # cannot cross it
                # overlap on the other axis, or the box rests on air
                other = 1 - axis
                shared_lo = max(_low(a, other), _low(b, other))
                shared_hi = min(_high(a, other), _high(b, other))
                if shared_hi - shared_lo <= 0.02:
                    continue
                mid = 0.5 * (gap_lo + gap_hi)
                cross = 0.5 * (shared_lo + shared_hi)
                out.append((mid, cross) if axis == 0 else (cross, mid))
    return out


def _low(rect: Rect, axis: int) -> float:
    return rect.x_min if axis == 0 else rect.y_min


def _high(rect: Rect, axis: int) -> float:
    return rect.x_max if axis == 0 else rect.y_max


def wedge_bridge_anchors(members: list[Rect], model: ContainerModel, bottom_z: float,
                         dx: float, dy: float, config) -> list[tuple[float, float]]:
    """Centres that reach out over the chamfer from wedge-side supports.

    Reach is bounded by two things and neither is a guess: the chamfer itself,
    and the point at which the centre of mass would leave the support polygon.
    The second is checked properly later against the real contacts; this only
    has to propose somewhere worth checking.
    """
    limit = model.x_limit_at_height(bottom_z)
    out = []
    for rect, _top in members:
        if rect.x_min > model.x_floor_min + config.wedge_bridge_strip:
            continue  # not on the wedge side; ordinary bridging covers it
        # as far left as the chamfer allows, and as far as half the box width
        # past its support's left edge, whichever binds
        for left in (limit, rect.x_min - dx / 2.0):
            centre_x = max(limit, left) + dx / 2.0
            if centre_x - dx / 2.0 < limit - 1e-9:
                continue
            out.append((centre_x, 0.5 * (rect.y_min + rect.y_max)))
            out.append((centre_x, rect.y_max - dy / 2.0))
            out.append((centre_x, rect.y_min + dy / 2.0))
    return out


# ---------------------------------------------------------------------------
# Plateau accounting -- what a candidate actually buys
# ---------------------------------------------------------------------------
def plateau_map(grid, z_floor: float, tolerance: float):
    """Label the hard top surface into same-height connected plateaus."""
    from .diagnostics import SUPPORT_HARD, connected_components

    hard = grid.usable & (grid.support == SUPPORT_HARD)
    levels = np.round((grid.height - z_floor) / max(tolerance, 1e-6))
    labels = np.zeros(grid.height.shape, dtype=np.int32)
    next_label = 0
    for level in np.unique(levels[hard]) if hard.any() else ():
        mask = hard & (levels == level)
        component, count = connected_components(mask)
        for index in range(1, count + 1):
            next_label += 1
            labels[component == index] = next_label
    return labels, next_label


def largest_plateau_area(grid, z_floor: float, tolerance: float) -> float:
    labels, count = plateau_map(grid, z_floor, tolerance)
    if count == 0:
        return 0.0
    sizes = np.bincount(labels.ravel())[1:]
    return float(sizes.max()) * grid.cell_area


def hard_plateau_stats(grid, z_floor: float, tolerance: float) -> dict:
    """Connected hard plateau area, largest and total."""
    from .diagnostics import SUPPORT_HARD

    labels, count = plateau_map(grid, z_floor, tolerance)
    hard_area = float(
        (grid.usable & (grid.support == SUPPORT_HARD)).sum()
    ) * grid.cell_area
    if count == 0:
        return {"largest": 0.0, "total": hard_area, "count": 0}
    sizes = np.bincount(labels.ravel())[1:]
    return {
        "largest": float(sizes.max()) * grid.cell_area,
        "total": hard_area,
        "count": int(count),
    }


__all__ = [
    "ALL_FAMILIES", "FAMILY_BRIDGE", "FAMILY_FLOOR", "FAMILY_SHELF",
    "FAMILY_WEDGE_STEP",
    "FAMILY_TERRACE", "FAMILY_WEDGE_BRIDGE", "ROLE_BRIDGE", "ROLE_TERRACE",
    "ROLE_WEDGE_BRIDGE", "bridge_anchors", "hard_plateau_stats", "hard_tops",
    "largest_plateau_area", "level_groups", "plateau_map", "terrace_anchors",
    "wedge_bridge_anchors",
]
