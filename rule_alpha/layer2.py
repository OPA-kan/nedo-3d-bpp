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

**hole fill** -- put the box *into* a gap the floor layer could not close.
Layer 1 anchors are derived from the edges of what is already packed, and every
pose it offers is the flattest one; so a slot that is 0.55 m across and 0.30 m
deep never sees the 0.55 x 0.30 pose of a 0.30 x 0.55 box, because nothing ever
proposed that yaw.  Here the hole is found first and the pose is chosen to fit
it -- rotated 90 degrees when that is what fits -- and only the flattest tier
that fits is offered, so the box stays as horizontal as the gap allows.

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

from dataclasses import dataclass

import numpy as np

from ._reuse import packed_aabbs_local
from .geometry import ContainerModel, Rect, box_rect


FAMILY_FLOOR = "floor"
FAMILY_TERRACE = "terrace-extension"
FAMILY_BRIDGE = "plateau-merge"
FAMILY_WEDGE_BRIDGE = "wedge-bridge"
FAMILY_SHELF = "shelf"
FAMILY_WEDGE_STEP = "wedge-step"
FAMILY_HOLE_FILL = "hole-fill"
FAMILY_TYPED_CAP = "typed-cap"

ALL_FAMILIES = (
    FAMILY_FLOOR, FAMILY_SHELF, FAMILY_WEDGE_STEP, FAMILY_TERRACE,
    FAMILY_BRIDGE, FAMILY_WEDGE_BRIDGE, FAMILY_HOLE_FILL, FAMILY_TYPED_CAP,
)

ROLE_TERRACE = "terrace"
ROLE_BRIDGE = "bridge"
ROLE_WEDGE_BRIDGE = "wedge-bridge"
ROLE_HOLE_FILL = "hole-fill"
ROLE_TYPED_CAP = "typed-cap"


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
# Holes -- what one layer could not close
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Hole:
    """A pocket of resting surface that its neighbourhood stands above.

    On the floor that is a gap between boxes.  On top of the foundation it is a
    notch in the terrace.  Both want the same thing: something shaped like the
    gap, laid as flat as the gap will take.
    """

    rect: Rect
    """Largest axis-aligned rectangle that fits inside the pocket."""

    bottom_z: float
    """Height a box dropped into it would rest at."""

    area: float
    """Area of the whole pocket, which is >= ``rect.area``."""

    enclosure: float
    """Share of the pocket's rim that is wall or higher ground."""

    on_floor: bool


def _rim_enclosure(cells, grid, model: ContainerModel, level_z: float,
                   tolerance: float) -> float:
    """How walled-in a pocket is, counting the opening as open.

    The container's back and side walls, the chamfer, and any neighbouring
    cargo that stands higher all enclose.  The -Y opening does not: it is a
    door, and a grid cell beyond it is not a wall however much it looks like
    one to a mask.
    """
    rim = np.zeros_like(cells)
    rim[1:, :] |= cells[:-1, :]
    rim[:-1, :] |= cells[1:, :]
    rim[:, 1:] |= cells[:, :-1]
    rim[:, :-1] |= cells[:, 1:]
    rim &= ~cells
    if not rim.any():
        return 1.0  # the pocket is the whole grid; nothing borders it
    higher = grid.usable & (grid.height > level_z + tolerance)
    beyond_the_door = grid.yy < model.floor_rect.y_min
    wall = (~grid.usable) & ~beyond_the_door
    return float((rim & (wall | higher)).sum()) / float(rim.sum())


def _rect_cells(grid, x0: int, y0: int, r0: int, c0: int, r1: int, c1: int):
    """Boolean mask of one rectangle of the grid, in full-grid coordinates."""
    mask = np.zeros(grid.height.shape, dtype=bool)
    mask[x0 + r0: x0 + r1 + 1, y0 + c0: y0 + c1 + 1] = True
    return mask


def _rect_world(grid, x0: int, y0: int, r0: int, c0: int, r1: int, c1: int) -> Rect:
    half = grid.cell / 2.0
    return Rect(
        float(grid.xs[x0 + r0]) - half, float(grid.xs[x0 + r1]) + half,
        float(grid.ys[y0 + c0]) - half, float(grid.ys[y0 + c1]) + half,
    )


def surface_holes(grid, model: ContainerModel, config) -> list[Hole]:
    """Every pocket worth aiming a box at, most enclosed first.

    Two kinds, found the same way: bare floor with cargo around it, and a patch
    of hard top that the tops beside it overlook.  Both are levels of the same
    height map, so both fall out of one pass over the distinct heights.

    Within a level the unit is a *rectangle*, not a connected region.  On a
    half-packed board every scrap of bare floor is one connected component --
    the dead corner behind a box and the open middle are the same blob -- so
    asking whether that component is enclosed gets the only answer it can: no,
    and no pocket is ever found.  Peeling the largest rectangles off it in turn
    separates them.  The open middle is a big rectangle bordered by more free
    floor; the dead corner is a small one bordered by cargo on three sides; only
    the second is a hole.
    """
    from .diagnostics import (
        SUPPORT_HARD, connected_components, largest_rectangle_in_mask,
    )

    if not config.hole_fill_enabled:
        return []

    tolerance = config.plateau_height_tolerance
    z_floor = model.z_floor
    levels = np.round((grid.height - z_floor) / max(tolerance, 1e-6))

    layers: list[tuple[np.ndarray, float, bool]] = []
    free = grid.usable & ~grid.occupied
    if free.any():
        layers.append((free, z_floor, True))
    hard = grid.usable & grid.occupied & (grid.support == SUPPORT_HARD)
    if hard.any():
        for level in np.unique(levels[hard]):
            layers.append(
                (hard & (levels == level), z_floor + float(level) * tolerance, False)
            )

    max_rect_area = config.hole_fill_max_rect_share * grid.usable_area
    holes: list[Hole] = []
    for mask, level_z, on_floor in layers:
        if level_z + config.hole_fill_min_headroom > model.z_ceiling:
            continue
        labels, count = connected_components(mask)
        for index in range(1, count + 1):
            cells = labels == index
            if float(cells.sum()) * grid.cell_area < config.hole_fill_min_area:
                continue
            idx_x, idx_y = np.nonzero(cells)
            x0, y0 = int(idx_x.min()), int(idx_y.min())
            work = cells[x0: int(idx_x.max()) + 1, y0: int(idx_y.max()) + 1].copy()
            for _peel in range(config.hole_fill_rects_per_region):
                area_cells, (r0, c0, r1, c1) = largest_rectangle_in_mask(work)
                if area_cells <= 0:
                    break
                work[r0:r1 + 1, c0:c1 + 1] = False
                area = float(area_cells) * grid.cell_area
                if area < config.hole_fill_min_area:
                    break  # the peels only get smaller from here
                if area > max_rect_area:
                    continue  # room, not a hole -- but keep peeling for its lobes
                patch = _rect_cells(grid, x0, y0, r0, c0, r1, c1)
                enclosure = _rim_enclosure(patch, grid, model, level_z, tolerance)
                if enclosure < config.hole_fill_min_enclosure:
                    continue
                holes.append(
                    Hole(
                        rect=_rect_world(grid, x0, y0, r0, c0, r1, c1),
                        bottom_z=level_z, area=area, enclosure=enclosure,
                        on_floor=on_floor,
                    )
                )
    # Enclosure is a threshold, not a preference.  Ranking by it put 0.06 m^2
    # slivers -- perfectly sealed and too small for anything -- ahead of the
    # 0.27 m^2 pockets that could actually take a box, and the cap then threw
    # the useful ones away.
    holes.sort(key=lambda hole: (-hole.rect.area, -hole.enclosure))
    return holes[: config.hole_fill_max_holes]


def hole_anchors(hole: Hole, dx: float, dy: float,
                 gap: float) -> list[tuple[float, float]]:
    """Centres that seat the box in a corner of the pocket, then its middle.

    Corners first for the same reason a terrace is flush rather than centred:
    what is left over should stay in one piece.  Back and right come before
    front and left, which is the direction the hard foundation grows anyway.
    """
    rect = hole.rect
    inset = gap / 2.0
    left = rect.x_min + dx / 2.0 + inset
    right = rect.x_max - dx / 2.0 - inset
    front = rect.y_min + dy / 2.0 + inset
    back = rect.y_max - dy / 2.0 - inset
    if right < left or back < front:
        return []
    return [
        (right, back), (left, back), (right, front), (left, front),
        (0.5 * (left + right), back),
        (0.5 * (left + right), 0.5 * (front + back)),
    ]


def hole_fits(hole: Hole, dx: float, dy: float, gap: float) -> bool:
    return (
        dx + gap <= hole.rect.x_max - hole.rect.x_min + 1e-9
        and dy + gap <= hole.rect.y_max - hole.rect.y_min + 1e-9
    )


def flattest_fitting_tier(hole: Hole, orientations, gap: float, config):
    """The orientations to offer this pocket: the flattest tier that fits.

    Sorted by height, the poses fall into tiers of equal ``dz``; a 90-degree
    yaw is the *same* tier, which is exactly the rotation this family exists to
    offer.  Taking only the first tier that fits means a box is never stood on
    end in a gap a lying pose could have filled, and is stood up only where
    nothing flatter would go in at all.
    """
    fitting = [o for o in orientations if hole_fits(hole, o.dx, o.dy, gap)]
    if not fitting:
        return []
    best = min(o.dz for o in fitting)
    tier = [o for o in fitting if o.dz <= best + config.hole_fill_tier_tolerance]
    return sorted(tier, key=lambda o: -o.footprint)


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
    "ALL_FAMILIES", "FAMILY_BRIDGE", "FAMILY_FLOOR", "FAMILY_HOLE_FILL",
    "FAMILY_SHELF", "FAMILY_WEDGE_STEP",
    "FAMILY_TERRACE", "FAMILY_TYPED_CAP", "FAMILY_WEDGE_BRIDGE", "Hole",
    "ROLE_BRIDGE", "ROLE_HOLE_FILL", "ROLE_TERRACE", "ROLE_TYPED_CAP",
    "ROLE_WEDGE_BRIDGE", "bridge_anchors", "flattest_fitting_tier",
    "hard_plateau_stats", "hard_tops", "hole_anchors", "hole_fits",
    "largest_plateau_area", "level_groups", "plateau_map", "surface_holes",
    "terrace_anchors", "wedge_bridge_anchors",
]
