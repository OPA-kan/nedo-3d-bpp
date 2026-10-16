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


def plan_frame(agent, item_list: list[dict], deadline: float, frame: list[int], side: str,
               log=None) -> tuple[list[int], list[dict], dict]:
    """One count-secured plan with the soft block on ``side``.  Returns
    ``(order, plan, info)`` in the planner's form: the planned items in
    plan order (the frame's first), then the unplanned ones."""
    from .planner import pack_rows, planning_order

    config = agent.config
    layers = max(1, int(getattr(config, "plan_count_secure_block_layers", 2)))
    max_share = float(getattr(config, "plan_count_secure_block_share", 0.6))
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
        if soft:
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


def _rank(entry, threshold: int, gate: int) -> tuple:
    """The re-plan's order of plans: over the threshold the plan score
    decides (the soft and priority shares count there), the threshold plus
    the margin first; under it only the count can still pay, so the plan
    with more items comes first."""
    n = len(entry[2])
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
    if _rank(secured, threshold, gate) > _rank(chosen, threshold, gate):
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
    frame = count_frame(item_list, gate + int(getattr(config, "plan_count_secure_extra", 0)))
    record["frame"] = len(frame)
    scorer = getattr(agent, "plan_score", None)
    sides = [s for s in re.split(r"[,+|;]", str(getattr(config, "plan_count_secure_blocks", "plain"))) if s]
    by_index = {int(i["index"]): i for i in item_list}
    changes = {}
    if getattr(config, "plan_count_secure_standing_rows", True):
        # the hard cargo the flat rows leave in standing rows of their own,
        # and the soft cargo on its own rows over the top they make
        changes.update(plan_standing_rows=True, plan_soft_own_rows=True)
    changes.update(parse_overrides(config, str(getattr(config, "plan_count_secure_overrides", "") or "")))

    def rank(entry):
        return _rank(entry, threshold, gate)

    factor = float(getattr(config, "plan_count_secure_start_factor", 1.2))
    best = chosen
    for token in sides:
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
        try:
            if side.startswith("typed:"):
                # the typed-standing gallery (planner._plan_typed_once) as a
                # re-plan of its own, "typed:<at>-<mode>-<rows>[-soft|-prio]":
                # ranked with the other re-plans, under this module's trigger
                # and start rule, with the count-secured overrides; its
                # count frame takes plan_count_secure_extra too
                if getattr(config, "plan_typed_standing_no_priority_container", False) and any(
                        m.is_prioritized for m in agent.board.models):
                    record["variants"].append({"side": token, "skipped": True, "priority_container": True})
                    continue
                from .planner import _plan_typed_once

                parts = side[len("typed:"):].split("-")
                at = parts[0] if parts and parts[0] in ("back", "front", "top") else "back"
                mode = parts[1] if len(parts) > 1 and parts[1] in ("stand", "tower") else "stand"
                rows = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 2
                tokens = set(parts[3:])
                with_priority = True if "prio" in tokens else (False if "soft" in tokens else None)
                variant = (re.split(r"[,+|]", str(getattr(config, "plan_variants", "after-hard"))) or ["after-hard"])[0]
                order, plan = _plan_typed_once(agent, item_list, deadline, variant,
                                               gate + int(getattr(config, "plan_count_secure_extra", 0)),
                                               at, mode, rows, log, with_priority=with_priority)
                info = {"frame_planned": sum(1 for e in plan if int(e["index"]) in set(frame))}
            elif side == "plain":
                # the row planner itself under the count-secured overrides,
                # no frame: its first priority order
                from .planner import _plan_once

                variant = (re.split(r"[,+|]", str(getattr(config, "plan_variants", "after-hard"))) or ["after-hard"])[0]
                order, plan = _plan_once(agent, item_list, deadline, variant, log)
                info = {"frame_planned": sum(1 for e in plan if int(e["index"]) in set(frame))}
            else:
                order, plan, info = plan_frame(agent, item_list, deadline, frame, side, log)
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
        record["variants"].append({"side": token, "planned": len(plan), "frame_planned": info.get("frame_planned"),
                                   "soft": n_soft, "priority": n_prio, "score": round(score, 3),
                                   "seconds": round(time.perf_counter() - t0, 1)})
        if log:
            log(f"  [count-secure] {token}: {len(plan)} planned (frame {info.get('frame_planned')} of {len(frame)}, "
                f"soft {n_soft}, priority {n_prio}), score {score:.3f}, gate {gate}")
        entry = ((score, len(plan)), order, plan)
        if best is None or rank(entry) > rank(best):
            best = entry
            record["chosen"] = token
    return best
