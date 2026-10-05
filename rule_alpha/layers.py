"""Task A offline layer packer: the container filled to the ceiling, row by row.

The top of the leaderboard sits in the seventies, which at the official
weights is only possible with nearly every item placed; this agent places
61 %.  The items of a manifest sum to 50-56 % of the container's volume, and
a level-layer shelf packing with no stability rules fits 36-41 of 41 on
every bench A scene -- the room is there, the ladder's rules leave it.

Level layers over the whole floor do not carry in: the simulator sweeps an
item along y at its own x and height, and a box resting on a 0.24 m box
collides with the 0.27 m tops beside it (130 of 135 second-layer poses on
a-c1-s0001 failed the sweep).  So the load is built as rows from the back
wall to the opening, every row stacked to the ceiling before the next one
starts: a box in the current row sweeps in over rows that are still empty.
A row is a strip of one depth; its columns run left to right, each a stack
of flat boxes whose footprints shrink upward, and every pose goes through
the planner's pose check (inclusion, the transport sweep, the cover rule,
the support share), so the plan is feasible on the analytic model.  The
row depths are searched (the distinct flat depths of the manifest, in
sequences) within the budget and the layout with the most boxes kept.
Hard cargo first, then the priority cargo, then the soft cargo in the
rows that are left, nearest the opening: nothing covers the special cargo.
"""

from __future__ import annotations

import copy
import itertools
import time

from . import classify as cls
from . import layer1
from .planner import ARCHETYPE, _Pose, _flat_poses, _placement, _try_pose


def _flat(profile):
    """The flat orientations of a profile: (dx, dy, dz, orientation)."""
    return [(o.dx, o.dy, o.dz, o) for o in _flat_poses(profile)]


def _depth_options(profiles: list) -> list[float]:
    depths = set()
    for p in profiles:
        for dx, dy, _dz, _o in _flat(p):
            depths.add(round(dy, 3))
            depths.add(round(dx, 3))
    return sorted(depths, reverse=True)


class _Fill:
    """One attempt at filling one container with a list of profiles along a
    sequence of row depths, on a scratch board; ``run`` returns the count."""

    def __init__(self, agent, container_idx: int, items: list, config, log=None):
        self.agent = agent
        self.ci = container_idx
        self.items = list(items)
        self.config = config
        self.log = log
        self.containers = copy.deepcopy(agent.board.containers)
        for c in self.containers:
            c.setdefault("packed_items", [])
        self.board = layer1.Board(self.containers, config)
        self.plan: list[dict] = []
        self.planned: list[int] = []
        self.ranks = {0, 1, 2}
        self.capacity = sum(float(c["length"]) * float(c["width"]) * float(c["height"]) for c in self.containers) or 1.0
        self.n_soft = sum(1 for p in items if p.is_soft)
        self.n_prio = sum(1 for p in items if p.is_prioritized)

    def place(self, profile, orientation, x: float, y: float):
        box, why = _try_pose(self.board, self.ci, profile, orientation, x, y, self.config, None)
        if box is None:
            return None, why
        model = self.board.model(self.ci)
        cand = _Pose(box, orientation, model.z_floor)
        placement = _placement(cand, 1, profile, self.ci, model)
        placement.step = len(self.planned) + 1
        self.board.apply(placement)
        self.planned.append(profile.index)
        self.items.remove(profile)
        self.plan.append({"step": len(self.planned), "index": profile.index, "container_idx": int(self.ci),
                          "orientation": int(orientation.index),
                          "center": [float(v) for v in box.center], "size": [float(v) for v in box.size],
                          "bottom": float(box.minimum[2]), "on_floor": bool(float(box.minimum[2]) <= model.z_floor + 1e-6),
                          "archetype": ARCHETYPE})
        return box, ""

    # -- the column: a stack chosen with a one-step look-ahead ---------------
    def shapes(self):
        """The remaining items grouped by (dx, dy, dz, rank, orientation
        index): one representative profile and a count each."""
        out = {}
        for profile in self.items:
            rank = 2 if profile.is_soft else (1 if profile.is_prioritized else 0)
            if rank not in self.ranks:
                continue
            flat = _flat(profile)
            for o in profile.orientations:
                standing = 0 if any(o is f[3] for f in flat) else 1
                key = (round(o.dx, 3), round(o.dy, 3), round(o.dz, 3), rank, standing)
                if key not in out:
                    out[key] = [profile, o, 0]
                out[key][2] += 1
        return out

    def value_of(self, profile, o) -> float:
        """A box's worth at the platform's prices: its fill, its soft or
        priority share, and a count term for the threshold."""
        v = o.dx * o.dy * o.dz
        value = 1.0 + 0.1 * 28.7 * v / self.capacity
        if profile.is_soft:
            value += 14.1 / max(1, self.n_soft)
        if profile.is_prioritized:
            value += 14.3 / max(1, self.n_prio)
        return value

    def fits(self, key, level, top_fp, lock, width, width_limit, depth, model) -> bool:
        dx, dy, dz, rank, _standing = key
        if dy > depth + 1e-9 or dx > width_limit + 1e-9:
            return False
        if width > 0.0 and dx > width + 1e-9:
            return False
        if top_fp is not None and (dx > top_fp[0] + 1e-9 or dy > top_fp[1] + 1e-9):
            return False
        if lock is not None and rank != lock:
            return False  # nothing goes on soft or priority cargo but its own kind
        if level + dz > model.z_ceiling - (self.config.inclusion_clearance + self.config.anchor_slack) + 1e-9:
            return False
        return self.band_ok(model, level, dz)

    def completion(self, counts, level, top_fp, lock, width, width_limit, depth, model) -> float:
        """The value of the rest of the column filled greedily (the best
        single box at each step), a plain geometric estimate."""
        total = 0.0
        counts = dict(counts)
        while True:
            best = None
            for key, (profile, o, n) in counts.items():
                if n <= 0 or not self.fits(key, level, top_fp, lock, width, width_limit, depth, model):
                    continue
                value = self.value_of(profile, o)
                if best is None or value > best[0]:
                    best = (value, key, profile, o)
            if best is None:
                return total
            value, key, profile, o = best
            total += value
            counts[key] = [profile, o, counts[key][2] - 1]
            dx, dy, dz, rank, _standing = key
            level = level + dz
            top_fp = (dx, dy)
            if width == 0.0:
                width = dx
            if rank in (1, 2):
                lock = rank

    def column(self, x_left: float, y_front: float, y_back: float, width_limit: float) -> float:
        """A stack of boxes at the column's left edge within the row strip;
        returns the column's width (0 when nothing fits).  Each box is the
        one whose placement plus a greedy completion of the column is worth
        the most at the platform's prices -- so a standing box goes in only
        where it is worth more than the flat boxes it keeps out, and the
        soft cargo takes a column's top where a hard box would not fit the
        transport bands (the simulator carries an item in with no lift
        when its top lands within 0.098 m under the mid-height plane or the
        ceiling, or its bottom within 0.05 m above the mid-height shelf
        level, and it then scrapes the box it lands on)."""
        model = self.board.model(self.ci)
        depth = y_back - y_front
        gap = self.config.settled_clearance + self.config.anchor_slack
        width = 0.0
        top_fp = None
        lock = None
        level = float(model.z_floor)
        failed: set = set()
        while self.items:
            counts = self.shapes()
            best = None
            for key, (profile, o, n) in counts.items():
                if key in failed or not self.fits(key, level, top_fp, lock, width, width_limit, depth, model):
                    continue
                dx, dy, dz, rank, _standing = key
                rest = dict(counts)
                rest[key] = [profile, o, n - 1]
                value = self.value_of(profile, o) + self.completion(
                    rest, level + dz, (dx, dy), rank if rank in (1, 2) else lock,
                    width if width > 0.0 else dx, width_limit, depth, model)
                if best is None or value > best[0]:
                    best = (value, key, profile, o)
            if best is None:
                break
            _v, key, profile, o = best
            dx, dy, dz, rank, _standing = key
            box, why = self.place(profile, o, x_left + dx / 2.0, y_back - dy / 2.0)
            if box is None:
                failed.add(key)
                continue
            if width == 0.0:
                width = dx + gap
            top_fp = (dx, dy)
            level = float(box.maximum[2])
            if rank in (1, 2):
                lock = rank
            failed = set()
        return width

    def band_ok(self, model, bottom: float, dz: float) -> bool:
        from ._reuse import SIMULATOR_DROP_HEIGHT

        lift = float(SIMULATOR_DROP_HEIGHT) + 0.018
        raw = model.raw
        height = float(raw["height"]); thickness = float(raw["thickness"]); buffer = float(raw.get("buffer", 0.0))
        mid_ceiling = height / 2.0 + buffer
        ceiling = height + buffer - thickness
        shelf_rest = height / 2.0 + thickness + buffer
        top = bottom + dz
        if bottom > model.z_floor + 1e-6:
            # resting on a box: no lift when the bottom sits in the shelf-rest window
            if 0.0 <= bottom - shelf_rest <= 0.05 + 1e-9:
                return False
        for c in (mid_ceiling, ceiling):
            if 0.0 <= c - top < lift + 1e-9:
                return False
        return True

    def row(self, y_back: float, depth: float) -> float:
        """Columns across one row strip; returns the strip's front line."""
        model = self.board.model(self.ci)
        rect = model.floor_rect
        wall = self.config.inclusion_clearance + self.config.anchor_slack
        y_front = y_back - depth
        if y_front < rect.y_min - 1e-9:
            return y_back
        x = model.x_limit_at_height(model.z_floor) + wall
        for shelf in model.shelves:
            # the small shelf's plate sits at mid-height along the left
            # wall: a column under its edge cannot rise past it
            if shelf.name == "small_shelf":
                x = max(x, float(shelf.maximum[0]) + self.config.settled_clearance + self.config.anchor_slack + 0.002)
        x_right = rect.x_max
        while x < x_right - 0.1 and self.items:
            width = self.column(x, y_front, y_back, x_right - x)
            if width <= 0.0:
                break
            x += width
        return y_front

    def tops(self, ranks: set, deadline: float, step: float = 0.04) -> None:
        """The leftovers: every level of the height map from the floor up,
        a deep-first, left-first sweep of the anchors for every remaining
        item of the given ranks (priority before soft, biggest first); a
        pose rests on a level patch and goes through the pose check."""
        import numpy as np
        from wedge_rl.stack import skyline

        model = self.board.model(self.ci)
        container = self.board.container(self.ci)
        rect = model.floor_rect
        wall = self.config.inclusion_clearance + self.config.anchor_slack
        level = float(model.z_floor)
        tolerance = 0.01
        while level < model.z_ceiling - 0.15:
            if time.perf_counter() >= deadline:
                return
            sky = skyline(container, model, step=step)
            xs_all, ys_all, tops_map = sky
            queue = sorted([p for p in self.items if (2 if p.is_soft else (1 if p.is_prioritized else 0)) in ranks],
                           key=lambda p: (0 if p.is_prioritized else 1, -p.max_footprint, -p.mass))
            for profile in queue:
                done = False
                for o in profile.orientations:
                    dx, dy, dz = o.dx, o.dy, o.dz
                    if not self.band_ok(model, level, dz) or level + dz > model.z_ceiling - wall:
                        continue
                    x_min = model.x_limit_at_height(level) + wall + dx / 2.0
                    for y in np.arange(rect.y_max - dy / 2.0, rect.y_min + dy / 2.0 - 1e-9, -step):
                        iy = (ys_all >= y - dy / 2.0 + 1e-9) & (ys_all <= y + dy / 2.0 - 1e-9)
                        if not iy.any():
                            continue
                        for x in np.arange(x_min, rect.x_max - dx / 2.0 + 1e-9, step):
                            ix = (xs_all >= x - dx / 2.0 + 1e-9) & (xs_all <= x + dx / 2.0 - 1e-9)
                            if not ix.any():
                                continue
                            under = tops_map[np.ix_(ix, iy)]
                            if float(under.max()) > level + tolerance or float((np.abs(under - level) <= tolerance).mean()) < 0.9:
                                continue
                            box, _why = self.place(profile, o, float(x), float(y))
                            if box is not None:
                                done = True
                                break
                        if done:
                            break
                    if done:
                        break
                if done:
                    sky = skyline(container, model, step=step)
                    xs_all, ys_all, tops_map = sky
            higher = sorted({round(float(t), 3) for t in np.asarray(tops_map).ravel() if float(t) > level + tolerance})
            if not higher:
                return
            level = higher[0]

    def run(self, depths: list[float], deadline: float) -> int:
        model = self.board.model(self.ci)
        rect = model.floor_rect
        gap = self.config.settled_clearance + self.config.anchor_slack
        y_back = rect.y_max
        self.ranks = {0}
        for depth in depths:
            if time.perf_counter() >= deadline or not self.items:
                break
            if y_back - depth < rect.y_min - 1e-9:
                continue
            front = self.row(y_back, depth)
            if front >= y_back - 1e-9:
                break
            y_back = front - gap
        self.ranks = {0, 1, 2}
        self.tops({1}, deadline)
        self.tops({2}, deadline)
        self.tops({0}, deadline)
        return len(self.planned)


def pack_layers(agent, item_list: list[dict], deadline: float, log=None) -> tuple[list[int], list[dict]]:
    """Returns ``(order, plan)`` in the planner's format: the planned items in
    placement order, then the unplanned ones."""
    config = agent.config
    profiles = {p.index: p for p in (cls.classify_item(int(i["index"]), i, config) for i in item_list)}
    board0 = agent.board
    priority_idx = [i for i, m in enumerate(board0.models) if m.is_prioritized]
    normal_idx = [i for i, m in enumerate(board0.models) if not m.is_prioritized] or list(range(len(board0.models)))
    max_rows = int(getattr(config, "layers_max_rows", 4))
    max_layouts = int(getattr(config, "layers_max_layouts", 24))

    def best_fill(container_idx: int, items: list, base_containers: list):
        """The depth sequence with the most boxes for this container and
        these items, each tried on a scratch copy of ``base_containers``."""
        if not items:
            return None
        depths = _depth_options(items)
        model = board0.model(container_idx)
        usable = model.floor_rect.y_max - model.floor_rect.y_min
        gap = config.settled_clearance + config.anchor_slack
        sequences = []
        for n in range(1, max_rows + 1):
            for seq in itertools.product(depths, repeat=n):
                if sum(seq) + gap * (n - 1) <= usable + 1e-9:
                    sequences.append(list(seq))
        # the fuller sequences first (the most floor depth used), then the
        # deeper rows first; capped by the budget of layouts
        sequences.sort(key=lambda s: (-sum(s), [-d for d in s]))
        sequences = sequences[:max_layouts]
        best = None
        longest = 0.0
        for seq in sequences:
            if time.perf_counter() + longest >= deadline:
                break
            t0 = time.perf_counter()
            scratch = copy.deepcopy(agent)  # shallow enough: the board is rebuilt in _Fill
            scratch.board = layer1.Board(copy.deepcopy(base_containers), config)
            fill = _Fill(scratch, container_idx, items, config, log)
            count = fill.run(seq, deadline)
            longest = max(longest, time.perf_counter() - t0)
            volume = sum(e["size"][0] * e["size"][1] * e["size"][2] for e in fill.plan)
            key = (count, volume)
            if log:
                log(f"  [layers] c{container_idx} depths {seq}: {count} boxes, {volume:.2f} m^3")
            if best is None or key > best[0]:
                best = (key, fill)
        return best[1] if best is not None else None

    plan: list[dict] = []
    planned: list[int] = []
    containers = copy.deepcopy(board0.containers)
    for c in containers:
        c.setdefault("packed_items", [])

    def commit(fill):
        nonlocal containers
        if fill is None:
            return
        for e in fill.plan:
            e["step"] = len(planned) + 1
            planned.append(int(e["index"]))
            plan.append(e)
        containers = fill.containers

    remaining = list(profiles.values())
    for ci in priority_idx:
        prio = [p for p in remaining if p.is_prioritized]
        commit(best_fill(ci, prio, containers))
        remaining = [p for p in remaining if p.index not in set(planned)]
    for ci in normal_idx:
        if ci in priority_idx:
            continue
        # every class in one fill: the column chooser ranks hard before
        # priority before soft, so the soft cargo takes the tops and the
        # leftovers, and the cover rule keeps anything off it afterwards
        mine = [p for p in remaining if not (p.is_prioritized and priority_idx)]
        commit(best_fill(ci, mine, containers))
        remaining = [p for p in remaining if p.index not in set(planned)]
    if priority_idx and getattr(config, "plan_normal_in_priority_container", False):
        for ci in priority_idx:
            hard = [p for p in remaining if not p.is_soft and not p.is_prioritized]
            commit(best_fill(ci, hard, containers))
            remaining = [p for p in remaining if p.index not in set(planned)]
    left = [p.index for p in remaining]
    return planned + left, plan
