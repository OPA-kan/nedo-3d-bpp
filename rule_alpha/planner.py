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
    soft = sorted((p for p in profiles if p.is_soft),
                  key=lambda p: (min(o.dz for o in p.orientations), -volume(p), p.index))
    if has_priority_container and getattr(config, "priority_cargo_first", False):
        hard = [p for p in hard if p.is_prioritized] + [p for p in hard if not p.is_prioritized]
        return [p.index for p in hard] + [p.index for p in soft]
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
              z_cap: float | None):
    from wedge_rl.stack import covers_other_attribute

    model = board.model(container_idx)
    container = board.container(container_idx)
    wall = config.inclusion_clearance + config.anchor_slack
    bottom = _drop_height(container, model, x, y, orientation.dx, orientation.dy, orientation.dz)
    if bottom + orientation.dz > model.z_ceiling - wall + 1e-9:
        return None, "ceiling"
    if z_cap is not None and bottom + orientation.dz > z_cap + 1e-9:
        return None, "cap"
    if x - orientation.dx / 2.0 < model.x_limit_at_height(bottom) + wall - 1e-9:
        return None, "chamfer"
    box = AABB((x, y, bottom + orientation.dz / 2.0), (orientation.dx, orientation.dy, orientation.dz), ARCHETYPE)
    ok, why = layer1.validate(box, model, container, config)
    if ok and getattr(config, "no_cover_other_attribute", False) and covers_other_attribute(
            box, container, bool(profile.is_soft), bool(profile.is_prioritized)):
        ok, why = False, "covers-other-attribute"
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
              layout_index: int = 0) -> list:
    """Fills one container with the given items in layers of rows: rows from
    the back wall to the opening, each row from the left to the right, each
    layer on whatever the last one left (poses drop onto the packed tops);
    a pass over the floor is a layer, and passes repeat until one places
    nothing.  Every pose is checked by the validator, so the order in which
    the rows are built is an order the simulator can carry in.  Placed items
    are removed from ``items``."""
    model = board.model(container_idx)
    rect = model.floor_rect
    gap = config.settled_clearance + config.anchor_slack
    slack = config.anchor_slack
    wall = config.inclusion_clearance + slack
    x_right = rect.x_max - slack
    y_front = rect.y_min + slack
    # (back line, depth) of every row, shared by all layers of the container
    row_lines = row_lines if row_lines is not None else []
    # count first: the smallest box that fits a slot, and the layout with
    # the most boxes; otherwise the biggest and the most volume
    count_first = bool(getattr(config, "count_first", False))
    area_sign = 1.0 if count_first else -1.0

    def place(profile, orientation, x, y):
        reserve = agent._soft_headroom_reserve(board.containers) if not profile.is_soft else 0.0
        z_cap = model.z_ceiling - reserve if reserve > 0 else None
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
                for o in _flat_poses(profile):
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
        depths = sorted({round(side, 4) for p in pool for o in _flat_poses(p) for side in (o.dx, o.dy)}, reverse=True)
        found: dict[tuple, tuple] = {}
        budget = [4000]

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
                gained = float(len(row)) if count_first else sum(o.dx * o.dy * o.dz for _p, o in row)
                rows.append((d, row))
                search(pool2, y_left - d - gap, rows, volume + gained)
                rows.pop()
                if budget[0] <= 0:
                    return

        search(list(pool), rect.y_max - slack - y_front, [], 0.0)
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
                for o in _flat_poses(profile):
                    if o.dy <= depth + 1e-9 and o.dx <= width + 1e-9:
                        choices.append((row_dz is not None and abs(o.dz - row_dz) > 1e-6,
                                        abs(o.dy - depth) > 1e-6, area_sign * o.dx * o.dy, n, o, profile))
            if not choices:
                break
            choices.sort(key=lambda t: t[:4])
            box = None
            for _h, _w, _a, _n, o, profile in choices[:8]:
                box = try_slot(profile, o, x_cursor, y_back)
                if box is not None:
                    break
            if box is None and getattr(config, "plan_standing", True):
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
    while items and passes < 12 and time.perf_counter() < deadline:
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
            y_back = rect.y_max - slack
            for depth, _row in layout:
                row_lines.append((y_back, depth))
                y_back -= depth + gap
        for y_back, depth in row_lines:
            if time.perf_counter() >= deadline:
                break
            fill_row(y_back, depth, x_left)
        if log:
            log(f"  [plan] container {container_idx} pass {passes}: {len(planned) - before} placed, {len(items)} left")
        if len(planned) == before:
            break
    return row_lines


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
    orders = [v for v in re.split(r"[,+|]", str(getattr(config, "plan_variants", "after-hard,mixed,last"))) if v]
    layouts = max(1, int(getattr(config, "plan_layouts", 1)))
    variants = [(o, li) for li in range(layouts) for o in orders]
    scorer = getattr(agent, "plan_score", None)
    # Every variant gets the whole of what is left of the budget, one after
    # the other, and a variant the deadline cuts short counts only when no
    # variant finished.  v7 gave each of three layouts a third of the
    # budget: on the evaluation machine (about five times slower than
    # this one) every plan was cut before its soft rows and its priority
    # cargo, and the official soft and placement scores fell by a quarter
    # while the bench, with time to spare, had shown them rising.
    best = None
    best_partial = None
    started = time.perf_counter()
    longest = 0.0
    for variant, layout_index in variants:
        now = time.perf_counter()
        if best is not None and now + longest * 1.2 >= deadline:
            break
        t0 = now
        order, plan = _plan_once(agent, item_list, deadline, variant, log, layout_index=layout_index)
        complete = time.perf_counter() < deadline
        longest = max(longest, time.perf_counter() - t0)
        volume = sum(e["size"][0] * e["size"][1] * e["size"][2] for e in plan)
        score = scorer(plan) if scorer is not None else volume
        if log:
            log(f"  [plan] variant {variant}/layout {layout_index}: {len(plan)} planned, {volume:.3f} m^3, "
                f"score {score:.3f}, {'complete' if complete else 'CUT'}, {time.perf_counter() - started:.1f}s")
        entry = ((score, len(plan)), order, plan)
        if complete:
            if best is None or entry[0] > best[0]:
                best = entry
        elif best_partial is None or entry[0] > best_partial[0]:
            best_partial = entry
        if time.perf_counter() >= deadline:
            break
    chosen = best if best is not None else best_partial
    return chosen[1], chosen[2]


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
        if priority_idx:
            for ci in priority_idx:
                items = [p for p in remaining if p.is_prioritized]
                pack_rows(agent, board, ci, items, config, plan, planned, deadline, log, layout_index=layout_index)
                remaining = [p for p in remaining if p.index not in set(planned)]
        for ci in normal_idx or list(range(len(board.models))):
            items = [p for p in remaining if not (p.is_prioritized and priority_idx)]
            hard = [p for p in items if not p.is_soft]
            lines = pack_rows(agent, board, ci, hard, config, plan, planned, deadline, log, layout_index=layout_index)
            soft = [p for p in items if p.is_soft]
            pack_rows(agent, board, ci, soft, config, plan, planned, deadline, log, row_lines=lines)
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
        reserve = agent._soft_headroom_reserve(board.containers) if not profile.is_soft else 0.0
        chosen = None
        for container_idx in layer1.routing_order(profile, board, config):
            model = board.model(container_idx)
            container = board.container(container_idx)
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
    the validator on the board as it stands (settled, not as planned)."""
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
        box = None
        for dy in shifts:
            for dx in shifts:
                centre = (float(entry["center"][0]) + dx, float(entry["center"][1]) + dy, float(entry["center"][2]))
                candidate = AABB(centre, tuple(entry["size"]), ARCHETYPE)
                ok, why = layer1.validate(candidate, model, container, replay_config)
                if ok and getattr(config, "no_cover_other_attribute", False) and covers_other_attribute(
                        candidate, container, bool(profile.is_soft), bool(profile.is_prioritized)):
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
