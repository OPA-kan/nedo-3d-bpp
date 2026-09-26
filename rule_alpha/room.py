"""The room a load keeps for the boxes still to come.

Task C ends at the first item with no legal pose, and on the 48-scene
suite that item is the 0.65 x 0.45 box 12 times of 44, the 0.75 x 0.56
box 8 times, the 0.55 x 0.40 box 9: the load runs out of level,
reachable slots of those footprints long before it runs out of volume
(a third of the floor free at the decline, in strips no box fits).  The
ladder picks among its survivors by archetype; ``RoomSelector`` re-ranks
the first few of them by the slots the load keeps after each.

A slot: a footprint's worth of cells on one level (tops within
``tolerance`` of each other, or the floor) that the transport sweep can
reach -- nothing between it and the opening rises above the level plus
the lift -- and that fits under the ceiling.  Counted on a heightmap
with a cell of ``cell`` metres, overlapping positions divided by the
footprint's cells, so the count is about the number of boxes that
would fit side by side.
"""

from __future__ import annotations

import math
import time

import numpy as np

from ._reuse import AABB, packed_aabbs_local

# the simulator carries an item in at its target height plus this lift,
# and the sweep needs the settled clearance under it
LIFT = 0.08


def parse_classes(spec: str) -> list[tuple[float, float, float, float]]:
    """``"0.65x0.45x0.25:1,0.75x0.56x0.27:0.5"`` -> [(l, w, h, weight), ...]."""
    out = []
    for part in str(spec).replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        dims, _sep, weight = part.partition(":")
        l, w, h = (float(v) for v in dims.lower().split("x"))
        out.append((l, w, h, float(weight) if weight else 1.0))
    return out


class RoomScorer:
    def __init__(self, config, classes, cell: float = 0.05, tolerance: float = 0.02):
        self.config = config
        self.classes = classes
        self.cell = float(cell)
        self.tolerance = float(tolerance)
        self.clearance = float(getattr(config, "settled_clearance", 0.026))
        self.wall = float(getattr(config, "inclusion_clearance", 0.016))

    def heightmap(self, board, container_idx: int, extra: AABB | None = None):
        model = board.model(container_idx)
        rect = model.floor_rect
        cell = self.cell
        xs = np.arange(rect.x_min + cell / 2.0, rect.x_max, cell)
        ys = np.arange(rect.y_min + cell / 2.0, rect.y_max, cell)  # from the opening to the back
        height = np.full((len(ys), len(xs)), float(model.z_floor))
        xlim = model.x_limit_at_height(model.z_floor)
        height[:, xs < xlim] = np.inf  # the chamfer pocket: no floor there
        boxes = [b for b, _s, _p in packed_aabbs_local(board.container(container_idx))]
        if extra is not None:
            boxes.append(extra)
        for b in boxes:
            ix = (xs > float(b.minimum[0])) & (xs < float(b.maximum[0]))
            iy = (ys > float(b.minimum[1])) & (ys < float(b.maximum[1]))
            if ix.any() and iy.any():
                sub = height[np.ix_(iy, ix)]
                height[np.ix_(iy, ix)] = np.maximum(sub, float(b.maximum[2]))
        return model, xs, ys, height

    @staticmethod
    def _windows_all(mask: np.ndarray, ny: int, nx: int) -> np.ndarray:
        """For every (j, i): is the ny x nx window whose lowest-y, lowest-x
        corner is (j, i) all True?  Via a 2D prefix sum."""
        if ny > mask.shape[0] or nx > mask.shape[1]:
            return np.zeros((0, 0), dtype=bool)
        s = np.zeros((mask.shape[0] + 1, mask.shape[1] + 1), dtype=np.int32)
        s[1:, 1:] = np.cumsum(np.cumsum(mask.astype(np.int32), axis=0), axis=1)
        total = s[ny:, nx:] - s[:-ny, nx:] - s[ny:, :-nx] + s[:-ny, :-nx]
        return total == ny * nx

    def slots(self, board, container_idx: int, extra: AABB | None = None) -> float:
        model, xs, ys, height = self.heightmap(board, container_idx, extra)
        ceiling = float(model.z_ceiling) - self.wall
        finite = np.isfinite(height)
        levels = sorted({round(float(v), 2) for v in height[finite]})
        # the tallest top between each cell and the opening (rows run from
        # the opening), per column: what the sweep to that cell passes over
        front = np.full_like(height, -np.inf)
        run = np.full(height.shape[1], -np.inf)
        for j in range(height.shape[0]):
            front[j] = run
            run = np.maximum(run, np.where(finite[j], height[j], -np.inf))
        score = 0.0
        for l, w, h, weight in self.classes:
            best = 0.0
            for dx, dy in ((l, w), (w, l)):
                nx = max(1, int(round(dx / self.cell)))
                ny = max(1, int(round(dy / self.cell)))
                count = 0.0
                for level in levels:
                    if level + h > ceiling + 1e-9:
                        continue
                    on_level = finite & (np.abs(height - level) <= self.tolerance)
                    if on_level.sum() < nx * ny:
                        continue
                    # reachable: the sweep at level + lift clears what is in front
                    clear = front <= level + LIFT - self.clearance + 1e-9
                    ok = self._windows_all(on_level & clear, ny, nx)
                    count += float(ok.sum()) / float(nx * ny)
                best = max(best, count)
            score += weight * best
        return score


class RoomSelector:
    """A ``layer1.choose_for_item`` selector: among the first ``k``
    survivors (the ladder's pick always among them) the one after which
    the load keeps the most slots for the reference classes, when that
    beats the ladder's pick by ``margin`` slots."""

    def __init__(self, config):
        self.config = config
        self.k = int(getattr(config, "room_selector_k", 6))
        self.margin = float(getattr(config, "room_selector_margin", 0.25))
        self.budget = float(getattr(config, "room_selector_seconds", 1.0))
        self.scorer = RoomScorer(config, parse_classes(getattr(config, "room_selector_classes",
                                                                "0.65x0.45x0.25:1,0.75x0.56x0.27:0.7,0.55x0.40x0.24:0.5")),
                                 cell=float(getattr(config, "room_selector_cell", 0.05)),
                                 tolerance=float(getattr(config, "room_selector_tolerance", 0.02)))
        self.calls = 0
        self.overrides = 0
        self.seconds = 0.0

    def __call__(self, survivors, chosen, chosen_archetype, board, container_idx, profile):
        self.calls += 1
        if len(survivors) < 2:
            return None
        t0 = time.perf_counter()
        pool = list(survivors[: self.k])
        if chosen not in pool:
            pool.append(chosen)
        scores = []
        for c in pool:
            if time.perf_counter() - t0 > self.budget and c is not chosen:
                scores.append(-math.inf)
                continue
            scores.append(self.scorer.slots(board, container_idx, extra=c.box))
        self.seconds += time.perf_counter() - t0
        i_chosen = next(i for i, c in enumerate(pool) if c is chosen)
        best = int(np.argmax(scores))
        if best == i_chosen or scores[best] <= scores[i_chosen] + self.margin:
            return None
        self.overrides += 1
        pick = pool[best]
        label = sorted(pick.archetypes)[0] if pick.archetypes else "alternative"
        return pick, f"room/{label}"


# the official SKU mix (bench.scenes.SKUS: length, width, height, soft, weight)
SKU_MIX = [
    (0.55, 0.40, 0.24, False, 13), (0.65, 0.45, 0.25, False, 11), (0.75, 0.56, 0.27, False, 4),
    (0.50, 0.40, 0.40, True, 2), (0.45, 0.30, 0.20, True, 2), (0.65, 0.35, 0.23, True, 5), (0.60, 0.30, 0.25, True, 4),
]


class RolloutSelector:
    """A ``layer1.choose_for_item`` selector: among the first ``k``
    survivors (the ladder's pick always among them) the one after which
    a fast heightmap packer fits the most of ``futures`` sampled
    continuations of the stream (``length`` items each, the SKU mix), when
    that beats the ladder's pick by ``margin`` items.

    The packer: for each future item, flat orientations, the lowest level
    (tops within the tolerance) with a footprint's worth of cells that the
    transport sweep reaches, the deepest then the leftmost such window; the
    box is stamped on the heightmap; the first item with no window ends the
    rollout, as it would end the episode."""

    def __init__(self, config):
        self.config = config
        self.k = int(getattr(config, "rollout_selector_k", 6))
        self.futures = int(getattr(config, "rollout_selector_futures", 4))
        self.length = int(getattr(config, "rollout_selector_length", 12))
        self.margin = float(getattr(config, "rollout_selector_margin", 0.5))
        self.budget = float(getattr(config, "rollout_selector_seconds", 1.2))
        self.scorer = RoomScorer(config, [], cell=float(getattr(config, "room_selector_cell", 0.05)),
                                 tolerance=float(getattr(config, "room_selector_tolerance", 0.02)))
        self.rng = np.random.default_rng(int(getattr(config, "rollout_selector_seed", 7)))
        self.calls = 0
        self.overrides = 0
        self.seconds = 0.0
        weights = np.asarray([s[4] for s in SKU_MIX], dtype=float)
        self._p = weights / weights.sum()

    def sample_futures(self):
        return [[SKU_MIX[i][:3] for i in self.rng.choice(len(SKU_MIX), size=self.length, p=self._p)]
                for _ in range(self.futures)]

    def rollout(self, model, height: np.ndarray, future) -> int:
        sc = self.scorer
        ceiling = float(model.z_ceiling) - sc.wall
        height = height.copy()
        finite = np.isfinite(height)
        placed = 0
        for l, w, h in future:
            best = None
            levels = sorted({round(float(v), 2) for v in height[finite]})
            front = np.full_like(height, -np.inf)
            run = np.full(height.shape[1], -np.inf)
            for j in range(height.shape[0]):
                front[j] = run
                run = np.maximum(run, np.where(finite[j], height[j], -np.inf))
            for level in levels:
                if level + h > ceiling + 1e-9:
                    continue
                on_level = finite & (np.abs(height - level) <= sc.tolerance)
                clear = front <= level + LIFT - sc.clearance + 1e-9
                mask = on_level & clear
                for dx, dy in ((l, w), (w, l)):
                    nx = max(1, int(round(dx / sc.cell)))
                    ny = max(1, int(round(dy / sc.cell)))
                    ok = sc._windows_all(mask, ny, nx)
                    if ok.size and ok.any():
                        js, is_ = np.nonzero(ok)
                        # the deepest (largest y index), then the leftmost
                        order = np.lexsort((is_, -js))
                        j, i = int(js[order[0]]), int(is_[order[0]])
                        best = (j, i, ny, nx)
                        break
                if best is not None:
                    break
            if best is None:
                break
            j, i, ny, nx = best
            height[j:j + ny, i:i + nx] = level + h
            placed += 1
        return placed

    def score(self, board, container_idx: int, box, futures) -> float:
        model, _xs, _ys, height = self.scorer.heightmap(board, container_idx, extra=box)
        return float(np.mean([self.rollout(model, height, f) for f in futures]))

    def __call__(self, survivors, chosen, chosen_archetype, board, container_idx, profile):
        self.calls += 1
        if len(survivors) < 2:
            return None
        t0 = time.perf_counter()
        pool = list(survivors[: self.k])
        if chosen not in pool:
            pool.append(chosen)
        futures = self.sample_futures()
        scores = []
        for c in pool:
            if time.perf_counter() - t0 > self.budget and c is not chosen:
                scores.append(-math.inf)
                continue
            scores.append(self.score(board, container_idx, c.box, futures))
        self.seconds += time.perf_counter() - t0
        i_chosen = next(i for i, c in enumerate(pool) if c is chosen)
        best = int(np.argmax(scores))
        if best == i_chosen or scores[best] <= scores[i_chosen] + self.margin:
            return None
        self.overrides += 1
        pick = pool[best]
        label = sorted(pick.archetypes)[0] if pick.archetypes else "alternative"
        return pick, f"rollout/{label}"
