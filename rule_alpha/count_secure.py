"""Task A count-secured planning (``config.plan_count_secure``).

On a dense manifest (one container, 50-110 items, the manifest 0.8-1.7 of
the container's volume) the row planner places the hard cargo smallest
first, then the priority cargo, then the soft cargo, and the hard cargo
alone overfills the container: the soft boxes, the smallest items of the
manifest, never get a turn and the episode ends under the count threshold
(c1x60 seed 2: 27 planned, 28 placed against a threshold of 31, 16 soft
boxes of 45-73 L left out; the smallest 33 items across classes take 0.34
of the container).  The platform zeroes four of the five components of
such an episode (``reports/wedge/stability-lattice.md``, the findings
section "Why Task A episodes fall under the count").

When the planner's best plan holds fewer than the count threshold plus
``plan_value_margin`` items, this module plans the manifest again, one plan
per token of ``plan_count_secure_blocks``:

* ``plain``: the row planner itself with the count-secured overrides
  (``plan_count_secure_standing_rows``: the hard cargo the flat rows leave
  in standing rows of their own, the soft cargo on its own rows);
* ``left`` / ``right`` / ``back`` / ``top``: a count frame -- the
  threshold plus the margin smallest items across classes, the priority
  cargo always in it (in the priority container first, as the row planner
  does) -- planned before the rest:

  1. the frame's soft cargo as a block on a strip of the floor (along the
     left or right wall, or at the back), in layers of rows -- soft on
     soft under the configured soft-structure cap -- so it keeps off the
     floor the hard rows need (hard cargo may not rest on soft cargo);
     ``top``: no block, the frame's soft cargo on its own rows over the
     frame's hard rows;
  2. the frame's hard cargo in rows on the rest of the floor (the normal
     hard cargo, then the priority hard cargo on top of it where no
     priority container takes it);
  3. only then the rest of the manifest for fill: the bigger hard cargo on
     the hard rows, the rest of the soft cargo on whatever top takes it,
     and the planner's greedy pose search for what the rows leave.

Measured on the dense manifests (``reports/wedge/a-count-secure.md``):
the soft block loses to the hard columns.  Soft carries soft only to the
0.7 m cap, a top in the mid-height transport band (0.70-0.80 m) is not
carried in, so a soft block is two layers of 0.25 m, about 11 items a
square metre, where a hard column of the smallest boxes holds two flat
layers, a standing layer and the soft cargo on top, 18-27; the frame plans
hold 15-30 items against the ``plain`` plan's 26-34 on c1x50-c1x80.

Every pose goes through the planner's own checks (the validator with the
transport sweep, the cover rule, the soft support ratio), so the count a
plan holds is the analytic replay's.  The plans are ranked first by
whether they hold the threshold plus the margin, then by the plan score
(under the threshold, by the count); the planner's ordinary plan stands
whenever it holds the threshold plus the margin.
"""

from __future__ import annotations

import copy
import dataclasses
import itertools
import re
import time

from . import classify as cls
from . import layer1
from .geometry import Rect


class _RegionBoard:
    """The planning board with one container's floor narrowed to a
    rectangle: ``planner.pack_rows`` lays its rows over ``floor_rect``, so
    a model whose rectangle is the region keeps every row inside it.  The
    validator does not read the rectangle; everything else is the board's."""

    def __init__(self, board: layer1.Board, container_idx: int, rect: Rect):
        self._board = board
        self._ci = int(container_idx)
        model = copy.copy(board.model(container_idx))
        model.floor_rect = rect
        self._model = model

    def model(self, index: int):
        return self._model if int(index) == self._ci else self._board.model(index)

    def __getattr__(self, name):
        return getattr(self._board, name)


def parse_overrides(config, text: str) -> dict:
    """``plan_count_secure_overrides``: "field=value;field=value" (";" or
    "|" between pairs: an arm spec's overrides are comma-separated), each
    value read as the type of the field's current value."""
    out = {}
    for pair in re.split(r"[;|]", text):
        key, _eq, raw = pair.strip().partition("=")
        if not key:
            continue
        current = getattr(config, key)
        if isinstance(current, bool):
            out[key] = raw.strip().lower() in ("1", "true", "yes", "on")
        elif isinstance(current, int):
            out[key] = int(raw)
        elif isinstance(current, float):
            out[key] = float(raw)
        else:
            out[key] = raw
    return out


def count_frame(item_list: list[dict], size: int) -> list[int]:
    """The count frame: every priority item, then the smallest of the rest
    (by volume, the index on a tie) up to ``size`` items in all."""
    def volume(item):
        return float(item["length"]) * float(item["width"]) * float(item["height"])

    prio = [int(i["index"]) for i in item_list if i.get("is_prioritized")]
    rest = sorted((i for i in item_list if not i.get("is_prioritized")), key=lambda i: (volume(i), int(i["index"])))
    return prio + [int(i["index"]) for i in rest[:max(0, int(size) - len(prio))]]


def _snap(length: float, sides: list[float], gap: float, limit: float) -> float:
    """The smallest sum of up to three box sides (with the gaps between)
    at or above ``length`` and within ``limit``; ``length`` itself when no
    sum fits."""
    best = None
    for n in (1, 2, 3, 4):
        for combo in itertools.combinations_with_replacement(sorted(set(sides)), n):
            total = sum(combo) + gap * (n - 1)
            if total + 1e-9 >= length and total <= limit + 1e-9 and (best is None or total < best):
                best = total
    return best if best is not None else min(length, limit)


def block_regions(model, config, soft_profiles: list, side: str, layers: int,
                  max_share: float) -> tuple[Rect, Rect] | None:
    """(block, rest): the floor strip the soft block takes on ``side``
    ("left", "right", "back") and the floor left for the hard rows, or
    None when the strip would be the whole floor.  The strip's area is the
    soft footprint over ``layers`` (soft on soft needs the floor share the
    soft-structure gate asks first: at least that share of the floor), the
    strip's width snapped up to a sum of the soft boxes' sides."""
    from . import stability

    rect = model.floor_rect
    gap = config.settled_clearance + config.anchor_slack
    width = rect.x_max - rect.x_min
    depth = rect.y_max - rect.y_min
    footprints = []
    sides = []
    for p in soft_profiles:
        dz = min(o.dz for o in p.orientations)
        flat = [o for o in p.orientations if abs(o.dz - dz) < 1e-9]
        footprints.append(flat[0].dx * flat[0].dy)
        for o in flat:
            sides.extend([o.dx, o.dy])
    if not footprints:
        return None
    need = sum(footprints) / 0.85
    floor_share = float(getattr(stability, "SOFT_STRUCTURE_FLOOR_SHARE", 0.0) or 0.0)
    if layers > 1 and need > floor_share * width * depth:
        # stacked: the footprint over the layers, but no less than the
        # share of the floor soft-on-soft waits for
        need = max(need / layers, (floor_share + 0.03) * width * depth)
    if side in ("left", "right"):
        w = _snap(need / depth, sides, gap, max_share * width)
        if w >= width - 0.2:
            return None
        if side == "left":
            return (Rect(rect.x_min, rect.x_min + w, rect.y_min, rect.y_max),
                    Rect(rect.x_min + w + gap, rect.x_max, rect.y_min, rect.y_max))
        return (Rect(rect.x_max - w, rect.x_max, rect.y_min, rect.y_max),
                Rect(rect.x_min, rect.x_max - w - gap, rect.y_min, rect.y_max))
    if side == "back":
        d = _snap(need / width, sides, gap, max_share * depth)
        if d >= depth - 0.2:
            return None
        return (Rect(rect.x_min, rect.x_max, rect.y_max - d, rect.y_max),
                Rect(rect.x_min, rect.x_max, rect.y_min, rect.y_max - d - gap))
    return None


def _greedy_tail(agent, board: layer1.Board, profiles: dict, by_index: dict, indices: list[int], config,
                 plan: list, planned: list, deadline: float) -> None:
    """The planner's pose search for what the rows left (``_plan_once``'s
    tail): each item at its best legal pose under the "walls" preference."""
    from wedge_rl.stack import stack_candidates

    from .planner import _key, _placement

    key = _key("walls", 0.22)
    longest = 0.0
    for index in indices:
        now = time.perf_counter()
        if now + longest >= deadline:
            return
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
                chosen = (container_idx, model, min(cands, key=lambda c: key(c, model)), len(cands))
                break
        longest = max(longest, time.perf_counter() - now)
        if chosen is None:
            continue
        container_idx, model, cand, count = chosen
        placement = _placement(cand, count, profile, container_idx, model)
        placement.step = len(planned) + 1
        board.apply(placement)
        planned.append(index)
        plan.append({"step": len(planned), "index": index, "container_idx": int(container_idx),
                     "orientation": int(cand.orientation),
                     "center": [float(v) for v in cand.box.center], "size": [float(v) for v in cand.box.size],
                     "bottom": float(cand.bottom), "on_floor": bool(cand.on_floor), "archetype": "plan"})


def pack_block(agent, board: layer1.Board, container_idx: int, items: list, config, plan: list, planned: list,
               deadline: float, rect: Rect, wall: str = "left") -> int:
    """The soft block: each item (in the given order) at the legal flat
    pose inside ``rect`` with the lowest layer, then the deepest, then the
    nearest the ``wall`` side -- the floor layer fills back to front before
    anything is stacked (soft carries soft only once the floor share the
    soft-structure gate asks is covered), the poses from
    ``stack_candidates`` (validator, transport sweep, cover rule), off the
    floor only on ``plan_min_support_soft`` of the footprint.  A soft box
    on end is 0.6 m of top-heavy column, so only the flat poses.  Placed
    items leave ``items``; returns how many were placed."""
    from wedge_rl.stack import stack_candidates

    from .planner import _placement

    region = _RegionBoard(board, container_idx, rect)
    model = region.model(container_idx)
    needed = float(getattr(config, "plan_min_support_soft", 0.8))
    tol = 0.01
    count = 0
    for profile in list(items):
        if time.perf_counter() >= deadline:
            break
        flat = min(o.dz for o in profile.orientations)
        cands = stack_candidates(model, region.container(container_idx), config, profile, max_candidates=10 ** 6)
        best = None
        for c in cands:
            b = c.box
            if abs(float(c.dims[2]) - flat) > 1e-9:
                continue
            if (float(b.minimum[0]) < rect.x_min - tol or float(b.maximum[0]) > rect.x_max + tol
                    or float(b.minimum[1]) < rect.y_min - tol or float(b.maximum[1]) > rect.y_max + tol):
                continue
            if not c.on_floor and c.support_ratio < needed - 1e-9:
                continue
            side = float(b.minimum[0]) - rect.x_min if wall == "left" else rect.x_max - float(b.maximum[0])
            key = (int((c.bottom - model.z_floor) / 0.1 + 1e-6), -round(float(b.center[1]), 2), round(side, 2))
            if best is None or key < best[0]:
                best = (key, c, len(cands))
        if best is None:
            continue
        _k, cand, n = best
        placement = _placement(cand, n, profile, container_idx, board.model(container_idx))
        placement.step = len(planned) + 1
        board.apply(placement)
        planned.append(profile.index)
        items.remove(profile)
        plan.append({"step": len(planned), "index": profile.index, "container_idx": int(container_idx),
                     "orientation": int(cand.orientation),
                     "center": [float(v) for v in cand.box.center], "size": [float(v) for v in cand.box.size],
                     "bottom": float(cand.bottom), "on_floor": bool(cand.on_floor), "archetype": "plan"})
        count += 1
    return count


def pack_soft_block(agent, board: layer1.Board, container_idx: int, items: list, config, plan: list,
                    planned: list, deadline: float, log=None) -> float | None:
    """The soft frame block (``plan_count_secure_blocks`` token ``soft``):
    ``items`` (the frame's soft cargo, consumed as placed) standing on the
    smallest face in rows against the back wall, the normal boxes first and
    the priority ones last (nothing normal may rest on them), then a second
    standing layer on the first where the soft-structure cap and the soft
    floor share let soft carry soft (``plan_count_secure_soft_layers``);
    the rows stop once the floor holds a base for every box left, and never
    pass ``plan_count_secure_soft_depth_share`` of the floor's depth or
    ``plan_count_secure_soft_rows`` rows.  Returns the block's front edge
    (y), or None when nothing was placed."""
    from .planner import pack_typed_gallery

    model = board.model(container_idx)
    rect = model.floor_rect
    share = float(getattr(config, "plan_count_secure_soft_depth_share", 0.6))
    y_bottom = rect.y_max - share * (rect.y_max - rect.y_min)
    return pack_typed_gallery(agent, board, container_idx, items, config, plan, planned, deadline, log,
                              mode="column", max_rows=int(getattr(config, "plan_count_secure_soft_rows", 4)),
                              y_bottom=y_bottom, layers=int(getattr(config, "plan_count_secure_soft_layers", 2)),
                              priority_last=True, ledge=bool(getattr(config, "plan_count_secure_soft_ledge", False)),
                              row_gap_extra=float(getattr(config, "plan_count_secure_soft_gap", 0.03)),
                              replay_nudge=float(getattr(config, "plan_count_secure_soft_nudge", 0.04)),
                              row_end_extra=float(getattr(config, "plan_count_secure_soft_end_slack", 0.0)))


def plan_frame(agent, item_list: list[dict], deadline: float, frame: list[int], side: str,
               log=None) -> tuple[list[int], list[dict], dict]:
    """One count-secured plan with the soft block on ``side``.  Returns
    ``(order, plan, info)`` in the planner's form: the planned items in
    plan order (the frame's first), then the unplanned ones."""
    from .planner import pack_rows, planning_order

    config = agent.config
    layers = max(1, int(getattr(config, "plan_count_secure_block_layers", 2)))
    max_share = float(getattr(config, "plan_count_secure_block_share", 0.6))
    gap = config.settled_clearance + config.anchor_slack
    containers = copy.deepcopy(agent.board.containers)
    for container in containers:
        container.setdefault("packed_items", [])
    board = layer1.Board(containers, config)
    by_index = {int(item["index"]): item for item in item_list}
    profiles = {p.index: p for p in (cls.classify_item(int(i["index"]), i, config) for i in item_list)}
    has_priority = any(m.is_prioritized for m in board.models)
    # the frame's order as the planner would play it with the priority
    # cargo after the normal hard cargo (nothing may rest on it but more
    # priority cargo); in a priority container, the priority cargo first
    order = planning_order(list(profiles.values()), config, has_priority, "after-hard")
    in_frame = set(int(i) for i in frame)
    plan: list[dict] = []
    planned: list[int] = []
    priority_idx = [i for i, m in enumerate(board.models) if m.is_prioritized]
    normal_idx = [i for i, m in enumerate(board.models) if not m.is_prioritized] or list(range(len(board.models)))
    info = {"side": side, "regions": []}

    def left_of(pool):
        done = set(planned)
        return [p for p in pool if p.index not in done]

    priority_lines: dict[int, list] = {}
    if priority_idx:
        # the priority container takes the priority cargo first, as the
        # row planner does
        for ci in priority_idx:
            items = [profiles[i] for i in order if profiles[i].is_prioritized and i not in set(planned)]
            priority_lines[ci] = pack_rows(agent, board, ci, items, config, plan, planned, deadline, log,
                                           deep_first=bool(getattr(config, "plan_priority_deep_first", False)))
    frame_profiles = [profiles[i] for i in order if i in in_frame]
    hard_lines: dict[int, tuple] = {}
    for ci in normal_idx:
        if time.perf_counter() >= deadline:
            break
        model = board.model(ci)
        here = [p for p in left_of(frame_profiles) if not (p.is_prioritized and priority_idx)]
        # the normal cargo before the priority cargo of each kind: nothing
        # but priority cargo may rest on priority cargo
        soft = [p for p in here if p.is_soft and not p.is_prioritized] + [p for p in here if p.is_soft and p.is_prioritized]
        hard = [p for p in here if not p.is_soft and not p.is_prioritized]
        hard_prio = [p for p in here if not p.is_soft and p.is_prioritized]
        rest_rect = model.floor_rect
        if side == "top":
            # no block: the frame's hard rows over the whole floor, the
            # frame's soft cargo on its own rows over their top, the
            # priority hard cargo where the soft cargo left the top free
            lines = pack_rows(agent, board, ci, hard, config, plan, planned, deadline, log)
            hard_lines[ci] = (board, lines)
            pack_rows(agent, board, ci, [p for p in soft if not p.is_prioritized], config, plan, planned,
                      deadline, log)
            pack_rows(agent, board, ci, hard_prio, config, plan, planned, deadline, log, row_lines=lines)
            pack_rows(agent, board, ci, left_of([p for p in soft if p.is_prioritized]), config, plan, planned,
                      deadline, log)
            continue
        if side == "soft":
            # the soft frame block (config.plan_count_secure_soft_*): the
            # frame's soft cargo standing in rows against the back wall,
            # two standing layers where the soft-structure cap lets the
            # first carry the second (planner.pack_typed_gallery, mode
            # "column"), the frame's hard rows on the floor in front of it
            edge = pack_soft_block(agent, board, ci, soft, config, plan, planned, deadline, log)
            if edge is not None:
                # the hard rows start the block's row gap in front of its
                # planned edge: its front row settles towards them
                rest_rect = Rect(rest_rect.x_min, rest_rect.x_max, rest_rect.y_min,
                                 edge - gap - float(getattr(config, "plan_count_secure_soft_gap", 0.03)))
                info["regions"].append([round(v, 3) for v in
                                        Rect(rest_rect.x_min, rest_rect.x_max, edge, model.floor_rect.y_max).as_tuple()])
        elif soft:
            regions = block_regions(model, config, soft, side, layers, max_share)
            if regions is not None:
                block_rect, rest_rect = regions
                info["regions"].append([round(v, 3) for v in block_rect.as_tuple()])
                if getattr(config, "plan_count_secure_block_rows", True):
                    # rows of flat soft boxes inside the strip, layer by
                    # layer (a soft box on end is 0.6 m of top-heavy
                    # column); the rows laid out for volume, so each row
                    # takes the boxes of its own depth
                    block_config = dataclasses.replace(config, plan_standing=False, count_first=False)
                    pack_rows(agent, _RegionBoard(board, ci, block_rect), ci, soft, block_config, plan, planned,
                              deadline, log)
                else:
                    pack_block(agent, board, ci, soft, config, plan, planned, deadline, block_rect,
                               "right" if side == "right" else "left")
        region = _RegionBoard(board, ci, rest_rect)
        lines = pack_rows(agent, region, ci, hard, config, plan, planned, deadline, log)
        pack_rows(agent, region, ci, hard_prio, config, plan, planned, deadline, log, row_lines=lines)
        hard_lines[ci] = (region, lines)
    info["frame_planned"] = sum(1 for i in planned if i in in_frame)
    # the rest, for fill: the bigger hard cargo on the frame's hard rows,
    # then the rest of the soft cargo over the whole floor (its own rows,
    # on whatever top takes it), then the pose search
    for ci in normal_idx:
        if time.perf_counter() >= deadline:
            break
        rest = [profiles[i] for i in order if i not in set(planned)]
        hard = [p for p in rest if not p.is_soft and not (p.is_prioritized and priority_idx)]
        region, lines = hard_lines.get(ci, (board, None))
        pack_rows(agent, region, ci, hard, config, plan, planned, deadline, log, row_lines=lines)
        soft = [p for p in left_of(rest) if p.is_soft and not (p.is_prioritized and priority_idx)]
        pack_rows(agent, board, ci, soft, config, plan, planned, deadline, log)
    if priority_idx and getattr(config, "plan_normal_in_priority_container", False):
        for ci in priority_idx:
            hard = [profiles[i] for i in order if i not in set(planned)
                    and not profiles[i].is_soft and not profiles[i].is_prioritized]
            pack_rows(agent, board, ci, hard, config, plan, planned, deadline, log, row_lines=priority_lines.get(ci))
    left = [i for i in order if i not in set(planned)]
    _greedy_tail(agent, board, profiles, by_index, left, config, plan, planned, deadline)
    # the frame first in the replay order: a decline ends the episode, and
    # the frame's items in every container are what the count needs (the
    # rest was planned after the frame in each container, so the frame's
    # poses do not depend on it)
    frame_steps = [e for e in plan if int(e["index"]) in in_frame]
    rest_steps = [e for e in plan if int(e["index"]) not in in_frame]
    for n, e in enumerate(frame_steps + rest_steps):
        e["step"] = n + 1
    plan = frame_steps + rest_steps
    done = [int(e["index"]) for e in plan]
    unplanned = [i for i in order if i not in set(done)]
    info["planned"] = len(plan)
    return done + unplanned, plan, info


def priority_strip(model, config, priority: list, max_rows: int) -> tuple[float, int] | None:
    """``plan_count_secure_dense_priority_rows``: the depth (m) of the
    standing layer's front strip reserved for the priority hard boxes, and
    its rows: the shallowest standing pose under
    ``plan_standing_rows_max_height`` among them (the 0.55 x 0.40 x 0.24
    class on edge is 0.24 m deep and 0.55 m wide: two a row), as many rows
    as the boxes need up to ``max_rows``.  None when no priority box has a
    standing pose under the cap (the 0.75 x 0.56 x 0.27 boxes on their
    side are 0.56 or 0.75 m tall)."""
    from .planner import _standing_poses

    cap = float(getattr(config, "plan_standing_rows_max_height", 10.0))
    poses = [o for p in priority for o in _standing_poses(p) if o.dz <= cap + 1e-9]
    if not poses or max_rows <= 0:
        return None
    gap = config.settled_clearance + config.anchor_slack
    rect = model.floor_rect
    width = rect.x_max - rect.x_min - 2.0 * config.anchor_slack
    pose = min(poses, key=lambda o: (o.dy, -o.dx))
    per_row = max(1, int((width + gap) / (pose.dx + gap) + 1e-9))
    rows = min(int(max_rows), -(-len(priority) // per_row))
    return rows * (pose.dy + gap), rows


def _flat_height(profile) -> float:
    return min(o.dz for o in profile.orientations)


def _median(values: list[float]) -> float:
    values = sorted(values)
    return values[(len(values) - 1) // 2]


def carry_in_lift(bottom: float, top: float, container: dict) -> float:
    """The lift (m) the simulator carries a box in with at this height
    (``transport.transport_lifts``, read at the planned pose): the
    nominal drop height, 0 where the bottom is within 0.05 m over a
    resting level (the floor, the mid-height shelf level: the box slides
    in at its own height), and the clearance under a ceiling surface
    (the mid-height level, the ceiling) less the margin where the top is
    within the drop height of one.  A box on a packed top needs a lift
    of at least the sweep's clearance, or it touches its support on the
    way in."""
    from ._reuse import _production as prod
    from .transport import EDGE

    height = float(container["height"])
    thickness = float(container["thickness"])
    buffer = float(container.get("buffer", 0.0))
    lifts = [float(prod.SIMULATOR_DROP_HEIGHT)]
    for resting_z in (thickness + buffer, height / 2.0 + thickness + buffer):
        if -EDGE <= bottom - resting_z <= 0.05 + EDGE:
            lifts.append(0.0)
    margin = float(prod.SIMULATOR_CEILING_MARGIN) + float(prod.SIMULATOR_CEILING_CLIP_EPS)
    for ceiling_z in (height / 2.0 + buffer, height + buffer - thickness):
        clearance = ceiling_z - top
        if -EDGE <= clearance < float(prod.SIMULATOR_DROP_HEIGHT) + margin + EDGE:
            lifts.append(max(0.0, clearance - margin))
    return min(lifts)


def _sweep_clearance(config) -> float:
    return float(getattr(config, "transport_clearance", 0.0) or 0.0) or float(config.settled_clearance)


def carry_in_ok(bottom: float, top: float, model, container: dict, config) -> bool:
    """A box resting on packed cargo between ``bottom`` and ``top`` can be
    carried in: under the ceiling by the inclusion clearance, and lifted
    by at least the sweep's clearance (the c1 container's 1.57 m ceiling
    takes tops to 1.5255 m; the tops at 0.73-0.81 m under the mid-height
    level cannot be carried in either, the flat third layer of the
    sample mix)."""
    wall = float(config.inclusion_clearance) + float(config.anchor_slack)
    if top > float(model.z_ceiling) - wall + 1e-9:
        return False
    return carry_in_lift(bottom, top, container) >= _sweep_clearance(config) - 1e-9


def carry_in_ceiling(model, config) -> float:
    """The highest top (m, container frame) a box on packed cargo can be
    carried in at (``carry_in_ok``): the ceiling less the simulator's
    margin and lift clip and the sweep's clearance (c1: 1.5255)."""
    from ._reuse import _production as prod

    return float(model.z_ceiling) - float(prod.SIMULATOR_CEILING_MARGIN) - float(prod.SIMULATOR_CEILING_CLIP_EPS) \
        - _sweep_clearance(config)


def soft_thin_threshold(soft_profiles: list) -> float:
    """``plan_count_secure_dense_soft_thin`` read off the manifest: the
    flat soft heights sorted, a class is tall when it is at least 1.4
    times the next thinner one, and the threshold is the tallest height
    under the first such jump (the sample mix: 0.20, 0.23, 0.25 | 0.40 ->
    0.25).  0 when no class is tall (one pass, as without the lever)."""
    heights = sorted({round(_flat_height(p), 4) for p in soft_profiles})
    for low, high in zip(heights, heights[1:]):
        if high >= 1.4 * low - 1e-9:
            return low
    return 0.0


def soft_layers_needed(board, soft_profiles: list, share: float = 0.75) -> int:
    """How many flat soft layers the manifest's soft boxes need over the
    standing tops: two when their flat footprints cover more than
    ``share`` of the normal containers' floor, else one (the sample mix's
    13 soft boxes on the c1 floor: 2.5 m^2 on 2.0)."""
    floor = sum(m.floor_rect.area for m in board.models if not m.is_prioritized) \
        or sum(m.floor_rect.area for m in board.models)
    area = 0.0
    for p in soft_profiles:
        dz = _flat_height(p)
        o = next(o for o in p.orientations if abs(o.dz - dz) < 1e-9)
        area += o.dx * o.dy
    return 2 if area > share * floor else 1


def _row_slots(model, config, dx: float, dy: float) -> int:
    """How many boxes of this footprint a layer over the floor holds in
    rows (``priority_strip``'s arithmetic over the floor's depth, the
    footprint either way round)."""
    gap = config.settled_clearance + config.anchor_slack
    rect = model.floor_rect
    width = rect.x_max - rect.x_min - 2.0 * config.anchor_slack
    depth = rect.y_max - rect.y_min - 2.0 * config.anchor_slack
    best = 0
    for a, b in ((dx, dy), (dy, dx)):
        per_row = int((width + gap) / (a + gap) + 1e-9)
        rows = int((depth + gap) / (b + gap) + 1e-9)
        best = max(best, per_row * rows)
    return best


def dense_standing_cap(model, container: dict, config, hard_profiles: list, soft_profiles: list,
                       flat_top: float, layers: int, hard_limit: float | None = None) -> tuple[float, dict]:
    """``plan_count_secure_dense_soft_layers``: the standing layer's cap
    chosen for the count the layers over the flat top can hold.  The
    candidates are no standing layer (cap 0) and every standing pose
    height of ``hard_profiles`` (the frame's normal hard boxes left after
    the flat layers).  A candidate's count: the standing slots of the
    tallest pose under the cap that can be carried in (``carry_in_ok``)
    and keeps under ``hard_limit`` (the soft headroom reserve), by the
    rows the floor holds (``_row_slots``; the taller the pose, the
    smaller its footprint), no more than the boxes; plus up to ``layers``
    flat soft layers over the standing tops (over the flat top when
    nothing stands), each of the manifest's median soft height, each
    carried in and resting on a top under the re-plan's soft cap
    (``stability.SOFT_STRUCTURE_MAX_TOP``) from the second on, each
    holding the floor's area at the mean soft footprint, no more than
    the soft boxes.  A cap whose tops take ``layers`` soft layers comes
    first (the token is the plan with that many layers beside the
    uncapped plan, which the rank weighs against it), then the highest
    count, then the lower cap (a lower load).  On the sample mix over
    the 0.54 m flat top: 0.40 (11 on edge and two layers of 8) over 0.55
    (15 on end and one layer, even where the manifest's few soft boxes
    would make it the higher count) and over no standing layer (the
    first soft layer's top in the mid-height band).  Returns the cap and
    the estimate."""
    from . import stability

    fixed = float(getattr(config, "plan_standing_rows_max_height", 10.0))
    poses = sorted({(round(o.dz, 4), round(o.dx, 4), round(o.dy, 4)) for p in hard_profiles for o in _standing_poses_of(p)})
    if not poses:
        return fixed, {"cap": fixed, "layers": 0, "why": "no standing pose"}
    wall = float(config.inclusion_clearance) + float(config.anchor_slack)
    limit = float(model.z_ceiling) - wall if hard_limit is None else min(float(hard_limit), float(model.z_ceiling) - wall)
    soft_cap = stability.SOFT_STRUCTURE_MAX_TOP
    n_hard = len(hard_profiles)
    n_soft = len(soft_profiles)
    s = _median([_flat_height(p) for p in soft_profiles]) if soft_profiles else 0.0
    soft_area = 0.0
    for p in soft_profiles:
        o = next(o for o in p.orientations if abs(o.dz - _flat_height(p)) < 1e-9)
        soft_area += o.dx * o.dy
    per_layer = int(0.8 * model.floor_rect.area / (soft_area / n_soft)) if n_soft else 0
    heights = sorted({h for h, _dx, _dy in poses})
    best = None
    estimates = []
    for cap in [0.0] + heights:
        standing, top, pose = 0, flat_top, None
        for h, dx, dy in sorted((q for q in poses if q[0] <= cap + 1e-9), reverse=True):
            if flat_top + h <= limit + 1e-9 and carry_in_ok(flat_top, flat_top + h, model, container, config):
                pose = (h, dx, dy)
                break
        if pose is not None:
            # the boxes of the classes the cap admits
            admitted = sum(1 for p in hard_profiles if any(o.dz <= cap + 1e-9 for o in _standing_poses_of(p)))
            standing = min(_row_slots(model, config, pose[1], pose[2]), admitted, n_hard)
            top = flat_top + pose[0]
        # the soft layers the geometry allows over the top (``fits``) and
        # the boxes they hold
        soft, fits = 0, 0
        z = top
        for k in range(max(0, int(layers))):
            if s <= 0.0:
                break
            if k > 0 and soft_cap is not None and z > float(soft_cap) + 1e-9:
                break
            if not carry_in_ok(z, z + s, model, container, config):
                break
            fits += 1
            soft += min(per_layer, max(0, n_soft - soft))
            z += s
        count = standing + soft
        estimates.append({"cap": cap, "standing": standing, "soft": soft, "layers": fits, "top": round(top, 3)})
        # a cap whose tops take the layers asked first (the token is the
        # two-layer plan beside the uncapped one), then the count, then
        # the lower cap
        key = (fits >= max(0, int(layers)), count, -cap)
        if best is None or key > best[0]:
            best = (key, cap, estimates[-1])
    _key, cap, chosen = best
    return cap, {"cap": cap, "layers": chosen["layers"], "standing": chosen["standing"], "soft": chosen["soft"],
                 "flat_top": round(flat_top, 3), "soft_height": round(s, 3), "limit": round(limit, 3),
                 "candidates": estimates}


def _standing_poses_of(profile) -> list:
    from .planner import _standing_poses

    return _standing_poses(profile)


def adaptive_dense_tokens(agent, item_list: list[dict], tokens: list[str]) -> tuple[list[str], dict]:
    """``plan_count_secure_dense_adaptive``: the ``dense`` tokens rewritten
    from the manifest.  A token's ``plan_standing_rows_max_height`` field
    becomes ``plan_count_secure_dense_soft_layers`` (``soft_layers_needed``:
    the cap itself is resolved in the plan, ``dense_standing_cap``); its
    ``plan_count_secure_dense_soft_thin`` becomes ``soft_thin_threshold``;
    other fields and other tokens stay; a rewritten token equal to an
    earlier one is dropped.  Returns the tokens and what was derived."""
    profiles = [cls.classify_item(int(i["index"]), i, agent.config) for i in item_list]
    soft = [p for p in profiles if p.is_soft]
    layers = soft_layers_needed(agent.board, soft) if soft else 1
    thin = soft_thin_threshold(soft) if soft else 0.0
    out: list[str] = []
    for token in tokens:
        side, at, extra = token.partition("@")
        if side != "dense" or not at:
            if token not in out:
                out.append(token)
            continue
        fields = []
        for pair in extra.split("&"):
            key, _eq, raw = pair.partition("=")
            if key == "plan_standing_rows_max_height":
                fields.append(f"plan_count_secure_dense_soft_layers={layers}")
            elif key == "plan_count_secure_dense_soft_thin":
                fields.append(f"plan_count_secure_dense_soft_thin={thin:g}")
            elif key:
                fields.append(pair)
        rewritten = "dense@" + "&".join(fields) if fields else "dense"
        if rewritten not in out:
            out.append(rewritten)
    return out, {"soft_layers": layers, "soft_thin": thin, "soft": len(soft)}


def plan_dense(agent, item_list: list[dict], deadline: float, frame: list[int],
               log=None) -> tuple[list[int], list[dict], dict]:
    """The ``dense`` count-secured plan (``plan_count_secure_blocks`` token
    ``dense``): the load of the dense c1x70 / c1x80 manifests built layer
    by layer, in the order the simulator can carry in
    (``reports/wedge/a-dense.md``):

    1. the hard cargo's flat layers (``pack_rows`` without standing rows:
       the row planner's two flat layers of the boxes that tile the floor,
       tops at 0.29 and 0.54 m in the c1 container; a flat third layer's
       top lands in the mid-height transport band);
    2. ``plan_count_secure_dense_ledge``: the frame's normal soft boxes
       standing on the small shelf over the chamfer pocket (the ledge the
       row planner never rests cargo on: 0.44 m wide, the whole depth, its
       top at the mid-height level), from the back -- before the standing
       layer, since a ledge pose slides in at its own height and would
       cross the standing layer's left column;
    3. the standing layer: the hard cargo left in standing rows
       (``plan_standing_rows``, the poses up to
       ``plan_standing_rows_max_height``: 0.55 keeps the shipped layer of
       0.55 x 0.40 x 0.24 boxes on their 0.24 x 0.40 face, tops 1.09 m;
       0.40 stands them on edge, tops 0.94 m, where two flat soft layers
       fit under the ceiling), the normal hard boxes first and the
       priority ones last, so they take the front rows and the soft rows
       over the back are not kept off them (normal cargo may not cover
       priority cargo);
    4. the soft cargo in flat rows over the standing tops, its own row
       lines, layer upon layer while the soft-structure cap the re-plan
       runs under (``plan_count_secure_soft_cap``) lets soft carry soft:
       the frame's normal soft boxes first, the priority soft last (over
       the priority hard boxes in front, where nothing else may go);
    5. the rest for fill: the bigger hard cargo on the rows' lines, the
       pose search.

    Returns ``(order, plan, info)`` in the planner's form."""
    from .planner import pack_rows, pack_typed_gallery, planning_order

    config = agent.config
    containers = copy.deepcopy(agent.board.containers)
    for container in containers:
        container.setdefault("packed_items", [])
    board = layer1.Board(containers, config)
    by_index = {int(item["index"]): item for item in item_list}
    profiles = {p.index: p for p in (cls.classify_item(int(i["index"]), i, config) for i in item_list)}
    has_priority = any(m.is_prioritized for m in board.models)
    order = planning_order(list(profiles.values()), config, has_priority, "after-hard")
    in_frame = set(int(i) for i in frame)
    plan: list[dict] = []
    planned: list[int] = []
    priority_idx = [i for i, m in enumerate(board.models) if m.is_prioritized]
    normal_idx = [i for i, m in enumerate(board.models) if not m.is_prioritized] or list(range(len(board.models)))
    info = {"side": "dense", "ledge": 0, "flat": 0, "standing": 0, "soft": 0}
    flat_config = dataclasses.replace(config, plan_standing_rows=False, plan_standing=False)
    prio_rows = int(getattr(config, "plan_count_secure_dense_priority_rows", 0))
    thin_cap = float(getattr(config, "plan_count_secure_dense_soft_thin", 0.0))
    soft_layers = int(getattr(config, "plan_count_secure_dense_soft_layers", 0))

    def left_of(pool):
        done = set(planned)
        return [p for p in pool if p.index not in done]

    priority_lines: dict[int, list] = {}
    for ci in priority_idx:
        # the priority container takes the priority cargo first, as the
        # row planner does
        items = [profiles[i] for i in order if profiles[i].is_prioritized and i not in set(planned)]
        priority_lines[ci] = pack_rows(agent, board, ci, items, config, plan, planned, deadline, log,
                                       deep_first=bool(getattr(config, "plan_priority_deep_first", False)))
    hard_lines: dict[int, list] = {}
    cap_config: dict = {}
    for ci in normal_idx:
        if time.perf_counter() >= deadline:
            break
        here = [profiles[i] for i in order if i not in set(planned) and not (profiles[i].is_prioritized and priority_idx)]
        hard = [p for p in here if not p.is_soft and not p.is_prioritized] + [p for p in here if not p.is_soft and p.is_prioritized]
        soft_frame = [p for p in here if p.is_soft and not p.is_prioritized and p.index in in_frame]
        soft_rest = [p for p in here if p.is_soft and not p.is_prioritized and p.index not in in_frame]
        soft_prio = [p for p in here if p.is_soft and p.is_prioritized]
        # 1. the flat layers
        n0 = len(planned)
        lines = pack_rows(agent, board, ci, hard, flat_config, plan, planned, deadline, log)
        info["flat"] += len(planned) - n0
        # 2. the ledge
        if getattr(config, "plan_count_secure_dense_ledge", True) and getattr(board.model(ci), "small_shelf", None) is not None:
            n0 = len(planned)
            pack_typed_gallery(agent, board, ci, soft_frame, config, plan, planned, deadline, log, mode="column",
                               max_rows=0, layers=1, ledge=True,
                               replay_nudge=float(getattr(config, "plan_count_secure_soft_nudge", 0.04)))
            info["ledge"] += len(planned) - n0
        # 3. the standing layer: pack_rows switches to standing rows once
        # a flat pass places nothing (the band), so the flat lines are
        # handed back for the hard cargo's later passes
        n0 = len(planned)
        standing_config = dataclasses.replace(config, plan_standing_rows=True)
        model = board.model(ci)
        if soft_layers > 0:
            # plan_count_secure_dense_soft_layers: the cap from the flat
            # layers' actual top, the frame's hard classes left and the
            # manifest's soft heights (dense_standing_cap)
            flat_top = max([float(e["center"][2]) + float(e["size"][2]) / 2.0
                            for e in plan if int(e["container_idx"]) == ci and e["archetype"] == "plan"
                            and not by_index[int(e["index"])].get("is_soft")] or [model.z_floor])
            layer_hard = [p for p in left_of(hard) if not p.is_prioritized and p.index in in_frame] \
                or [p for p in left_of(hard) if not p.is_prioritized] or left_of(hard)
            reserve = agent._soft_headroom_reserve(board.containers, ci)
            cap, cap_info = dense_standing_cap(model, board.container(ci), config, layer_hard,
                                               left_of(soft_frame) + soft_rest + soft_prio, flat_top, soft_layers,
                                               hard_limit=model.z_ceiling - reserve if reserve > 0 else None)
            standing_config = dataclasses.replace(standing_config, plan_standing_rows_max_height=cap)
            # the derived cap holds for the rest of the container's plan
            # (the soft rows, the fill's standing rows), as a token's
            # fixed cap does
            cap_config[ci] = dataclasses.replace(config, plan_standing_rows_max_height=cap)
            info["standing_cap"] = cap_info
            if log:
                log(f"  [dense] container {ci} standing cap {cap:.2f} ({cap_info})")
        gap = config.settled_clearance + config.anchor_slack
        strip = None
        if prio_rows > 0:
            strip = priority_strip(model, standing_config, [p for p in left_of(hard) if p.is_prioritized], prio_rows)
        soft_floor_line = None
        if strip is None:
            pack_rows(agent, board, ci, left_of(hard), standing_config, plan, planned, deadline, log, row_lines=lines)
        else:
            # plan_count_secure_dense_priority_rows: the normal boxes keep
            # off the layer's front strip; the priority boxes stand there
            # (the rows behind them are loaded first), the normal boxes
            # left take what the strip has left, and the normal soft rows
            # over the top stop at the priority boxes' back edge, so
            # nothing normal covers them
            depth, rows = strip
            normal = [p for p in left_of(hard) if not p.is_prioritized]
            s0 = len(plan)
            pack_rows(agent, board, ci, normal, standing_config, plan, planned, deadline, log, row_lines=lines,
                      y_bottom=model.floor_rect.y_min + config.anchor_slack + depth)
            fronts = [float(e["center"][1]) - float(e["size"][1]) / 2.0 for e in plan[s0:]]
            y_top = min(fronts) - gap if fronts else None
            s1 = len(plan)
            pack_rows(agent, board, ci, [p for p in left_of(hard) if p.is_prioritized], standing_config, plan,
                      planned, deadline, log, row_lines=lines, y_top=y_top)
            backs = [float(e["center"][1]) + float(e["size"][1]) / 2.0 for e in plan[s1:]]
            info["priority_strip"] = {"rows": rows, "depth": round(depth, 3), "standing": len(plan) - s1}
            if backs:
                soft_floor_line = max(backs) + gap
            pack_rows(agent, board, ci, left_of(normal), standing_config, plan, planned, deadline, log,
                      row_lines=lines, y_top=y_top)
        info["standing"] += len(planned) - n0
        hard_lines[ci] = lines
        # 4. the soft layers over the top, their own rows, layer on layer
        n0 = len(planned)
        soft = left_of(soft_frame) + soft_rest + soft_prio
        ci_config = cap_config.get(ci, config)
        if soft_floor_line is None and thin_cap <= 0.0:
            pack_rows(agent, board, ci, soft, ci_config, plan, planned, deadline, log)
        else:
            # plan_count_secure_dense_soft_thin: the flat soft boxes up to
            # the cap first, in rows of their own, the taller ones after
            # (the count-first layout search takes a row of 0.40 m boxes
            # for its floor count and the second layer is lost over it);
            # the normal soft rows behind the priority strip, the priority
            # soft over the whole top (it may cover the priority boxes)
            normal = [p for p in soft if not p.is_prioritized]
            passes = [normal]
            if thin_cap > 0.0:
                passes = [[p for p in normal if min(o.dz for o in p.orientations) <= thin_cap + 1e-9],
                          [p for p in normal if min(o.dz for o in p.orientations) > thin_cap + 1e-9]]
            for pool in passes:
                if pool:
                    pack_rows(agent, board, ci, pool, ci_config, plan, planned, deadline, log, y_bottom=soft_floor_line)
            pack_rows(agent, board, ci, [p for p in left_of(soft) if p.is_prioritized], ci_config, plan, planned,
                      deadline, log)
        info["soft"] += len(planned) - n0
    # 5. the rest for fill (plan_count_secure_dense_priority_fill: the
    # priority hard boxes before the normal ones -- what the fill places
    # now is never covered by the plan's soft rows, which are laid)
    def fill_order(pool):
        if not getattr(config, "plan_count_secure_dense_priority_fill", False):
            return list(pool)
        return [p for p in pool if p.is_prioritized] + [p for p in pool if not p.is_prioritized]

    for ci in normal_idx:
        if time.perf_counter() >= deadline:
            break
        rest = [profiles[i] for i in order if i not in set(planned)]
        hard = fill_order([p for p in rest if not p.is_soft and not (p.is_prioritized and priority_idx)])
        pack_rows(agent, board, ci, hard, cap_config.get(ci, config), plan, planned, deadline, log,
                  row_lines=hard_lines.get(ci))
    if priority_idx and getattr(config, "plan_normal_in_priority_container", False):
        for ci in priority_idx:
            hard = [profiles[i] for i in order if i not in set(planned)
                    and not profiles[i].is_soft and not profiles[i].is_prioritized]
            pack_rows(agent, board, ci, hard, config, plan, planned, deadline, log, row_lines=priority_lines.get(ci))
    left = [p.index for p in fill_order([profiles[i] for i in order if i not in set(planned)])]
    _greedy_tail(agent, board, profiles, by_index, left, config, plan, planned, deadline)
    for n, e in enumerate(plan):
        e["step"] = n + 1
    done = [int(e["index"]) for e in plan]
    info["frame_planned"] = sum(1 for i in done if i in in_frame)
    info["planned"] = len(plan)
    return done + [i for i in order if i not in set(done)], plan, info


class _plan_soft_cap:
    """``plan_count_secure_soft_cap``: the soft-structure cap the re-plan
    is planned under (the floor share waived with it), restored after."""

    def __init__(self, config):
        self.cap = float(getattr(config, "plan_count_secure_soft_cap", -1.0))

    def __enter__(self):
        from . import stability

        self.saved = (stability.SOFT_STRUCTURE_MAX_TOP, stability.SOFT_STRUCTURE_FLOOR_SHARE)
        if self.cap >= 0.0:
            stability.SOFT_STRUCTURE_MAX_TOP = self.cap
            stability.SOFT_STRUCTURE_FLOOR_SHARE = 0.0
        return self

    def __exit__(self, *exc):
        from . import stability

        stability.SOFT_STRUCTURE_MAX_TOP, stability.SOFT_STRUCTURE_FLOOR_SHARE = self.saved
        return False

    def mark(self, plan: list, by_index: dict) -> int:
        """The plan's soft poses off the floor carry the cap for the replay
        (``planner.replay``); returns how many."""
        if self.cap < 0.0:
            return 0
        n = 0
        for e in plan:
            if by_index.get(int(e["index"]), {}).get("is_soft") and not e.get("on_floor"):
                e["soft_cap"] = self.cap
                n += 1
        return n


def plan_volume(plan: list) -> float:
    """The planned volume (m^3): the fill an uncounted episode is scored on."""
    return sum(float(e["size"][0]) * float(e["size"][1]) * float(e["size"][2]) for e in plan)


def _rank(entry, threshold: int, gate: int, by_fill: bool = False) -> tuple:
    """The re-plan's order of plans: over the threshold the plan score
    decides (the soft and priority shares count there), the threshold plus
    the margin first; under it only the count can still pay, so the plan
    with more items comes first.  ``by_fill`` (``plan_count_secure_fill_first``:
    the count out of reach): the planned volume first, then the count."""
    n = len(entry[2])
    if by_fill:
        return (False, False, round(plan_volume(entry[2]), 6), n)
    if n >= threshold:
        return (n >= gate, True, entry[0][0], n)
    return (False, False, n, entry[0][0])


def prefer_secured(agent, item_list: list[dict], chosen: tuple, secured: tuple) -> tuple:
    """``plan_count_secure_early``: the re-plan ran after the first plan;
    the plan the variants chose afterwards (``chosen``) stands unless the
    re-plan's pick ranks higher -- and when the re-plan kept the base, the
    variants' choice stands as the planner made it."""
    record = getattr(agent, "count_secure_log", None) or {}
    if chosen is None:
        return secured
    if record.get("chosen", "base") == "base" or secured is None:
        return chosen
    threshold, gate = record.get("threshold"), record.get("gate")
    if len(chosen[2]) >= int(record.get("trigger", gate)):
        # a later variant holds the trigger itself: the shipped choice
        record["chosen"] = "base"
        return chosen
    by_fill = bool(record.get("fill_first"))
    if _rank(secured, threshold, gate, by_fill) > _rank(chosen, threshold, gate, by_fill):
        return secured
    record["chosen"] = "base"
    return chosen


def secure_count(agent, item_list: list[dict], deadline: float, chosen: tuple, longest: float,
                 log=None) -> tuple:
    """``chosen`` (the planner's entry: ``((score, n), order, plan)``) or a
    count-secured plan that holds more of the count.  Runs only when the
    chosen plan holds fewer than the threshold plus ``plan_value_margin``
    items; each side in ``plan_count_secure_blocks`` is planned while the
    budget allows one more plan as long as the longest so far."""
    config = agent.config
    try:
        threshold = agent._count_threshold()
    except Exception:
        threshold = None
    if threshold is None:
        threshold = len(item_list) // 2 + 1
    margin = int(getattr(config, "plan_value_margin", 2))
    gate = threshold + margin
    # the plan that triggers the re-plan: under the threshold plus
    # plan_count_secure_margin (negative: plus plan_value_margin)
    trigger_margin = int(getattr(config, "plan_count_secure_margin", -1))
    trigger = threshold + (margin if trigger_margin < 0 else trigger_margin)
    base_n = len(chosen[2]) if chosen is not None else 0
    record = {"threshold": threshold, "gate": gate, "trigger": trigger, "base": base_n, "variants": [],
              "chosen": "base", "replanned": False}
    agent.count_secure_log = record
    if chosen is not None and base_n >= trigger:
        return chosen
    record["replanned"] = True
    # plan_count_secure_fill_first: the count out of reach (the planner's
    # plan under the share of the threshold), so the re-plan is ranked by
    # the planned volume -- the fill, the one component an uncounted
    # episode is scored on -- and the dense plans, built for the count,
    # are not planned
    fill_share = float(getattr(config, "plan_count_secure_fill_first", 0.0) or 0.0)
    by_fill = fill_share > 0.0 and base_n < fill_share * threshold
    record["fill_first"] = by_fill
    frame = count_frame(item_list, gate + int(getattr(config, "plan_count_secure_extra", 0)))
    record["frame"] = len(frame)
    scorer = getattr(agent, "plan_score", None)
    sides = [s for s in re.split(r"[,+|;]", str(getattr(config, "plan_count_secure_blocks", "plain"))) if s]
    if getattr(config, "plan_count_secure_dense_adaptive", False):
        # the dense tokens from the manifest (reports/wedge/a-mix.md)
        sides, derived = adaptive_dense_tokens(agent, item_list, sides)
        record["adaptive"] = dict(derived, tokens=list(sides))
        if log:
            log(f"  [count-secure] adaptive dense tokens {sides} ({derived})")
    by_index = {int(i["index"]): i for i in item_list}
    changes = {}
    if getattr(config, "plan_count_secure_standing_rows", True):
        # the hard cargo the flat rows leave in standing rows of their own,
        # and the soft cargo on its own rows over the top they make
        changes.update(plan_standing_rows=True, plan_soft_own_rows=True)
    changes.update(parse_overrides(config, str(getattr(config, "plan_count_secure_overrides", "") or "")))

    def rank(entry):
        return _rank(entry, threshold, gate, by_fill)

    factor = float(getattr(config, "plan_count_secure_start_factor", 1.2))
    best = chosen
    for token in sides:
        if by_fill and token.partition("@")[0] == "dense":
            record["variants"].append({"side": token, "skipped": True, "fill_first": True})
            continue
        if (token.partition("@")[0] == "dense" and getattr(config, "plan_count_secure_dense_when_short", True)
                and best is not None and len(best[2]) >= gate):
            # a plan so far holds the threshold plus the margin: the dense
            # plan would win the rank on its count and trade the priority
            # boxes the platform pays for once the episode counts
            record["variants"].append({"side": token, "skipped": True, "held": len(best[2])})
            continue
        now = time.perf_counter()
        if now + factor * longest >= deadline:
            # not started: it would not finish in what is left of the budget
            record["variants"].append({"side": token, "skipped": True, "left": round(deadline - now, 1),
                                       "longest": round(longest, 1)})
            break
        t0 = now
        # "side@field=value&field=value": a variant with fields of its own
        side, _at, extra = token.partition("@")
        mine = dict(changes)
        mine.update(parse_overrides(config, extra.replace("&", ";")))
        if mine:
            agent.config = dataclasses.replace(config, **mine)
        soft_cap = _plan_soft_cap(agent.config)
        try:
            with soft_cap:
                if side == "plain":
                    # the row planner itself under the count-secured overrides,
                    # no frame: its first priority order
                    from .planner import _plan_once

                    variant = (re.split(r"[,+|]", str(getattr(config, "plan_variants", "after-hard"))) or ["after-hard"])[0]
                    order, plan = _plan_once(agent, item_list, deadline, variant, log)
                    info = {"frame_planned": sum(1 for e in plan if int(e["index"]) in set(frame))}
                elif side == "dense":
                    order, plan, info = plan_dense(agent, item_list, deadline, frame, log)
                else:
                    order, plan, info = plan_frame(agent, item_list, deadline, frame, side, log)
            info["soft_capped"] = soft_cap.mark(plan, by_index)
        except Exception as exc:  # a failed variant leaves the planner's plan
            record["variants"].append({"side": token, "error": repr(exc)})
            continue
        finally:
            agent.config = config
        longest = max(longest, time.perf_counter() - t0)
        if time.perf_counter() >= deadline:
            record["variants"].append({"side": token, "planned": len(plan), "cut": True})
            break
        score = scorer(plan) if scorer is not None else float(len(plan))
        n_soft = sum(1 for e in plan if by_index[int(e["index"])].get("is_soft"))
        n_prio = sum(1 for e in plan if by_index[int(e["index"])].get("is_prioritized"))
        entry_log = {"side": token, "planned": len(plan), "frame_planned": info.get("frame_planned"),
                     "soft": n_soft, "priority": n_prio, "score": round(score, 3),
                     "volume": round(plan_volume(plan), 4), "seconds": round(time.perf_counter() - t0, 1)}
        if side == "dense":
            entry_log["layers"] = {k: info.get(k) for k in ("flat", "ledge", "standing", "soft")}
            if info.get("standing_cap"):
                entry_log["standing_cap"] = info["standing_cap"]
        if info.get("soft_capped"):
            entry_log["soft_capped"] = info["soft_capped"]
        record["variants"].append(entry_log)
        if log:
            log(f"  [count-secure] {token}: {len(plan)} planned (frame {info.get('frame_planned')} of {len(frame)}, "
                f"soft {n_soft}, priority {n_prio}), score {score:.3f}, gate {gate}")
        entry = ((score, len(plan)), order, plan)
        if best is None or rank(entry) > rank(best):
            best = entry
            record["chosen"] = token
    return best
