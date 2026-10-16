"""Task A offline planner: a greedy geometric packing of the whole manifest.

The ladder is an online policy: it builds terraces so that whatever arrives
next can still be carried in, and it stacks tall early.  With the manifest
in hand none of that is needed -- the order is ours -- and on the core-a
scenes it leaves the container with rugged tops that no remaining item
fits (a-c1-s0001: 31 of 41 placed, the ten soft items left with zero
validator-legal poses).

This planner places every item of the manifest, one after the other, at the
best legal pose under a fixed preference (``key``): the poses come from
``wedge_rl.stack.stack_candidates`` -- every anchor on the floor or on a
packed top that the analytic validator accepts, transport sweep included --
so the plan is feasible on the analytic model by construction.  The order
handed back is the plan's order; the online phase replays the plan pose by
pose, re-validated on the settled board, and falls back to the ladder
where a pose no longer fits.

Preferences (``config.offline_planner``):

* ``lowest``: lowest bottom, then deepest, then leftmost (bottom-left-back)
* ``walls``: deepest first, then lowest -- builds the load as walls from the
  back, so nothing placed later has to be carried over something taller
* ``band``: lowest layer band (``plan_band`` high), then deepest, then
  leftmost -- layers, filled back to front within a band
"""

from __future__ import annotations

import copy
import math
import dataclasses
import time

from . import classify as cls
from . import layer1
from .geometry import AABB

ARCHETYPE = "plan"


def _key(name: str, band: float):
    # the flattest pose is preferred at every level: a thin standing box is
    # the "deepest" pose at a wall and the first version stood every hard
    # box on its narrow face, which nothing can rest on
    def flat(c):
        return round(float(c.dims[2]), 2)

    if name == "walls":
        return lambda c, m: (-round(float(c.box.center[1]), 1), flat(c), round(c.bottom, 2),
                             round(float(c.box.center[0]), 2))
    if name == "band":
        return lambda c, m: (int((c.bottom - m.z_floor) / band + 1e-6), flat(c),
                             -round(float(c.box.center[1]), 2), round(float(c.box.center[0]), 2))
    return lambda c, m: (round(c.bottom, 2), flat(c), -round(float(c.box.center[1]), 2),
                         round(float(c.box.center[0]), 2))


def planning_order(profiles: list, config, has_priority_container: bool, priority: str = "mixed") -> list[int]:
    """Hard cargo first, the big boxes before the small; then the soft, the
    flattest first so the tall ones take what is left of the headroom.

    ``priority`` places the priority cargo: ``mixed`` (by size with the
    rest), ``after-hard`` (on top of the normal hard cargo, before the
    soft) or ``last``.  Nothing may be built on priority cargo but more
    priority cargo, so in a layout without a priority container it belongs
    on top -- which is also where it is reached first."""
    def volume(p):
        o = p.orientations[0]
        return o.dx * o.dy * o.dz

    sign = 1.0 if getattr(config, "count_first", False) else -1.0
    hard = sorted((p for p in profiles if not p.is_soft), key=lambda p: (sign * volume(p), p.index))
    if getattr(config, "plan_soft_count_first", False):
        soft = sorted((p for p in profiles if p.is_soft), key=lambda p: (volume(p), p.index))
    else:
        soft = sorted((p for p in profiles if p.is_soft),
                      key=lambda p: (min(o.dz for o in p.orientations), -volume(p), p.index))
    if (has_priority_container and getattr(config, "priority_cargo_first", False)
            and not (priority == "after-hard" and getattr(config, "plan_priority_on_top", False))):
        # (plan_priority_on_top: the after-hard variant keeps its order in
        # a priority container too, the priority cargo over the normal
        # hard rows, so the floor is not a priority layer nothing may
        # stand on)
        hard = [p for p in hard if p.is_prioritized] + [p for p in hard if not p.is_prioritized]
        return [p.index for p in hard] + [p.index for p in soft]
    if priority == "first":
        # the priority cargo before everything on every layout: on a
        # normal container nothing may rest on it, so it goes where the
        # rows start (the back), and a priority box placed is worth
        # about three soft boxes or ten hard boxes' fill
        return ([p.index for p in hard if p.is_prioritized] + [p.index for p in hard if not p.is_prioritized]
                + [p.index for p in soft if p.is_prioritized] + [p.index for p in soft if not p.is_prioritized])
    if priority == "after-hard":
        return ([p.index for p in hard if not p.is_prioritized] + [p.index for p in hard if p.is_prioritized]
                + [p.index for p in soft if not p.is_prioritized] + [p.index for p in soft if p.is_prioritized])
    if priority == "last":
        return ([p.index for p in hard if not p.is_prioritized] + [p.index for p in soft if not p.is_prioritized]
                + [p.index for p in hard if p.is_prioritized] + [p.index for p in soft if p.is_prioritized])
    return [p.index for p in hard] + [p.index for p in soft]


def _packed(container: dict):
    from ._reuse import packed_aabbs_local

    return packed_aabbs_local(container)


def _drop_height(container: dict, model, x: float, y: float, dx: float, dy: float, dz: float = 0.0) -> float:
    """The height a box with this footprint comes to rest at: the highest
    packed top under it (an overlap of a centimetre counts), else the floor;
    where a shelf covers the footprint and the box would not fit under it,
    the shelf's top (the ladder's shelf archetypes rest cargo there too)."""
    bottom = model.z_floor
    for b, _s, _p in _packed(container):
        if (min(x + dx / 2.0, float(b.maximum[0])) - max(x - dx / 2.0, float(b.minimum[0])) > 0.01
                and min(y + dy / 2.0, float(b.maximum[1])) - max(y - dy / 2.0, float(b.minimum[1])) > 0.01):
            bottom = max(bottom, float(b.maximum[2]))
    for shelf in getattr(model, "shelves", []) or []:
        if (min(x + dx / 2.0, float(shelf.maximum[0])) - max(x - dx / 2.0, float(shelf.minimum[0])) > 0.01
                and min(y + dy / 2.0, float(shelf.maximum[1])) - max(y - dy / 2.0, float(shelf.minimum[1])) > 0.01):
            if bottom + dz > float(shelf.minimum[2]) - 0.03 and bottom < float(shelf.maximum[2]):
                bottom = float(shelf.maximum[2])
    return bottom


def _flat_poses(profile) -> list:
    """The orientations with the smallest height, widest along x first."""
    dz = min(o.dz for o in profile.orientations)
    flat = [o for o in profile.orientations if abs(o.dz - dz) < 1e-9]
    return sorted(flat, key=lambda o: -o.dx)


def _standing_poses(profile) -> list:
    """The other orientations, the lowest first.  A flat third layer often
    cannot be carried in: the simulator lifts an item by less than its
    safety margin when the item's top comes within about 0.1 m of the
    mid-height "ceiling" (the shelf level, checked in every container),
    so a box whose top lands in that band collides with its own support
    on the way in.  Standing, the box clears the band."""
    dz = min(o.dz for o in profile.orientations)
    other = [o for o in profile.orientations if o.dz > dz + 1e-9]
    return sorted(other, key=lambda o: (o.dz, -o.dx))


def _try_pose(board, container_idx: int, profile, orientation, x: float, y: float, config,
              z_cap: float | None, bottom: float | None = None):
    from wedge_rl.stack import covers_other_attribute

    model = board.model(container_idx)
    container = board.container(container_idx)
    wall = config.inclusion_clearance + config.anchor_slack
    if bottom is None:
        bottom = _drop_height(container, model, x, y, orientation.dx, orientation.dy, orientation.dz)
    if bottom + orientation.dz > model.z_ceiling - wall + 1e-9:
        return None, "ceiling"
    if z_cap is not None and bottom + orientation.dz > z_cap + 1e-9:
        return None, "cap"
    if x - orientation.dx / 2.0 < model.x_limit_at_height(bottom) + wall - 1e-9:
        return None, "chamfer"
    box = AABB((x, y, bottom + orientation.dz / 2.0), (orientation.dx, orientation.dy, orientation.dz), ARCHETYPE)
    ok, why = layer1.validate(box, model, container, config)
    waive = bool(getattr(config, "plan_soft_floor_active", False)) and not profile.is_soft
    if ok and getattr(config, "no_cover_other_attribute", False) and covers_other_attribute(
            box, _cover_view(container, model, waive), bool(profile.is_soft), bool(profile.is_prioritized),
            shelves=model.shelves if getattr(config, "cover_veto_ignores_shelf", False) else None):
        ok, why = False, "covers-other-attribute"
    if ok and waive:
        ok, why = _soft_floor_unsunk_ok(box, model, container, config, why)
    if ok and bottom > model.z_floor + 1e-6:
        # the validator's rule (centre of mass inside the support) let a
        # soft box rest on 40 % of its footprint; in physics it tipped and
        # the episode ended.  A planned pose rests on most of its footprint.
        from . import stability

        needed = float(getattr(config, "plan_min_support_soft" if profile.is_soft else "plan_min_support", 0.0))
        if needed > 0.0:
            state = stability.evaluate(box, container, config)
            if state.contact_area < needed * orientation.dx * orientation.dy - 1e-9:
                ok, why = False, "support-ratio"
    return (box if ok else None), why


def pack_rows(agent, board: layer1.Board, container_idx: int, items: list, config, plan: list,
              planned: list, deadline: float, log=None, row_lines: list | None = None,
              layout_index: int = 0, deep_first: bool = False,
              y_top: float | None = None, y_bottom: float | None = None,
              floor_only: bool = False) -> list:
    """Fills one container with the given items in layers of rows: rows from
    the back wall to the opening, each row from the left to the right, each
    layer on whatever the last one left (poses drop onto the packed tops);
    a pass over the floor is a layer, and passes repeat until one places
    nothing.  Every pose is checked by the validator, so the order in which
    the rows are built is an order the simulator can carry in.  Placed items
    are removed from ``items``.  ``y_top`` / ``y_bottom`` narrow the floor's
    depth the rows are laid in (the typed-standing gallery's rows take the
    rest, ``pack_typed_gallery``)."""
    model = board.model(container_idx)
    rect = model.floor_rect
    gap = config.settled_clearance + config.anchor_slack
    slack = config.anchor_slack
    wall = config.inclusion_clearance + slack
    x_right = rect.x_max - slack
    y_front = rect.y_min + slack if y_bottom is None else max(rect.y_min + slack, float(y_bottom))
    y_start = rect.y_max - slack if y_top is None else min(rect.y_max - slack, float(y_top))
    # (back line, depth) of every row, shared by all layers of the container
    row_lines = row_lines if row_lines is not None else []
    # count first: the smallest box that fits a slot, and the layout with
    # the most boxes; otherwise the biggest and the most volume
    count_first = bool(getattr(config, "count_first", False))
    area_sign = 1.0 if count_first else -1.0
    # the poses a row is built from: flat, or -- once nothing flat fits
    # anywhere and plan_standing_rows is on -- standing, in rows of their
    # own over the flat layers (the mid-height transport band kills a flat
    # third layer; a standing box in a flat row's slot covers a third of
    # the row's depth, standing rows cover it all)
    pose_fn = _flat_poses
    flat_lines = None
    standing_cap = float(getattr(config, "plan_standing_rows_max_height", 10.0))

    def standing_fn(profile):
        # a box standing taller than the cap (a 0.75 x 0.56 x 0.27 box on
        # its side is 0.56 or 0.75 m tall) is height and a topple the
        # count does not pay for
        return [o for o in _standing_poses(profile) if o.dz <= standing_cap + 1e-9]

    def place(profile, orientation, x, y):
        reserve = agent._soft_headroom_reserve(board.containers, container_idx) if not profile.is_soft else 0.0
        z_cap = model.z_ceiling - reserve if reserve > 0 else None
        z_cap = _soft_floor_cap(board, container_idx, profile, orientation, x, y, config, z_cap)
        box, why = _try_pose(board, container_idx, profile, orientation, x, y, config, z_cap)
        if box is None:
            if log:
                log(f"    [plan] c{container_idx} item {profile.index} {orientation.dx}x{orientation.dy}x{orientation.dz} "
                    f"at ({x:+.2f},{y:+.2f}) cap {z_cap}: {why}")
            return None
        cand = _Pose(box, orientation, model.z_floor)
        placement = _placement(cand, 1, profile, container_idx, model)
        placement.step = len(planned) + 1
        board.apply(placement)
        planned.append(profile.index)
        items.remove(profile)
        plan.append({"step": len(planned), "index": profile.index, "container_idx": int(container_idx),
                     "orientation": int(orientation.index),
                     "center": [float(v) for v in box.center], "size": [float(v) for v in box.size],
                     "bottom": float(box.minimum[2]), "on_floor": bool(float(box.minimum[2]) <= model.z_floor + 1e-6),
                     "archetype": ARCHETYPE})
        return box

    def fill_row_plan(pool: list, depth: float, x_left: float) -> list:
        """Arithmetic fill of one row of the given depth from ``pool``
        (consumed): items whose flat side fits the depth, the ones of
        exactly that depth first, then the biggest; left to right."""
        x_cursor = x_left
        row = []
        while pool:
            width = x_right - x_cursor
            choices = []
            for n, profile in enumerate(pool):
                for o in pose_fn(profile):
                    if o.dy <= depth + 1e-9 and o.dx <= width + 1e-9:
                        choices.append((abs(o.dy - depth) > 1e-6, area_sign * o.dx * o.dy, n, o, profile))
            if not choices:
                break
            choices.sort(key=lambda t: t[:3])
            _w, _a, _n, o, profile = choices[0]
            row.append((profile, o))
            pool.remove(profile)
            x_cursor += o.dx + gap
        return row

    def best_layouts(pool: list, x_left: float, k: int = 1) -> list:
        """The ``k`` best sequences of rows (depth, items) over the floor's
        depth by volume, by a search over the row depths (the flat sides of
        the items) with the greedy row fill above; distinct in their row
        depths."""
        depths = sorted({round(side, 4) for p in pool for o in pose_fn(p) for side in (o.dx, o.dy)}, reverse=True)
        found: dict[tuple, tuple] = {}
        budget = [4000]
        # with plan_layout_layers a row is worth what it holds over its
        # layers up to its ceiling (the main shelf's underside where the
        # row runs under the shelf, else the ceiling under the soft
        # headroom reserve), not its floor layer alone: sized for the
        # floor layer's count, the rows took the smallest boxes' depth and
        # the bulk of the cargo never fitted a row (a-c1s-s0010: 17 of 41
        # planned, the 15 boxes of 0.65 x 0.45 refused by every 0.4 m row)
        layers = bool(getattr(config, "plan_layout_layers", False))
        reserve = agent._soft_headroom_reserve(board.containers, container_idx) if layers else 0.0
        wide_shelves = [s for s in (model.shelves or [])
                        if float(s.maximum[0]) - float(s.minimum[0]) > 0.5 * (rect.x_max - rect.x_min)]

        def row_zmax(y_top: float, d: float) -> float:
            zmax = model.z_ceiling - reserve - wall
            for s in wide_shelves:
                if float(s.minimum[1]) < y_top - 1e-9 and float(s.maximum[1]) > y_top - d + 1e-9 \
                        and float(s.minimum[2]) > model.z_floor + 0.1:
                    zmax = min(zmax, float(s.minimum[2]) - wall)
            return zmax

        def row_worth(row: list) -> float:
            return float(len(row)) if count_first else sum(o.dx * o.dy * o.dz for _p, o in row)

        def search(remaining: list, y_left: float, rows: list, volume: float):
            budget[0] -= 1
            key = tuple(d for d, _r in rows)
            if rows and volume > found.get(key, (0.0, []))[0]:
                found[key] = (volume, list(rows))
            if not remaining or budget[0] <= 0:
                return
            for d in depths:
                if d > y_left + 1e-9:
                    continue
                pool2 = list(remaining)
                row = fill_row_plan(pool2, d, x_left)
                if not row:
                    continue
                gained = row_worth(row)
                if layers:
                    height = model.z_floor + max(o.dz for _p, o in row)
                    zmax = row_zmax(y_front + y_left, d)
                    while pool2:
                        snapshot = list(pool2)
                        more = fill_row_plan(pool2, d, x_left)
                        if not more or height + max(o.dz for _p, o in more) > zmax + 1e-9:
                            pool2[:] = snapshot
                            break
                        gained += row_worth(more)
                        height += max(o.dz for _p, o in more)
                rows.append((d, row))
                search(pool2, y_left - d - gap, rows, volume + gained)
                rows.pop()
                if budget[0] <= 0:
                    return

        search(list(pool), y_start - y_front, [], 0.0)
        # a prefix of a longer sequence is not a different layout
        ranked = sorted(found.items(), key=lambda kv: -kv[1][0])
        out = []
        for key, (_v, rows) in ranked:
            if any(key == other[:len(key)] for other in (o[0] for o in out)):
                continue
            out.append((key, rows))
            if len(out) >= k:
                break
        return [rows for _key, rows in out]

    def try_slot(profile, orientation, x_cursor: float, y_back: float, max_bottom: float = math.inf):
        """The pose at the row's cursor, slid along the row and a little
        forward until it is legal: above the chamfer pocket there is
        nothing to rest on until the layer below begins, a deeper row below
        lifts a sliver of the footprint onto its edge, and a settled layer
        is never exactly where the plan put it.  A pose whose bottom would
        be above ``max_bottom`` is not tried."""
        x0 = x_cursor + orientation.dx / 2.0
        for dy_shift in (0.0, 0.05, 0.1, 0.15, 0.2):
            y = y_back - dy_shift - orientation.dy / 2.0
            if y - orientation.dy / 2.0 < y_front - 1e-9:
                break
            x = x0
            while x + orientation.dx / 2.0 <= x_right + 1e-9:
                bottom = _drop_height(board.container(container_idx), model, x, y,
                                      orientation.dx, orientation.dy, orientation.dz)
                x = max(x, model.x_limit_at_height(bottom) + wall + orientation.dx / 2.0)
                if x + orientation.dx / 2.0 > x_right + 1e-9:
                    break
                if bottom > max_bottom + 1e-9:
                    x += 0.05
                    continue
                box = place(profile, orientation, x, y)
                if box is not None:
                    return box
                x += 0.05
        return None

    def fill_row(y_back: float, depth: float, x_left: float) -> int:
        """One row, left to right, every pose validated: items whose flat
        side fits the row's depth; the height of the row's first box is
        preferred for the rest (a level row is what the next layer rests
        on), then the exact depth, then the biggest."""
        x_cursor = x_left
        row_dz = None
        count = 0
        while items and time.perf_counter() < deadline:
            width = x_right - x_cursor
            choices = []
            for n, profile in enumerate(items):
                for o in pose_fn(profile):
                    if o.dy <= depth + 1e-9 and o.dx <= width + 1e-9:
                        if floor_only and not _soft_floor_level(o.dz, row_dz, config):
                            continue
                        choices.append((row_dz is not None and abs(o.dz - row_dz) > 1e-6,
                                        abs(o.dy - depth) > 1e-6, area_sign * o.dx * o.dy, n, o, profile))
            if not choices:
                break
            choices.sort(key=lambda t: t[:4])
            box = None
            for _h, _w, _a, _n, o, profile in choices[:8]:
                box = try_slot(profile, o, x_cursor, y_back,
                               max_bottom=model.z_floor + 1e-6 if floor_only else math.inf)
                if box is not None:
                    break
            if (box is None and getattr(config, "plan_standing", True) and not floor_only
                    and not (getattr(config, "plan_standing_rows", False) and pose_fn is _flat_poses)):
                # nothing flat fits here (the mid-height band, most often):
                # a standing pose of the same items, lowest first
                standing = []
                for n, profile in enumerate(items):
                    for o in _standing_poses(profile):
                        if o.dy <= depth + 1e-9 and o.dx <= width + 1e-9:
                            standing.append((row_dz is not None and abs(o.dz - row_dz) > 1e-6, o.dz,
                                             -o.dx * o.dy, n, o, profile))
                standing.sort(key=lambda t: t[:4])
                standing_cap = float(getattr(config, "plan_standing_max_bottom", math.inf))
                for _h, _z, _a, _n, o, profile in standing[:8]:
                    box = try_slot(profile, o, x_cursor, y_back, max_bottom=standing_cap)
                    if box is not None:
                        break
            if box is None:
                break
            count += 1
            row_dz = float(box.size[2])
            x_cursor = float(box.maximum[0]) + gap
        return count

    passes = 0
    while items and passes < (1 if floor_only else 12) and time.perf_counter() < deadline:
        passes += 1
        before = len(planned)
        # where a row starts: the floor's left edge, so the layers stay in
        # line (the chamfer lets a higher box reach further left, but
        # nothing below would carry it); over the small shelf's top, its
        # left edge
        tops = [float(b.maximum[2]) for b, _s, _p in _packed(board.container(container_idx))]
        z_est = sum(tops) / len(tops) if tops else model.z_floor
        x_left = max(model.x_limit_at_height(z_est) + wall, rect.x_min)
        shelf = getattr(model, "small_shelf", None)
        if shelf is not None and z_est >= float(shelf.maximum[2]) - 1e-6:
            x_left = max(model.x_wall_min + wall, float(shelf.minimum[0]) + wall)
        if not row_lines:
            # the floor's rows come from the search; every later layer
            # keeps the same row lines, so its boxes rest on whole rows
            layouts = best_layouts(list(items), x_left, layout_index + 1)
            layout = layouts[min(layout_index, len(layouts) - 1)] if layouts else []
            y_back = y_start
            for depth, _row in layout:
                row_lines.append((y_back, depth))
                y_back -= depth + gap
            if floor_only:
                row_lines[:] = _soft_floor_lines(row_lines, rect, slack, config)
        if deep_first:
            # each row built up in layers before the next row is opened:
            # the priority cargo in its container takes the back rows to
            # the ceiling and leaves the front rows' floor to the rest
            for y_back, depth in row_lines:
                for _layer in range(12):
                    if not items or time.perf_counter() >= deadline:
                        break
                    if fill_row(y_back, depth, x_left) == 0:
                        break
        else:
            for y_back, depth in row_lines:
                if time.perf_counter() >= deadline:
                    break
                fill_row(y_back, depth, x_left)
        if log:
            log(f"  [plan] container {container_idx} pass {passes}: {len(planned) - before} placed, {len(items)} left"
                + (" (standing rows)" if pose_fn is not _flat_poses else ""))
        if len(planned) == before or deep_first:
            if (items and pose_fn is _flat_poses and getattr(config, "plan_standing_rows", False)
                    and getattr(config, "plan_standing", True) and not deep_first
                    and not any(p.is_soft for p in items)):
                pose_fn = standing_fn
                flat_lines = list(row_lines)
                row_lines.clear()
                continue
            break
    if flat_lines is not None:
        # the flat rows' lines are what the next pass (the soft cargo on
        # the hard rows' lines) expects
        row_lines[:] = flat_lines
    return row_lines


# ---------------------------------------------------------------------------
# The soft floor under the hard cargo (config.plan_soft_floor_under_count).
# On a dense manifest the plan places the hard cargo first and the soft
# boxes, the smallest items, find no room on top; under the count threshold
# the soft-floor variant lays them on the floor first, one storey in level
# rows from the back wall, and the hard rows ride on them.  The limits are
# the official simulator's (scripts/soft_floor_probe.py).

_SOFT_FLOOR_BAND = 0.06   # a soft box whose bottom is this close to the floor rests on it


def _flat_height(profile) -> float:
    return min(o.dz for o in profile.orientations)


def _soft_floor_eligible(profile, config) -> bool:
    return (bool(profile.is_soft) and not bool(profile.is_prioritized) and bool(profile.orientations)
            and _flat_height(profile) <= float(getattr(config, "plan_soft_floor_max_height", 0.30)) + 1e-9)


def _soft_floor_level(dz: float, row_dz, config) -> bool:
    """A soft-floor row is level: its boxes' heights within the tolerance of
    the row's first (a hard box bridging two heights tilts)."""
    if row_dz is None:
        return True
    return abs(dz - row_dz) <= float(getattr(config, "plan_soft_floor_level_tolerance", 0.03)) + 1e-9


def _soft_floor_lines(row_lines: list, rect, slack: float, config) -> list:
    """The soft floor's rows within ``plan_soft_floor_depth_share`` of the
    floor's depth from the back wall."""
    share = float(getattr(config, "plan_soft_floor_depth_share", 1.0))
    if share >= 1.0:
        return list(row_lines)
    depth = (rect.y_max - slack) - (rect.y_min + slack)
    y_limit = (rect.y_max - slack) - share * depth
    return [(y, d) for y, d in row_lines if y - d >= y_limit - 1e-9]


def _floor_soft_boxes(container: dict, model) -> list:
    """(packed item, local AABB) of the non-priority soft boxes on the floor."""
    from ._reuse import packed_aabbs_local

    out = []
    for packed, (b, soft, prio) in zip(container.get("packed_items", []), packed_aabbs_local(container)):
        if soft and not prio and float(b.minimum[2]) <= model.z_floor + _SOFT_FLOOR_BAND:
            out.append((packed, b))
    return out


def _cover_view(container: dict, model, waive: bool) -> dict:
    """The container as the cover veto reads it: with ``waive``, the soft
    boxes on the floor are left out (hard cargo may rest on the soft
    floor); the priority cargo and every other soft box still count."""
    if not waive:
        return container
    floor = {id(p) for p, _b in _floor_soft_boxes(container, model)}
    if not floor:
        return container
    view = dict(container)
    view["packed_items"] = [p for p in container.get("packed_items", []) if id(p) not in floor]
    return view


def _soft_floor_cap(board, container_idx: int, profile, orientation, x: float, y: float, config, z_cap):
    """The height cap of a hard pose over the soft floor while the
    soft-floor variant is planned (``plan_soft_floor_hard_max_top``)."""
    if not getattr(config, "plan_soft_floor_active", False) or profile.is_soft:
        return z_cap
    top = float(getattr(config, "plan_soft_floor_hard_max_top", 1.0))
    if top <= 0.0:
        return z_cap
    model = board.model(container_idx)
    for _p, b in _floor_soft_boxes(board.container(container_idx), model):
        if (min(x + orientation.dx / 2.0, float(b.maximum[0])) - max(x - orientation.dx / 2.0, float(b.minimum[0])) > 0.01
                and min(y + orientation.dy / 2.0, float(b.maximum[1])) - max(y - orientation.dy / 2.0, float(b.minimum[1])) > 0.01):
            return top if z_cap is None else min(z_cap, top)
    return z_cap


class _soft_floor_structure:
    """The soft floor carries load: the stability model's floor-share gate
    off and, with ``cap``, soft tops up to that height as structure."""

    def __init__(self, config, cap):
        self.cap = cap

    def __enter__(self):
        from . import stability

        self.saved = (stability.SOFT_STRUCTURE_MAX_TOP, stability.SOFT_STRUCTURE_FLOOR_SHARE)
        stability.SOFT_STRUCTURE_FLOOR_SHARE = 0.0
        if self.cap is not None:
            stability.SOFT_STRUCTURE_MAX_TOP = self.cap
        return self

    def __exit__(self, *exc):
        from . import stability

        stability.SOFT_STRUCTURE_MAX_TOP, stability.SOFT_STRUCTURE_FLOOR_SHARE = self.saved
        return False


def _soft_floor_group(floor: list, config) -> list:
    """The soft boxes of one height band (``plan_soft_floor_level_tolerance``
    wide) with the most footprint: the floor the hard rows ride on is
    level, since the analytic support reads contact within millimetres and
    a hard box over two heights rests on the taller alone (and in physics
    tilts: 2-4 degrees over 2 cm, 5-17 over 5 cm)."""
    if not floor:
        return []
    tol = float(getattr(config, "plan_soft_floor_level_tolerance", 0.005))
    best, best_area = [], -1.0
    for h in sorted({round(_flat_height(p), 4) for p in floor}):
        group = [p for p in floor if h - 1e-9 <= _flat_height(p) <= h + tol + 1e-9]
        area = sum(max(o.dx * o.dy for o in p.orientations if abs(o.dz - _flat_height(p)) < 1e-9) for p in group)
        if area > best_area + 1e-9:
            best, best_area = group, area
    return best


def _soft_floor_pass(agent, board, container_idx: int, items: list, config, plan: list, planned: list,
                     deadline: float, log=None) -> list:
    """The soft floor of one container: the eligible soft boxes, tallest
    first so the rows come out level and step down towards the door, in
    rows from the back wall, the floor alone.  Returns the items left."""
    floor = _soft_floor_group([p for p in items if _soft_floor_eligible(p, config)], config)
    if not floor:
        return items
    floor.sort(key=lambda p: (-round(_flat_height(p), 3),
                              -p.orientations[0].dx * p.orientations[0].dy * p.orientations[0].dz, p.index))
    before = len(plan)
    pack_rows(agent, board, container_idx, floor, config, plan, planned, deadline, log, floor_only=True)
    for entry in plan[before:]:
        entry["soft_floor"] = True
    _sink_soft_floor(board, container_idx, len(plan) - before, float(getattr(config, "plan_soft_floor_sink", 0.0)))
    if log:
        log(f"  [plan] container {container_idx} soft floor: {len(plan) - before} of "
            f"{sum(1 for p in items if _soft_floor_eligible(p, config))} soft boxes")
    placed = set(planned)
    return [p for p in items if p.index not in placed]


def _soft_floor_unsunk_ok(box, model, container: dict, config, why: str):
    """A hard pose over the soft floor is planned on the sunk tops
    (``plan_soft_floor_sink``) and must be legal as well where it lands if
    the soft boxes sink less: raised by the sink, read with the sink as
    contact tolerance.  The transport band under the shelf level is a step
    function of the pose's height, and a plan that cleared it by the sink
    alone missed at replay (a-hard-s0047, a-c1x60-s0002: the third layer's
    top 1.5 cm into the band)."""
    sink = float(getattr(config, "plan_soft_floor_sink", 0.0))
    if sink <= 0.0:
        return True, why
    floor = _floor_soft_boxes(container, model)
    if not any(min(float(box.maximum[0]), float(b.maximum[0])) - max(float(box.minimum[0]), float(b.minimum[0])) > 0.01
               and min(float(box.maximum[1]), float(b.maximum[1])) - max(float(box.minimum[1]), float(b.minimum[1])) > 0.01
               for _p, b in floor):
        return True, why
    from ._reuse import packed_aabbs_local

    def over_floor(b) -> bool:
        return any(min(float(b.maximum[0]), float(f.maximum[0])) - max(float(b.minimum[0]), float(f.minimum[0])) > 0.01
                   and min(float(b.maximum[1]), float(f.maximum[1])) - max(float(b.minimum[1]), float(f.minimum[1])) > 0.01
                   for _p, f in floor)

    # the board as it stands if the soft floor does not sink: the floor and
    # every box over it up by the sink
    packed = []
    for p, (b, _s, _pr) in zip(container.get("packed_items", []), packed_aabbs_local(container)):
        if over_floor(b):
            x, y, z = p["pos"]
            p = dict(p, pos=(x, y, float(z) + sink))
        packed.append(p)
    view = dict(container)
    view["packed_items"] = packed
    raised = AABB((float(box.center[0]), float(box.center[1]), float(box.center[2]) + sink),
                  tuple(float(v) for v in box.size), ARCHETYPE)
    ok, why2 = layer1.validate(raised, model, view, config)
    return (True, why) if ok else (False, "soft-floor-unsunk-" + str(why2))


def _sink_soft_floor(board, container_idx: int, count: int, sink: float) -> None:
    """The planning board's last ``count`` placements (the soft floor) moved
    ``sink`` down: the hard rows are planned on the tops the soft boxes
    settle to under them (the plan's entries keep the true poses)."""
    if sink <= 0.0 or count <= 0:
        return
    placements = list(board.placements[container_idx][-count:])
    for _ in range(count):
        board.undo_last(container_idx)
    for placement in placements:
        box = placement.box
        centre = (float(box.center[0]), float(box.center[1]), float(box.center[2]) - sink)
        board.apply(dataclasses.replace(placement, box=AABB(centre, tuple(float(v) for v in box.size), ARCHETYPE)))


def _mark_over_soft(plan: list, drop: float) -> int:
    """Every planned pose above a soft-floor box (its footprint over the
    box's, its bottom higher) replays with the soft floor's rules."""
    floor = [e for e in plan if e.get("soft_floor")]
    marked = 0
    for e in plan:
        if e.get("soft_floor"):
            continue
        cx, cy, _cz = e["center"]
        sx, sy, _sz = e["size"]
        for f in floor:
            if int(f["container_idx"]) != int(e["container_idx"]) or float(e["bottom"]) <= float(f["bottom"]) + 1e-6:
                continue
            fx, fy, _fz = f["center"]
            fsx, fsy, _fsz = f["size"]
            if (min(cx + sx / 2.0, fx + fsx / 2.0) - max(cx - sx / 2.0, fx - fsx / 2.0) > 0.01
                    and min(cy + sy / 2.0, fy + fsy / 2.0) - max(cy - sy / 2.0, fy - fsy / 2.0) > 0.01):
                e["over_soft"] = True
                e["replay_drop"] = float(drop)
                marked += 1
                break
    return marked


def soft_floor_yields(agent, plan: list, other: list) -> bool:
    """A soft-floor plan (played under the count gate) yields to another
    plan with more items: it bought its count with covered soft boxes, and
    the plan score's soft share must not keep it over a plan that places
    more (a-hard-s0019: the soft-floor plan's 59 items with 23 soft against
    the dry-run's 63 with 6)."""
    if not plan or not any(e.get("soft_floor") for e in plan):
        return False
    # only while the soft-floor plan does not hold the count itself: over
    # it the plan score decides as before (core-a, first CI round: three
    # c1 / c2p plans of 21-22 items over a threshold of 21 yielded to
    # dry-runs with 0-3 soft boxes, the suite's soft share 7.94 -> 7.60)
    try:
        threshold = agent._count_threshold()
    except Exception:
        threshold = None
    if threshold is not None and len(plan) >= threshold:
        return False
    return len(other) > len(plan)


def soft_floor_board_view(agent, containers: list) -> list:
    """The observation's containers as the online stages read them once a
    soft-floor plan plays (``plan_soft_floor_online``): the plan's soft
    floor boxes as hard cargo, so the cover rule does not refuse every pose
    over them and they carry load.  Unchanged otherwise."""
    plan_by_index = getattr(agent, "plan_by_index", None)
    if (not plan_by_index or getattr(agent, "plan_source", "") != "planner"
            or not getattr(agent.config, "plan_soft_floor_online", True)):
        return containers
    floor = {int(i) for i, e in plan_by_index.items() if e.get("soft_floor")}
    if not floor:
        return containers
    out = []
    for container in containers:
        packed = container.get("packed_items") or []
        if not any(int(p.get("index", -1)) in floor for p in packed):
            out.append(container)
            continue
        view = dict(container)
        view["packed_items"] = [dict(p, is_soft=False) if int(p.get("index", -1)) in floor else p for p in packed]
        out.append(view)
    return out


def _soft_floor_overrides(config) -> dict:
    """``plan_soft_floor_overrides`` parsed against the config's fields."""
    raw = str(getattr(config, "plan_soft_floor_overrides", "") or "")
    fields = {f.name: f.type for f in dataclasses.fields(config)}
    out = {}
    for pair in raw.split(";"):
        key, _eq, value = pair.strip().partition("=")
        if not key or key not in fields:
            continue
        low = value.strip().lower()
        if low in ("true", "false"):
            out[key] = low == "true"
            continue
        for cast in (int, float):
            try:
                out[key] = cast(value)
                break
            except ValueError:
                continue
        else:
            out[key] = value
    return out


def _soft_floor_variant(agent, item_list: list, deadline: float, variant: tuple, order: list, plan: list, log=None):
    """The soft-floor plan, planned when the chosen plan holds fewer than
    the count threshold plus ``plan_value_margin`` items, with the first
    variant's settings; it plays when it holds more items."""
    config = agent.config
    try:
        threshold = agent._count_threshold()
    except Exception:
        threshold = None
    if threshold is None:
        return order, plan
    gate = int(threshold) + int(getattr(config, "plan_value_margin", 2))
    if len(plan) >= gate or time.perf_counter() >= deadline:
        return order, plan
    name, layout_index, size_order, mode, _soft_structure, reserve = variant
    changes = {"plan_soft_floor_active": True, "soft_is_structure": True}
    if size_order is not None:
        changes["count_first"] = size_order == "small"
    if mode is not None:
        changes["plan_layout_layers"] = mode == "layers"
    if reserve is not None:
        changes["reserve_headroom_for_soft"] = reserve == "on"
    if not getattr(config, "plan_soft_floor_keep_reserve", False):
        changes["reserve_headroom_for_soft"] = False
    changes.update(_soft_floor_overrides(config))
    models = agent.board.models if getattr(agent, "board", None) is not None and agent.board.models else []
    z_floor = max((m.z_floor for m in models), default=0.04)
    # only the floor storey carries load in the plan
    cap = z_floor + float(getattr(config, "plan_soft_floor_max_height", 0.30)) + 0.03
    t0 = time.perf_counter()
    agent.config = dataclasses.replace(config, **changes)
    try:
        with _soft_floor_structure(config, cap):
            sf_order, sf_plan = _plan_once(agent, item_list, deadline, name, log, layout_index=layout_index)
    except Exception as exc:
        print(f"[plan] soft floor failed: {exc!r}", flush=True)
        return order, plan
    finally:
        agent.config = config
    if time.perf_counter() >= deadline:
        return order, plan
    marked = _mark_over_soft(sf_plan, float(getattr(config, "plan_soft_floor_replay_drop", 0.06)))
    n_floor = sum(1 for e in sf_plan if e.get("soft_floor"))
    take = len(sf_plan) > len(plan)
    if getattr(config, "plan_soft_floor_needs_gate", True) and len(sf_plan) < gate:
        # a soft-floor plan that does not secure the count on paper
        # replays to a crossing as rarely as the plan it would replace
        # and covers soft boxes for nothing (core-a, second CI round:
        # a-c1-s0012 planned 21 of a threshold of 21, placed 20, where
        # the plan's 19 had replayed to 21)
        take = False
    msg = (f"[plan] soft floor: {len(sf_plan)} planned ({n_floor} on the soft floor, {marked} over it) "
           f"against {len(plan)}, threshold {threshold}: {'taken' if take else 'kept the plan'} "
           f"({time.perf_counter() - t0:.1f}s)")
    if log:
        log("  " + msg)
    print(msg, flush=True)
    if take:
        agent.soft_floor_plan = {"planned": len(sf_plan), "base": len(plan), "floor": n_floor, "over": marked}
        return sf_order, sf_plan
    return order, plan


class _Pose:
    """A stack-candidate look-alike for ``_placement``."""

    def __init__(self, box: AABB, orientation, z_floor: float):
        self.box = box
        self.orientation = int(orientation.index)
        self.dims = (orientation.dx, orientation.dy, orientation.dz)
        self.bottom = float(box.minimum[2])
        self.on_floor = self.bottom <= z_floor + 1e-6
        self.gain = orientation.dx * orientation.dy * orientation.dz
        self.support_ratio = 1.0
        self.margin = 0.0


def plan_packing(agent, item_list: list[dict], deadline: float, log=None) -> tuple[list[int], list[dict]]:
    """Returns ``(order, plan)``: the planned items in planning order, then
    the items not planned (not reached before ``deadline``, or without a
    legal pose) in that same order; ``plan`` holds one entry per planned
    item with the settled pose.  Several orders of the priority cargo are
    planned within the deadline and the plan with the most volume kept."""
    config = agent.config
    import re

    # "+" as well as "," between variants: an arm spec's overrides are
    # themselves comma-separated
    split = r"[,+|;]" if getattr(config, "plan_variants_semicolon", False) else r"[,+|]"
    orders = [v for v in re.split(split, str(getattr(config, "plan_variants", "after-hard,mixed,last"))) if v]
    layouts = max(1, int(getattr(config, "plan_layouts", 1)))
    # the size order of the hard cargo as a variant too ("small": the
    # smallest first, count_first; "big": the biggest first): on the
    # physics suite the better of the two orders a scene places 0.4 items
    # more than the smallest-first order alone
    sizes = [s for s in re.split(r"[,+|]", str(getattr(config, "plan_size_orders", "") or "")) if s] or [None]
    # the layout scoring as a variant too ("floor": the floor layer's
    # count; "layers": what the rows hold over their layers): the layered
    # search gains 9 items on a shelf-container scene and loses 3-5 on the
    # two-container ones, so both are planned and the plan score chooses
    modes = [m for m in re.split(r"[,+|]", str(getattr(config, "plan_layout_variants", "") or "")) if m] or [None]
    # soft cargo as structure as a variant too ("off,on": the plan with
    # the soft gallery one layer deep first, then two deep): on the A
    # suite the two-deep plans hold 1.9 items and 0.18 of the soft share
    # more, on the hard A suite's larger manifests they trade the hard
    # cargo for soft and lose crossings (a-hard-s0041 74 -> 57 of 59), so
    # the two-deep plan plays only when it holds the count threshold plus
    # plan_value_margin and scores higher
    # ";" too: an arm spec's overrides are comma-separated, so the list
    # arrives as "off;on" (plan_variants, split on "," and "+" alone, has
    # run as the one variant "first;after-hard" -- neither order, the
    # size-mixed default -- since the arm specs took that form)
    softs = [s for s in re.split(r"[,+|;]", str(getattr(config, "plan_soft_structure_variants", "") or "")) if s] or [None]
    # the two-deep variant on manifests of at most this many containers
    # (hard A suite: level on one container, -2.9 and -3.6 items a scene
    # on two and three, where the two-deep plan replays 19 of 53 poses)
    max_containers = int(getattr(config, "plan_soft_structure_max_containers", 0) or 0)
    n_containers = len(agent.board.models) if getattr(agent, "board", None) is not None and agent.board.models else 1
    if max_containers and n_containers > max_containers:
        softs = [s for s in softs if s != "on"] or [None]
    # the soft headroom reserve as a variant too ("on;off"): the reserve
    # keeps the top layer for the soft cargo, and on the hard A manifests
    # the soft pass then fails to use it (uneven tops, the sweep, tall
    # soft boxes) while the hard rows stop under the cap (a-hard-s0013:
    # 15 781 cap refusals, 33 soft boxes unplanned, 52 planned of the 61
    # the threshold asks); the plan without the reserve plays only when
    # it holds the count threshold plus plan_value_margin
    reserves = [r for r in re.split(r"[,+|;]", str(getattr(config, "plan_reserve_variants", "") or "")) if r] or [None]
    variants = [(o, li, s, m, ss, rv) for rv in reserves for ss in softs for li in range(layouts) for m in modes for s in sizes for o in orders]
    scorer = getattr(agent, "plan_score", None)
    threshold = None
    if softs != [None] or reserves != [None] or getattr(config, "plan_alt_gate", ""):
        try:
            threshold = agent._count_threshold()
        except Exception:
            threshold = None
    gate = (threshold or 0) + int(getattr(config, "plan_value_margin", 2)) if threshold else 0
    # Every variant gets the whole of what is left of the budget, one after
    # the other, and a variant the deadline cuts short counts only when no
    # variant finished.  v7 gave each of three layouts a third of the
    # budget: on the evaluation machine (about five times slower than
    # this one) every plan was cut before its soft rows and its priority
    # cargo, and the official soft and placement scores fell by a quarter
    # while the bench, with time to spare, had shown them rising.
    best = None
    best_partial = None
    base_entry = None   # the first variant planned in full: the shipped form's plan
    early_secured = None  # config.plan_count_secure_early: the re-plan's pick after the first plan
    started = time.perf_counter()
    longest = 0.0
    from . import stability as _stability

    for variant, layout_index, size_order, mode, soft_structure, reserve in variants:
        now = time.perf_counter()
        if best is not None and now + longest * 1.2 >= deadline:
            break
        t0 = now
        changes = {}
        if size_order is not None:
            changes["count_first"] = size_order == "small"
        if mode is not None:
            changes["plan_layout_layers"] = mode == "layers"
        if reserve is not None:
            changes["reserve_headroom_for_soft"] = reserve == "on"
        saved_cap = _stability.SOFT_STRUCTURE_MAX_TOP
        saved_share = _stability.SOFT_STRUCTURE_FLOOR_SHARE
        if soft_structure is not None:
            on = soft_structure == "on"
            changes["soft_is_structure"] = on
            if on:
                # the gallery two deep whatever the online caps say; the
                # planner's candidates come from stack_candidates, which
                # drops soft structure when stack_soft_is_structure is off
                # (the online stack option's switch), so it is on here
                changes["stack_soft_is_structure"] = True
                # the soft rows laid out over the hard stack's top on their
                # own lines: with the hard rows' lines the two-deep plan
                # replays 44 of 61 poses on a-c2-s0005 (51 placed, 13
                # soft), with its own 56-59 placed and 19-22 soft
                changes["plan_soft_own_rows"] = True
                _stability.SOFT_STRUCTURE_MAX_TOP = None
                _stability.SOFT_STRUCTURE_FLOOR_SHARE = 0.0
        if changes:
            agent.config = dataclasses.replace(config, **changes)
        try:
            order, plan = _plan_once(agent, item_list, deadline, variant, log, layout_index=layout_index)
        finally:
            agent.config = config
            _stability.SOFT_STRUCTURE_MAX_TOP = saved_cap
            _stability.SOFT_STRUCTURE_FLOOR_SHARE = saved_share
        complete = time.perf_counter() < deadline
        longest = max(longest, time.perf_counter() - t0)
        volume = sum(e["size"][0] * e["size"][1] * e["size"][2] for e in plan)
        score = scorer(plan) if scorer is not None else volume
        if soft_structure == "on" and gate and len(plan) < gate:
            # a two-deep plan under the gate forfeits the four components
            # on the platform: it does not play
            score = -float("inf")
        if reserve == "off" and (not gate or len(plan) < gate):
            # the plan without the soft reserve plays only over the gate:
            # under it the reserve's soft placements are worth more
            score = -float("inf")
        if log:
            by_index = {int(i["index"]): i for i in item_list}
            n_soft = sum(1 for e in plan if by_index[int(e["index"])].get("is_soft"))
            n_prio = sum(1 for e in plan if by_index[int(e["index"])].get("is_prioritized"))
            log(f"  [plan] variant {variant}/layout {layout_index}/size {size_order}/mode {mode}/soft {soft_structure}/reserve {reserve}: {len(plan)} planned "
                f"(soft {n_soft}, priority {n_prio}), {volume:.3f} m^3, "
                f"score {score:.3f}, {'complete' if complete else 'CUT'}, {time.perf_counter() - started:.1f}s")
        entry = ((score, len(plan)), order, plan)
        if complete:
            if base_entry is None:
                base_entry = entry
                if (getattr(config, "plan_count_secure", False) and getattr(config, "plan_count_secure_early", False)
                        and early_secured is None):
                    # the re-plan right after the first plan, before the
                    # other variants take the budget (rule_alpha/count_secure.py)
                    from .count_secure import secure_count

                    early_secured = secure_count(agent, item_list, deadline, entry, longest, log)
            if best is None or entry[0] > best[0]:
                best = entry
        elif best_partial is None or entry[0] > best_partial[0]:
            best_partial = entry
        if time.perf_counter() >= deadline:
            break
    chosen = best if best is not None else best_partial
    if (getattr(config, "plan_alt_gate", "") == "base-under" and base_entry is not None
            and threshold is not None and len(base_entry[2]) >= threshold):
        # the alternatives (the reserve off, the priority on top, the
        # other orders) play only where the first variant's plan is under
        # the count threshold: where it crosses, the shipped plan stands
        # and the sample suite's soft and priority shares with it
        chosen = base_entry
    if early_secured is not None:
        from .count_secure import prefer_secured

        chosen = prefer_secured(agent, item_list, chosen, early_secured)
    elif getattr(config, "plan_count_secure", False) and time.perf_counter() < deadline:
        # under the count threshold plus plan_value_margin: the manifest
        # planned again around a count frame (rule_alpha/count_secure.py)
        from .count_secure import secure_count

        chosen = secure_count(agent, item_list, deadline, chosen, longest, log)
    if getattr(config, "plan_typed_standing", False) and chosen is not None:
        # under the count gate: the typed-standing plans (the count
        # frame's soft and priority cargo standing on the floor first)
        chosen = plan_typed_standing(agent, item_list, deadline, chosen, orders[0] if orders else "mixed", log)
    order, plan = chosen[1], chosen[2]
    if getattr(config, "plan_soft_floor_under_count", False) and plan:
        order, plan = _soft_floor_variant(agent, item_list, deadline, variants[0], order, plan, log)
    if getattr(config, "plan_soft_after_hard_rows", False) and plan:
        # every container's hard rows before any soft gallery: a decline
        # ends the episode, and with the two-deep soft gallery of the
        # first container played before the second container's rows,
        # a soft block that misses its supports ends the episode with
        # the second container empty (a-hard-s0041: 74 -> 43, the
        # second container 33 -> 0)
        by_index = {int(i["index"]): i for i in item_list}
        planned = [int(e["index"]) for e in sorted(plan, key=lambda e: e["step"])]
        planned_set = set(planned)
        # (a soft floor goes with the hard rows it carries)
        floor_set = {int(e["index"]) for e in plan if e.get("soft_floor")}
        hard = [i for i in planned if not by_index.get(i, {}).get("is_soft") or i in floor_set]
        soft = [i for i in planned if by_index.get(i, {}).get("is_soft") and i not in floor_set]
        step_of = {idx: k + 1 for k, idx in enumerate(hard + soft)}
        for e in plan:
            e["step"] = step_of[int(e["index"])]
        order = hard + soft + [i for i in order if i not in planned_set]
    return order, plan


def _plan_once(agent, item_list: list[dict], deadline: float, priority: str, log=None,
               layout_index: int = 0) -> tuple[list[int], list[dict]]:
    from wedge_rl.stack import stack_candidates

    config = agent.config
    name = str(getattr(config, "offline_planner", "lowest"))
    key = _key(name, float(getattr(config, "plan_band", 0.22)))
    containers = copy.deepcopy(agent.board.containers)
    for container in containers:
        container.setdefault("packed_items", [])
    board = layer1.Board(containers, config)
    by_index = {int(item["index"]): item for item in item_list}
    profiles = {p.index: p for p in (cls.classify_item(int(i["index"]), i, config) for i in item_list)}
    has_priority = any(m.is_prioritized for m in board.models)
    order = planning_order(list(profiles.values()), config, has_priority, priority)

    planned: list[int] = []
    left: list[int] = []
    plan: list[dict] = []
    longest = 0.0
    if name == "rows":
        # rows first, container by container along the routing rules: the
        # priority container takes the priority cargo, the normal ones the
        # rest (hard, then soft on top); what the rows leave goes through the
        # greedy pose search below
        remaining = [profiles[i] for i in order]
        priority_idx = [i for i, m in enumerate(board.models) if m.is_prioritized]
        normal_idx = [i for i, m in enumerate(board.models) if not m.is_prioritized]
        priority_lines: dict[int, list] = {}
        if priority_idx:
            for ci in priority_idx:
                items = [p for p in remaining if p.is_prioritized]
                priority_lines[ci] = pack_rows(agent, board, ci, items, config, plan, planned, deadline, log,
                                               layout_index=layout_index,
                                               deep_first=bool(getattr(config, "plan_priority_deep_first", False)))
                remaining = [p for p in remaining if p.index not in set(planned)]
        for ci in normal_idx or list(range(len(board.models))):
            items = [p for p in remaining if not (p.is_prioritized and priority_idx)]
            if getattr(config, "plan_soft_floor_active", False):
                # the soft floor first (config.plan_soft_floor_under_count)
                items = _soft_floor_pass(agent, board, ci, items, config, plan, planned, deadline, log)
            hard = [p for p in items if not p.is_soft]
            lines = pack_rows(agent, board, ci, hard, config, plan, planned, deadline, log, layout_index=layout_index)
            soft = [p for p in items if p.is_soft]
            # the soft cargo's rows: its own layout over the hard stack's
            # top (plan_soft_own_rows) or the hard rows' lines, which are
            # sized for hard boxes twice as deep as a soft one and waste
            # half of every row on it
            soft_lines = None if getattr(config, "plan_soft_own_rows", False) else lines
            pack_rows(agent, board, ci, soft, config, plan, planned, deadline, log, row_lines=soft_lines)
            remaining = [p for p in remaining if p.index not in set(planned)]
        if priority_idx and getattr(config, "plan_normal_in_priority_container", False):
            # the priority container's spare rows take the normal hard cargo
            # the normal containers left (the rule penalises priority cargo
            # in a normal container and cargo of another attribute on top
            # of priority cargo -- which the pose check refuses -- not
            # normal cargo beside it; soft-only cargo never enters it)
            for ci in priority_idx:
                hard = [p for p in remaining if not p.is_soft and not p.is_prioritized]
                pack_rows(agent, board, ci, hard, config, plan, planned, deadline, log,
                          row_lines=priority_lines.get(ci))
                remaining = [p for p in remaining if p.index not in set(planned)]
        order = [p.index for p in remaining]
        key = _key("walls", 0.22)
    for n, index in enumerate(order):
        now = time.perf_counter()
        if now + longest >= deadline:
            left.extend(order[n:])
            break
        t0 = now
        profile = profiles[index]
        item = by_index[index]
        chosen = None
        for container_idx in layer1.routing_order(profile, board, config):
            model = board.model(container_idx)
            container = board.container(container_idx)
            reserve = agent._soft_headroom_reserve(board.containers, container_idx) if not profile.is_soft else 0.0
            z_top = model.z_ceiling - reserve if reserve > 0 else None
            cands = stack_candidates(model, container, config, profile, max_candidates=10 ** 6,
                                     mass=float(item.get("mass", 0.0)), z_top=z_top)
            if cands:
                best = min(cands, key=lambda c: key(c, model))
                chosen = (container_idx, model, best, len(cands))
                break
        longest = max(longest, time.perf_counter() - t0)
        if chosen is None:
            left.append(index)
            if log:
                log(f"  [plan] item {index} has no legal pose -> unplanned")
            continue
        container_idx, model, cand, count = chosen
        placement = _placement(cand, count, profile, container_idx, model)
        placement.step = len(planned) + 1
        board.apply(placement)
        planned.append(index)
        plan.append({"step": len(planned), "index": index, "container_idx": int(container_idx),
                     "orientation": int(cand.orientation),
                     "center": [float(v) for v in cand.box.center], "size": [float(v) for v in cand.box.size],
                     "bottom": float(cand.bottom), "on_floor": bool(cand.on_floor), "archetype": ARCHETYPE})
    return planned + left, plan


def _placement(cand, count: int, profile, container_idx: int, model) -> layer1.Placement:
    orientation = next(o for o in profile.orientations if o.index == cand.orientation)
    surface = "floor" if cand.on_floor else "item"
    return layer1.Placement(
        profile=profile, orientation=orientation, container_idx=container_idx, box=cand.box,
        surface=surface, surface_name=surface, role=cls.ROLE_NONE, archetype=ARCHETYPE,
        reason=f"plan: {cand.gain:.4f} m^3 at {cand.bottom:.2f} m among {count} poses",
        features={"volume": cand.gain, "support_ratio": cand.support_ratio, "margin": cand.margin},
        container_is_prioritized=bool(model.is_prioritized), container_has_shelf=bool(model.shelves),
        layer=1 if cand.on_floor else 2,
    )


def replay(agent, board: layer1.Board, pool_profiles: list, plan_by_index: dict) -> layer1.Decision | None:
    """The planned pose of the first pool item that has one and still passes
    the validator on the board as it stands (settled, not as planned).  A
    soft-floor plan (config.plan_soft_floor_under_count) replays with the
    soft floor carrying load whatever its share of the floor."""
    if not any(e.get("over_soft") for e in plan_by_index.values()):
        return _replay(agent, board, pool_profiles, plan_by_index)
    with _soft_floor_structure(agent.config, None):
        return _replay(agent, board, pool_profiles, plan_by_index)


def _replay(agent, board: layer1.Board, pool_profiles: list, plan_by_index: dict) -> layer1.Decision | None:
    from wedge_rl.stack import covers_other_attribute

    config = agent.config
    # the plan's own order first: with a look-ahead of several items the
    # pool holds the next few planned poses, and a later one placed early
    # can take the room an earlier one needs
    queue = sorted(pool_profiles, key=lambda pp: plan_by_index.get(int(pp[1].index), {}).get("step", 10 ** 9))
    for pool_index, profile in queue:
        entry = plan_by_index.get(int(profile.index))
        if entry is None:
            continue
        container_idx = int(entry["container_idx"])
        if container_idx >= len(board.models):
            continue
        model = board.model(container_idx)
        container = board.container(container_idx)
        # the plan's gaps are the validator's clearance plus half a
        # millimetre; a settled neighbour a millimetre off makes the pose
        # illegal as planned, and once one pose is missed the ladder's
        # improvisation breaks the rest of the plan (a-c2-s0002: two of 47
        # planned poses replayed).  So the pose is checked with the
        # clearance the simulator itself asks (plus a guard), and slid by
        # up to ``plan_replay_nudge`` to clear what has drifted.
        clearance = min(config.settled_clearance, float(getattr(config, "plan_replay_clearance", 0.02)))
        replay_config = dataclasses.replace(config, settled_clearance=clearance,
                                            transport_clearance=config.settled_clearance)
        nudge = float(getattr(config, "plan_replay_nudge", 0.02))
        shifts = sorted({0.0, nudge / 2.0, -nudge / 2.0, nudge, -nudge}, key=abs)
        # the planned height, and the height the box comes to rest at on
        # the board as it settled (config.plan_replay_drop): a soft box
        # under load settles a centimetre or two lower than planned, and
        # the pose planned on its top then floats above the contact
        # tolerance and misses -- on a-hard-s0041 the two-deep plan
        # replayed 19 of 53 poses that way and the episode ended in the
        # soft block before the second container's rows were reached
        drop = float(getattr(config, "plan_replay_drop", 0.0))
        if entry.get("over_soft"):
            # a pose of the soft-floor plan (config.plan_soft_floor_under_count)
            drop = max(drop, float(entry.get("replay_drop", 0.0)))
            # the soft boxes sink by their load, 1-4 cm and unevenly, so
            # the tops a pose bridges are read within a wider tolerance
            tolerance = max(float(config.contact_tolerance),
                            float(getattr(config, "plan_soft_floor_contact_tolerance", 0.0)))
            replay_config = dataclasses.replace(replay_config, soft_is_structure=True, contact_tolerance=tolerance)
        size = tuple(entry["size"])
        planned_z = float(entry["center"][2])
        heights = [planned_z]
        if drop > 0.0:
            rest = _drop_height(container, model, float(entry["center"][0]), float(entry["center"][1]),
                                float(size[0]), float(size[1]), float(size[2])) + float(size[2]) / 2.0
            if rest < planned_z - 1e-4 and planned_z - rest <= drop:
                heights.append(rest)
            elif entry.get("over_soft") and planned_z + 1e-4 < rest <= planned_z + drop:
                # the soft floor sank less than planned (plan_soft_floor_sink)
                heights.append(rest)
        box = None
        for dy in shifts:
            for dx in shifts:
                candidate = None
                for z in heights:
                    centre = (float(entry["center"][0]) + dx, float(entry["center"][1]) + dy, z)
                    candidate = AABB(centre, size, ARCHETYPE)
                    ok, why = layer1.validate(candidate, model, container, replay_config)
                    if ok:
                        break
                if not ok:
                    continue
                if getattr(config, "no_cover_other_attribute", False) and covers_other_attribute(
                        candidate, _cover_view(container, model, bool(entry.get("over_soft"))),
                        bool(profile.is_soft), bool(profile.is_prioritized),
                        shelves=model.shelves if getattr(config, "cover_veto_ignores_shelf", False) else None):
                    ok = False
                if ok:
                    box = candidate
                    break
            if box is not None:
                break
        if box is None:
            agent.plan_misses += 1
            continue
        orientation = next(o for o in profile.orientations if o.index == int(entry["orientation"]))
        surface = "floor" if entry.get("on_floor") else "item"
        placement = layer1.Placement(
            profile=profile, orientation=orientation, container_idx=container_idx, box=box,
            surface=surface, surface_name=surface, role=cls.ROLE_NONE, archetype=ARCHETYPE,
            reason=f"plan step {entry.get('step', 0)}: replayed",
            features={}, container_is_prioritized=bool(model.is_prioritized),
            container_has_shelf=bool(model.shelves), layer=1 if entry.get("on_floor") else 2,
        )
        candidate = layer1.Candidate(
            box=box, profile=profile, orientation=orientation, container_idx=container_idx,
            surface=surface, surface_name=surface, role=cls.ROLE_NONE, family=ARCHETYPE,
            features={}, archetypes={ARCHETYPE},
        )
        decision = layer1.Decision(placement=placement, candidate_counts={ARCHETYPE: 1}, veto_counts={},
                                   considered=1, ladder=[ARCHETYPE], survivors=[candidate], chosen=candidate)
        return pool_index, decision
    return None


def online_row_lines(model, config, depths: list[float]) -> list[tuple[float, float]]:
    """Fixed row lines for the online rows policy: the given depths laid
    from the back wall to the opening as far as the floor's depth allows."""
    rect = model.floor_rect
    gap = config.settled_clearance + config.anchor_slack
    slack = config.anchor_slack
    y_front = rect.y_min + slack
    lines = []
    y_back = rect.y_max - slack
    if not depths:
        # "auto": the set of class depths that uses the most of this
        # floor's depth, a 0.56 m row (the largest class lies flat in no
        # other) first, the deeper second row on a tie.  The fixed
        # "0.56,0.45,0.4" fits two rows in a 1.38 m floor and leaves 0.32
        # m at the front that no hard box uses; 0.56 + 0.45 + 0.30 fits.
        import itertools

        usable = (rect.y_max - slack) - y_front
        classes = [0.56, 0.45, 0.40, 0.35, 0.30]
        best = None
        for n in range(1, 5):
            for combo in itertools.combinations_with_replacement(classes, n):
                combo = sorted(combo, reverse=True)
                used = sum(combo) + gap * (n - 1)
                if used > usable + 1e-9:
                    continue
                key = (1 if combo[0] >= 0.56 - 1e-9 else 0, round(used, 3), combo[1] if n > 1 else 0.0)
                if best is None or key > best[0]:
                    best = (key, combo)
        depths = best[1] if best else []
    for depth in depths:
        if y_back - depth < y_front - 1e-9:
            continue
        lines.append((y_back, float(depth)))
        y_back -= depth + gap
    return lines


def online_row_pose(board, container_idx: int, profile, config, row_lines: list, z_cap: float | None = None,
                    standing: bool = True):
    """The item's pose on the fixed row lines: the lowest legal pose, then
    the deepest row, then the leftmost -- so the floor of every row fills
    before anything is stacked and the rows stay aligned for the layers.
    Flat poses first; a standing pose only where no flat one is legal."""
    model = board.model(container_idx)
    rect = model.floor_rect
    slack = config.anchor_slack
    wall = config.inclusion_clearance + slack
    x_right = rect.x_max - slack
    x_left = max(model.x_limit_at_height(model.z_floor) + wall, rect.x_min)
    container = board.container(container_idx)

    order = str(getattr(config, "online_row_order", "lowest"))
    staircase = order == "staircase"
    # the staircase: each row's tallest top and the height of the boxes on
    # its top level, from the packed boxes whose centre lies in the row
    row_top, row_dz = {}, {}
    if staircase:
        for b, _s, _p in _packed(container):
            cy = float(b.center[1])
            for row_index, (y_back, depth) in enumerate(row_lines):
                if y_back - depth - 1e-6 <= cy <= y_back + 1e-6:
                    top = float(b.maximum[2])
                    if top > row_top.get(row_index, -1.0) + 1e-6:
                        row_top[row_index] = top
                        row_dz[row_index] = float(b.size[2])
                    break

    def poses(orientations):
        found = []
        for row_index, (y_back, depth) in enumerate(row_lines):
            for o in orientations:
                if o.dy > depth + 1e-9:
                    continue
                y = y_back - o.dy / 2.0
                x = x_left + o.dx / 2.0
                while x + o.dx / 2.0 <= x_right + 1e-9:
                    bottom = _drop_height(container, model, x, y, o.dx, o.dy, o.dz)
                    if staircase and row_index > 0:
                        # a row never rises above the row behind it: an item
                        # is carried in at its own height plus the lift, and
                        # a taller front row closes every level behind it
                        behind = row_top.get(row_index - 1, model.z_floor)
                        if bottom + o.dz > behind + 0.02:
                            x += 0.05
                            continue
                    box, why = _try_pose(board, container_idx, profile, o, x, y, config, z_cap)
                    if box is not None:
                        if staircase:
                            # the row whose top level is this box's own height
                            # keeps its tops level for the layer above
                            mismatch = abs(o.dz - row_dz.get(row_index, o.dz))
                            found.append(((round(bottom, 3), round(mismatch, 3), row_index, round(x, 3)), box, o))
                        else:
                            found.append(((round(bottom, 3), row_index, round(x, 3)), box, o))
                    x += 0.05
        return found

    found = poses(_flat_poses(profile))
    if not found and standing:
        found = poses(_standing_poses(profile))
    if not found:
        return None, None
    if staircase:
        found.sort(key=lambda t: t[0])
        return found[0][1], found[0][2]
    if order == "deep-first":
        # the back row built up before the next is opened: an item travels
        # in at its own height plus the lift, so a tall box in a front row
        # closes every level behind it; a staircase falling towards the
        # door never closes anything (v18 + lowest-first rows: 13 of 41 on
        # c-c1-s0001 with the back row one layer high behind 1.2 m towers
        # in the front row)
        found.sort(key=lambda t: (t[0][1], t[0][0], t[0][2]))
    else:
        found.sort(key=lambda t: t[0])
    return found[0][1], found[0][2]


_MODEL_CONTAINER: dict = {}


def board_container(model):
    return _MODEL_CONTAINER.get(id(model))


def online_layers_key(profile, model, config):
    """The online layer policy's preference over ``stack_candidates``.

    Hard cargo that other cargo may rest on: flat poses before standing
    ones whatever the height, then a pose resting on most of its
    footprint, then the lowest layer band, then the deepest, then the
    leftmost -- the floor fills back to front before anything is stacked,
    the layers stay level, and the front never rises above the back (the
    transport path from the opening passes over it; an item is carried
    only 0.08 m up, so a box at the front blocks every floor pose behind
    it, which is why nothing goes to the front before the back is full).

    Cargo nothing else may rest on (soft; priority where no priority
    container takes it): the highest well-supported top first, then the
    deepest -- above the hard stacks, where the column it kills is
    shortest.
    """
    band = float(getattr(config, "online_layer_band", 0.25))
    support_ok = float(getattr(config, "online_layer_support", 0.85))
    blocking = profile.is_soft or (profile.is_prioritized and not model.is_prioritized)

    def flat(c):
        return 0 if abs(float(c.dims[2]) - min(c.dims)) < 1e-6 else 1

    def supported(c):
        return 0 if c.on_floor or float(getattr(c, "support_ratio", 1.0)) >= support_ok else 1

    def band_of(c):
        return int((c.bottom - model.z_floor) / band + 1e-6)

    shelves = list(getattr(model, "shelves", None) or [])

    def on_shelf(c):
        # a shelf's top carries the cargo nothing may rest on: the room
        # above a shelf is the least the hard stacks want
        for sh in shelves:
            if abs(float(sh.maximum[2]) - float(c.bottom)) < 0.02 and \
                    float(sh.minimum[0]) <= float(c.box.center[0]) <= float(sh.maximum[0]) and \
                    float(sh.minimum[1]) <= float(c.box.center[1]) <= float(sh.maximum[1]):
                return 0
        return 1

    if not blocking:
        # the band before the support: a well-supported pose five layers
        # up ranked before a 70 %-supported one on the second layer, and
        # the policy built towers over a floor 73 % covered (c-c2-s0012,
        # 39 against the ladder's 50)
        return lambda c: (flat(c), band_of(c), supported(c),
                          -round(float(c.box.center[1]), 2), round(float(c.box.center[0]), 2))

    container = board_container(model)
    packed = list(_packed(container)) if container is not None else []

    def on_same(c):
        # on cargo of its own attribute (soft on soft, priority on
        # priority is free): a column of it in one place kills one column
        # for the hard stacks, not one per box
        for b, so, pr in packed:
            if abs(float(b.maximum[2]) - float(c.bottom)) > 0.02:
                continue
            if (min(float(c.box.maximum[0]), float(b.maximum[0])) - max(float(c.box.minimum[0]), float(b.minimum[0])) > 0.05
                    and min(float(c.box.maximum[1]), float(b.maximum[1])) - max(float(c.box.minimum[1]), float(b.minimum[1])) > 0.05):
                if (profile.is_soft and so) or (profile.is_prioritized and pr and not so):
                    return 0
        return 1

    # else the highest top, the deepest, soft to the left and priority to
    # the right (on an empty floor that is the back corner; a floor pose
    # at the front would block every floor pose behind it)
    x_side = 1.0 if profile.is_soft else -1.0
    return lambda c: (flat(c), supported(c), on_shelf(c), on_same(c), -band_of(c),
                      -round(float(c.box.center[1]), 2), x_side * round(float(c.box.center[0]), 2))


def online_shelf_pose(board, container_idx: int, profile, config, standing: bool = False):
    """The lowest, deepest, leftmost legal pose of the item on one of the
    container's shelf tops (or on what already stands there): the shelf
    gallery for the cargo nothing may rest on.  ``stack_candidates`` has
    no shelf anchors, so the tops are scanned here on a 5 cm grid."""
    model = board.model(container_idx)
    shelves = list(getattr(model, "shelves", None) or [])
    if not shelves:
        return None, None
    container = board.container(container_idx)
    wall = config.inclusion_clearance + config.anchor_slack
    found = []
    orientations = list(_flat_poses(profile)) + (list(_standing_poses(profile)) if standing else [])
    for sh in shelves:
        x0, x1 = max(float(sh.minimum[0]), model.x_wall_min) + wall, float(sh.maximum[0]) - wall
        y0, y1 = float(sh.minimum[1]) + wall, float(sh.maximum[1]) - wall
        top = float(sh.maximum[2])
        for o in orientations:
            if o.dx > x1 - x0 + 1e-9 or o.dy > y1 - y0 + 1e-9:
                continue
            y = y1 - o.dy / 2.0
            while y - o.dy / 2.0 >= y0 - 1e-9:
                x = x0 + o.dx / 2.0
                while x + o.dx / 2.0 <= x1 + 1e-9:
                    bottom = max(top, _drop_height(container, model, x, y, o.dx, o.dy, o.dz))
                    if bottom >= top - 1e-6:
                        box, why = _try_pose(board, container_idx, profile, o, x, y, config, None, bottom=bottom)
                        if box is not None:
                            found.append(((round(bottom, 3), -round(y, 3), round(x, 3)), box, o))
                            if bottom <= top + 1e-6:
                                # the deepest, leftmost pose on the shelf itself: nothing beats it
                                return box, o
                    x += 0.05
                y -= 0.05
    if not found:
        return None, None
    found.sort(key=lambda t: t[0])
    return found[0][1], found[0][2]


# the official SKU mix: (length, width, height, mass, soft, weight); the
# weights sum to 41, so the expected 41-item manifest is the mix itself
SKU_MIX = [
    (0.55, 0.40, 0.24, 8, False, 13), (0.65, 0.45, 0.25, 13, False, 11), (0.75, 0.56, 0.27, 18, False, 4),
    (0.50, 0.40, 0.40, 10, True, 2), (0.45, 0.30, 0.20, 5, True, 2), (0.65, 0.35, 0.23, 12, True, 5),
    (0.60, 0.30, 0.25, 7, True, 4),
]


def mix_row_lines(agent, board: layer1.Board, container_idx: int, config, seconds: float = 3.0) -> list:
    """Row lines for a container from the planner's own layout search over
    the expected manifest (the SKU mix, 41 items), on a scratch copy of the
    container: the layout a Task A plan would build for a typical stream.
    On a-c1-s0001 the manifest's rows were 0.65 m deep (the 0.65 x 0.45
    boxes across, three a row, six on the floor), a depth the class-depth
    sets never offer."""
    import copy

    from . import classify as cls

    items = []
    index = 10 ** 6
    for l, w, h, mass, soft, weight in SKU_MIX:
        for _ in range(weight):
            items.append(cls.classify_item(index, {"index": index, "length": l, "width": w, "height": h, "mass": mass,
                                                   "is_soft": soft, "is_prioritized": False}, config))
            index += 1
    hard = [p for p in items if not p.is_soft]
    scratch = layer1.Board(copy.deepcopy(board.containers), config)
    lines: list = []
    pack_rows(agent, scratch, container_idx, hard, config, [], [], time.perf_counter() + seconds, row_lines=lines)
    return lines


# -- the typed-standing plan (config.plan_typed_standing) ----------------------
#
# On a dense manifest the ordinary plan places the hard cargo first and the
# soft cargo last, and the soft boxes -- the smallest items of the manifest
# -- find no room on the hard stacks' tops (the mid-height transport band
# ends the flat layers at about 0.94 m, the soft headroom reserve keeps the
# hard rows under the cap, and the soft rows on the uneven tops place 1 of 21
# on a-c1x60-s0002): the count falls short.  The typed-standing plan puts
# the soft and priority cargo of the count frame (the smallest items, the
# priority cargo always) on the floor first, standing on their smallest face
# in rows against a wall, and lays the hard rows in the rest of the floor.


def count_frame(profiles: list, size: int) -> set:
    """The indices of the count frame: every priority item, then the
    smallest items by volume (any class) until ``size`` items are in."""
    def volume(p):
        o = p.orientations[0]
        return o.dx * o.dy * o.dz

    prio = [p for p in profiles if p.is_prioritized]
    rest = sorted((p for p in profiles if not p.is_prioritized), key=lambda p: (volume(p), p.index))
    return {p.index for p in prio} | {p.index for p in rest[:max(0, int(size) - len(prio))]}


def _gallery_poses(profile, mode: str, max_top: float) -> list:
    """The gallery's orientations of an item: the tallest pose under
    ``max_top`` (the smallest face down), the shallow side along y first;
    in a ``tower`` gallery a soft item's flat poses (its tower is stacked
    from them)."""
    fits = [o for o in profile.orientations if o.dz <= max_top + 1e-9]
    if not fits:
        return []
    if mode == "tower" and profile.is_soft:
        dz = min(o.dz for o in fits)
    else:
        dz = max(o.dz for o in fits)
    return sorted((o for o in fits if abs(o.dz - dz) < 1e-9), key=lambda o: (o.dy, o.dx))


def _tower_height(profile, orientation, mode: str) -> int:
    """How many items of the class a slot of the gallery holds: one, or in
    a ``tower`` gallery as many flat soft boxes as stack while the
    supporting top stays under the soft structure cap."""
    if mode != "tower" or not profile.is_soft:
        return 1
    from . import stability

    cap = stability.SOFT_STRUCTURE_MAX_TOP
    if cap is None:
        return 4
    return 1 + int(max(0.0, float(cap)) / max(orientation.dz, 1e-6) + 1e-9)


def _class_key(profile) -> tuple:
    o = profile.orientations[0]
    return (tuple(sorted((round(o.dx, 3), round(o.dy, 3), round(o.dz, 3)))), bool(profile.is_soft),
            bool(profile.is_prioritized))


def _commit_pose(board, container_idx: int, profile, orientation, box, plan: list, planned: list, items: list):
    model = board.model(container_idx)
    cand = _Pose(box, orientation, model.z_floor)
    placement = _placement(cand, 1, profile, container_idx, model)
    placement.step = len(planned) + 1
    board.apply(placement)
    planned.append(profile.index)
    items.remove(profile)
    plan.append({"step": len(planned), "index": profile.index, "container_idx": int(container_idx),
                 "orientation": int(orientation.index),
                 "center": [float(v) for v in box.center], "size": [float(v) for v in box.size],
                 "bottom": float(box.minimum[2]), "on_floor": bool(float(box.minimum[2]) <= model.z_floor + 1e-6),
                 "archetype": ARCHETYPE})


def pack_typed_gallery(agent, board: layer1.Board, container_idx: int, items: list, config, plan: list,
                       planned: list, deadline: float, log=None, mode: str = "stand", max_rows: int = 2,
                       y_top: float | None = None, y_bottom: float | None = None) -> float | None:
    """The typed-standing gallery: ``items`` (consumed as placed) in up to
    ``max_rows`` rows from ``y_top`` (default: the back wall) towards the
    opening, each row left to right.  ``stand``: every box on its smallest
    face, its top under ``plan_typed_standing_max_top``.  ``tower``: the
    soft boxes flat, every row's floor laid first (the soft floor share the
    support rule asks), then towers of the same class on each base while
    the supporting top stays under the soft structure cap; the priority
    boxes stand.  A row's depth is the one that holds the most items per
    metre of depth; the priority cargo is taken first.  Returns the y of
    the gallery's front edge (None when nothing was placed)."""
    model = board.model(container_idx)
    rect = model.floor_rect
    gap = config.settled_clearance + config.anchor_slack
    slack = config.anchor_slack
    wall = config.inclusion_clearance + slack
    x_right = rect.x_max - slack
    y_front = rect.y_min + slack if y_bottom is None else max(rect.y_min + slack, float(y_bottom))
    y_back = rect.y_max - slack if y_top is None else min(rect.y_max - slack, float(y_top))
    x_left = max(model.x_limit_at_height(model.z_floor) + wall, rect.x_min)
    max_top = float(getattr(config, "plan_typed_standing_max_top", 0.7))
    stand_cap = model.z_floor + max_top
    step = 0.02
    edge = None
    bases: list = []   # (box, orientation, class key) of every floor slot
    refusals: dict = {}

    def poses(p):
        return _gallery_poses(p, mode, max_top)

    def row_count(depth: float) -> int:
        pool = list(items)
        cursor, n = x_left, 0
        while pool:
            width = x_right - cursor
            fit = [(o.dx, k, o) for k, p in enumerate(pool) for o in poses(p)
                   if o.dy <= depth + 1e-9 and o.dx <= width + 1e-9]
            if not fit:
                break
            dx, k, o = min(fit, key=lambda t: t[:2])
            p = pool.pop(k)
            key = _class_key(p)
            same = [q for q in pool if _class_key(q) == key][:_tower_height(p, o, mode) - 1]
            for q in same:
                pool.remove(q)
            cursor += dx + gap
            n += 1 + len(same)
        return n

    def attempt(profile, o, x: float, y: float, z_cap):
        box, why = _try_pose(board, container_idx, profile, o, x, y, config, z_cap)
        if box is None:
            refusals[why] = refusals.get(why, 0) + 1
        return box

    def slide(profile, o, x_cursor: float, y_line: float):
        y = y_line - o.dy / 2.0
        if y - o.dy / 2.0 < y_front - 1e-9:
            return None
        x = x_cursor + o.dx / 2.0
        cap = None if (mode == "tower" and profile.is_soft) else stand_cap
        while x + o.dx / 2.0 <= x_right + 1e-9:
            if time.perf_counter() >= deadline:
                return None
            box = attempt(profile, o, x, y, cap)
            if box is not None:
                return box
            x += step
        return None

    def fill(y_line: float, depth: float) -> int:
        cursor, n = x_left, 0
        while items and time.perf_counter() < deadline:
            width = x_right - cursor
            choices = [(not p.is_prioritized, abs(o.dy - depth) > 1e-6, o.dx, k, o, p)
                       for k, p in enumerate(items) for o in poses(p)
                       if o.dy <= depth + 1e-9 and o.dx <= width + 1e-9]
            if not choices:
                break
            choices.sort(key=lambda t: t[:4])
            box = None
            for _p, _e, _w, _k, o, p in choices[:8]:
                box = slide(p, o, cursor, y_line)
                if box is not None:
                    _commit_pose(board, container_idx, p, o, box, plan, planned, items)
                    bases.append((box, o, _class_key(p), p))
                    break
            if box is None:
                break
            n += 1
            cursor = float(box.maximum[0]) + gap
        return n

    for _row in range(max(0, int(max_rows))):
        if not items or time.perf_counter() >= deadline:
            break
        depths = sorted({round(o.dy, 4) for p in items for o in poses(p)})
        ranked = []
        for d in depths:
            if y_back - d < y_front - 1e-9:
                continue
            n = row_count(d)
            if n:
                ranked.append((-n / (d + gap), -n, d))
        if not ranked:
            break
        ranked.sort()
        depth = ranked[0][2]
        placed = fill(y_back, depth)
        if log:
            log(f"  [typed] container {container_idx} row at y {y_back:+.2f} depth {depth:.2f}: {placed} on the floor, "
                f"{len(items)} gallery items left")
        if not placed:
            break
        edge = y_back - depth
        y_back = edge - gap
    if mode == "tower":
        # the towers: each soft base takes boxes of its own class on top,
        # a layer over all bases at a time
        tops = {id(b): b for b, _o, _k, _p in bases}
        for _layer in range(5):
            stacked = 0
            for n, (box, o, key, p0) in enumerate(bases):
                if not p0.is_soft or time.perf_counter() >= deadline:
                    continue
                top = tops[id(box)]
                if _layer + 1 >= _tower_height(p0, o, mode):
                    continue
                same = [q for q in items if _class_key(q) == key]
                if not same:
                    continue
                q = same[0]
                oq = next((oo for oo in q.orientations if abs(oo.dx - o.dx) < 1e-9 and abs(oo.dy - o.dy) < 1e-9
                           and abs(oo.dz - o.dz) < 1e-9), None)
                if oq is None:
                    continue
                new = attempt(q, oq, float(top.center[0]), float(top.center[1]), None)
                if new is None:
                    continue
                _commit_pose(board, container_idx, q, oq, new, plan, planned, items)
                tops[id(box)] = new
                stacked += 1
            if log:
                log(f"  [typed] container {container_idx} tower layer {_layer + 2}: {stacked} placed, {len(items)} left")
            if not stacked:
                break
    if log and refusals:
        log(f"  [typed] container {container_idx} gallery refusals: " + ", ".join(
            f"{k} {v}" for k, v in sorted(refusals.items(), key=lambda kv: -kv[1])))
    return edge


def _least_footprint_key(c, m):
    """Deepest first (by the decimetre, so nothing placed later is carried
    over it), then the smallest footprint (the box on its smallest face),
    then the lowest, then the leftmost."""
    return (-round(float(c.box.center[1]), 1), round(float(c.dims[0]) * float(c.dims[1]), 3), round(c.bottom, 2),
            round(float(c.box.center[0]), 2))


def _plan_tail(agent, board, profiles: dict, by_index: dict, order: list, plan: list, planned: list,
               deadline: float, log=None, least_footprint: bool = False) -> list:
    """The greedy pose search of ``_plan_once`` over what the rows left
    (``order``), deepest first then lowest (``least_footprint``: then the
    smallest footprint); returns the unplanned."""
    from wedge_rl.stack import stack_candidates

    config = agent.config
    key = _least_footprint_key if least_footprint else _key("walls", 0.22)
    left: list[int] = []
    longest = 0.0
    for n, index in enumerate(order):
        now = time.perf_counter()
        if now + longest >= deadline:
            left.extend(order[n:])
            break
        t0 = now
        profile = profiles[index]
        item = by_index[index]
        chosen = None
        for container_idx in layer1.routing_order(profile, board, config):
            model = board.model(container_idx)
            container = board.container(container_idx)
            reserve = agent._soft_headroom_reserve(board.containers, container_idx) if not profile.is_soft else 0.0
            z_top = model.z_ceiling - reserve if reserve > 0 else None
            cands = stack_candidates(model, container, config, profile, max_candidates=10 ** 6,
                                     mass=float(item.get("mass", 0.0)), z_top=z_top)
            if cands:
                best = min(cands, key=lambda c: key(c, model))
                chosen = (container_idx, model, best, len(cands))
                break
        longest = max(longest, time.perf_counter() - t0)
        if chosen is None:
            left.append(index)
            continue
        container_idx, model, cand, count = chosen
        placement = _placement(cand, count, profile, container_idx, model)
        placement.step = len(planned) + 1
        board.apply(placement)
        planned.append(index)
        plan.append({"step": len(planned), "index": index, "container_idx": int(container_idx),
                     "orientation": int(cand.orientation),
                     "center": [float(v) for v in cand.box.center], "size": [float(v) for v in cand.box.size],
                     "bottom": float(cand.bottom), "on_floor": bool(cand.on_floor), "archetype": ARCHETYPE})
    return left


def _plan_typed_once(agent, item_list: list[dict], deadline: float, priority: str, gate: int, at: str = "back",
                     mode: str = "stand", rows: int = 2, log=None,
                     with_priority: bool | None = None) -> tuple[list[int], list[dict]]:
    """One typed-standing plan: per normal container, the count frame's
    soft and priority cargo in the gallery (``pack_typed_gallery``) against
    the back wall (``at`` ``back``: braced by the wall behind and the first
    hard row in front) or at the opening (``front``: the hard rows first,
    the gallery in front of them, open on its front side), the hard rows in
    the rest of the floor, then the soft cargo left on the hard rows and
    the greedy pose search over what remains.  The priority container
    (if any) is planned as ``_plan_once`` plans it."""
    config = agent.config
    containers = copy.deepcopy(agent.board.containers)
    for container in containers:
        container.setdefault("packed_items", [])
    board = layer1.Board(containers, config)
    by_index = {int(item["index"]): item for item in item_list}
    profiles = {p.index: p for p in (cls.classify_item(int(i["index"]), i, config) for i in item_list)}
    has_priority = any(m.is_prioritized for m in board.models)
    order = planning_order(list(profiles.values()), config, has_priority, priority)
    frame = count_frame(list(profiles.values()), gate)
    if with_priority is None:
        with_priority = bool(getattr(config, "plan_typed_standing_priority", True))
    planned: list[int] = []
    plan: list[dict] = []
    remaining = [profiles[i] for i in order]
    priority_idx = [i for i, m in enumerate(board.models) if m.is_prioritized]
    normal_idx = [i for i, m in enumerate(board.models) if not m.is_prioritized] or list(range(len(board.models)))
    priority_lines: dict[int, list] = {}
    for ci in priority_idx:
        items = [p for p in remaining if p.is_prioritized]
        priority_lines[ci] = pack_rows(agent, board, ci, items, config, plan, planned, deadline, log,
                                       deep_first=bool(getattr(config, "plan_priority_deep_first", False)))
        remaining = [p for p in remaining if p.index not in set(planned)]
    gallery = [p for p in remaining if p.index in frame
               and (p.is_soft or (with_priority and p.is_prioritized and not priority_idx))]
    # the priority cargo first (nothing but priority may rest on it, so it
    # is worth the most standing), then the smallest standing footprint
    gallery.sort(key=lambda p: (not p.is_prioritized,
                                min((o.dx * o.dy for o in _gallery_poses(p, mode, 10.0)), default=9.0), p.index))
    share = int(math.ceil(len(gallery) / max(1, len(normal_idx))))
    gap = config.settled_clearance + config.anchor_slack
    for ci in normal_idx:
        done = set(planned)
        g = [p for p in gallery if p.index not in done][:share]
        items = [p for p in remaining if p.index not in done and not (p.is_prioritized and priority_idx)]
        g_set = {p.index for p in g}
        hard = [p for p in items if not p.is_soft and p.index not in g_set]
        if at == "top":
            # no floor gallery: the hard rows over the whole floor, then the
            # gallery's items at their least-footprint legal pose anywhere
            # (standing on the hard rows' tops, where the flat soft rows
            # find no room)
            lines = pack_rows(agent, board, ci, hard, config, plan, planned, deadline, log)
            _plan_tail(agent, board, profiles, by_index, [p.index for p in g], plan, planned, deadline, log,
                       least_footprint=True)
        elif at == "front":
            # the gallery's depth from a scratch plan at the back wall, the
            # hard rows behind it, then the gallery in front of them
            model = board.model(ci)
            scratch = layer1.Board(copy.deepcopy(board.containers), config)
            edge = pack_typed_gallery(agent, scratch, ci, list(g), config, [], [], deadline, None, mode, rows)
            y_line = None
            if edge is not None:
                depth = (model.floor_rect.y_max - config.anchor_slack) - edge
                y_line = model.floor_rect.y_min + config.anchor_slack + depth
            lines = pack_rows(agent, board, ci, hard, config, plan, planned, deadline, log,
                              y_bottom=None if y_line is None else y_line + gap)
            if y_line is not None:
                pack_typed_gallery(agent, board, ci, g, config, plan, planned, deadline, log, mode, rows, y_top=y_line)
        else:
            edge = pack_typed_gallery(agent, board, ci, g, config, plan, planned, deadline, log, mode, rows)
            lines = pack_rows(agent, board, ci, hard, config, plan, planned, deadline, log,
                              y_top=None if edge is None else edge - gap)
        done = set(planned)
        soft = [p for p in items if p.is_soft and p.index not in done]
        soft_lines = None if getattr(config, "plan_soft_own_rows", False) else lines
        pack_rows(agent, board, ci, soft, config, plan, planned, deadline, log, row_lines=soft_lines)
        remaining = [p for p in remaining if p.index not in set(planned)]
    if priority_idx and getattr(config, "plan_normal_in_priority_container", False):
        for ci in priority_idx:
            hard = [p for p in remaining if not p.is_soft and not p.is_prioritized]
            pack_rows(agent, board, ci, hard, config, plan, planned, deadline, log, row_lines=priority_lines.get(ci))
            remaining = [p for p in remaining if p.index not in set(planned)]
    left = _plan_tail(agent, board, profiles, by_index, [p.index for p in remaining], plan, planned, deadline, log)
    return planned + left, plan


def plan_typed_standing(agent, item_list: list[dict], deadline: float, base, priority: str, log=None):
    """config.plan_typed_standing: when the ordinary plan (``base``, an
    entry ``((score, count), order, plan)``) holds fewer than the count
    threshold plus ``plan_value_margin`` items, the typed-standing plans of
    ``plan_typed_standing_variants`` ("<at>-<mode>-<rows>[-soft|-prio]
    [-noreserve]", e.g. "back-stand-2") are planned while the budget lasts, and the plan
    that holds the count, then scores the highest, is returned (``base``
    when none beats it; ``plan_typed_standing_force``: the best typed plan
    whatever the base holds)."""
    config = agent.config
    try:
        threshold = agent._count_threshold()
    except Exception:
        threshold = None
    if threshold is None or base is None:
        return base
    if getattr(config, "plan_typed_standing_no_priority_container", False) and any(
            m.is_prioritized for m in agent.board.models):
        return base
    gate = int(threshold) + int(getattr(config, "plan_value_margin", 2))
    force = bool(getattr(config, "plan_typed_standing_force", False))
    if len(base[2]) >= gate and not force:
        return base
    import re

    scorer = getattr(agent, "plan_score", None)
    specs = [s for s in re.split(r"[,+|;]", str(getattr(config, "plan_typed_standing_variants", "") or "")) if s]

    def rank(entry):
        return (len(entry[2]) >= gate, entry[0])

    best, longest = (None if force else base), 0.0
    for spec in specs:
        parts = spec.split("-")
        at = parts[0] if parts and parts[0] in ("back", "front", "top") else "back"
        mode = parts[1] if len(parts) > 1 and parts[1] in ("stand", "tower") else "stand"
        rows = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 2
        tokens = set(parts[3:])
        with_priority = True if "prio" in tokens else (False if "soft" in tokens else None)
        t0 = time.perf_counter()
        if t0 + 1.2 * longest >= deadline:
            break
        if "noreserve" in tokens:
            # the hard rows to the ceiling: the gallery holds the soft cargo
            agent.config = dataclasses.replace(config, reserve_headroom_for_soft=False)
        try:
            order, plan = _plan_typed_once(agent, item_list, deadline, priority, gate, at, mode, rows, log,
                                           with_priority=with_priority)
        finally:
            agent.config = config
        longest = max(longest, time.perf_counter() - t0)
        if time.perf_counter() >= deadline:
            # cut short: not a plan to play
            break
        volume = sum(e["size"][0] * e["size"][1] * e["size"][2] for e in plan)
        score = scorer(plan) if scorer is not None else volume
        entry = ((score, len(plan)), order, plan)
        if log:
            by_index = {int(i["index"]): i for i in item_list}
            n_soft = sum(1 for e in plan if by_index[int(e["index"])].get("is_soft"))
            n_prio = sum(1 for e in plan if by_index[int(e["index"])].get("is_prioritized"))
            log(f"  [typed] {spec}: {len(plan)} planned (soft {n_soft}, priority {n_prio}) against the gate {gate} "
                f"(base {len(base[2])}), {volume:.3f} m^3, score {score:.3f}")
        if best is None or rank(entry) > rank(best):
            best = entry
    return best if best is not None else base
