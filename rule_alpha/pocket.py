"""The pocket guard: soft cargo keeps the room the hard cargo still to
come will need.

On the v28 end states of the Task C physics suite, 52 of the 87 small
boxes on the floor -- every one of them soft -- stand where the biggest
hard box left unplaced would otherwise have a floor pose (29 of 48
episodes; 19 of 57 on Task B, 13 episodes); no small hard box does.  The
ladder's soft archetypes put a soft box on a floor edge when it arrives
early, and that edge, or the sweep past it, is what a 0.65 x 0.45 or
0.75 x 0.56 box needs later.  Traced on six C scenes: at 15 of 18 soft
floor decisions another pose (a floor spot that does not block the
sweep, or a hard top) keeps on average 1.9 more level, reachable slots
for the big hard classes -- and the ladder's survivors never hold it,
so re-ranking them changes nothing.

``PocketGuard.alternative`` is asked after the ladder has decided a
floor pose for a soft item: it generates every pose the geometry allows
(the stack option's candidates, flat only, half the footprint
supported), scores each by the slots the load keeps for the hard
classes still expected (``room.RoomScorer`` on a heightmap where soft
tops are dead ground for hard cargo, since the cover rule forbids hard
on soft), and returns the best when it beats the ladder's pose by a
margin.  Which classes are expected, and how much each weighs, comes
from ``ClassFrequencies``: a Dirichlet prior over the sample stream's
hard classes updated with every item seen, and the chance that a class
still arrives before the stream ends.  Late in the episode nothing is
expected any more and the guard stands down.
"""

from __future__ import annotations

import dataclasses
import time

import numpy as np

from ._reuse import AABB, packed_aabbs_local
from .room import SKU_MIX, RoomScorer


class ClassFrequencies:
    """Hard classes seen so far, with a Dirichlet prior from the sample mix.

    ``prior_count`` pseudo-items are spread over the prior classes by
    their sample weights; a class never seen in the prior gets a slot of
    its own once observed.  ``remaining`` is the expected number of items
    still to come: the sample's items per container times the container
    count, less what has been seen (never below zero)."""

    def __init__(self, prior_count: float = 4.0, items_per_container: float = 41.0, containers: int = 1):
        total = float(sum(w for _l, _w, _h, soft, w in SKU_MIX if not soft))
        self.counts: dict[tuple, float] = {}
        for l, w, h, soft, weight in SKU_MIX:
            if soft:
                continue
            self.counts[self._key(l, w, h)] = prior_count * weight / total
        self.seen: set[int] = set()
        self.seen_count = 0
        self.expected_total = float(items_per_container) * max(1, int(containers))
        # Task A: the manifest is known, so the classes still to come are
        # counted, not estimated (set by ``manifest``)
        self.manifest: dict[tuple, int] | None = None
        self.seen_by_class: dict[tuple, int] = {}

    def set_manifest(self, items: list) -> None:
        counts: dict[tuple, int] = {}
        for item in items:
            if bool(item.get("is_soft", False)):
                continue
            key = self._key(item["length"], item["width"], item["height"])
            counts[key] = counts.get(key, 0) + 1
        self.manifest = counts
        self.expected_total = float(len(items))

    @staticmethod
    def _key(l: float, w: float, h: float) -> tuple:
        return tuple(round(float(v), 2) for v in sorted((l, w, h), reverse=True))

    def observe(self, pool: list) -> None:
        for item in pool:
            idx = int(item.get("index", -1))
            if idx in self.seen:
                continue
            self.seen.add(idx)
            self.seen_count += 1
            if bool(item.get("is_soft", False)):
                continue
            key = self._key(item["length"], item["width"], item["height"])
            self.counts[key] = self.counts.get(key, 0.0) + 1.0
            self.seen_by_class[key] = self.seen_by_class.get(key, 0) + 1

    @property
    def remaining(self) -> float:
        return max(0.0, self.expected_total - self.seen_count)

    def arrival_probabilities(self) -> list[tuple[float, float, float, float]]:
        """(l, w, h, P(at least one more of this class arrives)) per hard
        class, where the per-item probability is the class's posterior
        share of all items seen (soft ones included in the denominator)."""
        if self.manifest is not None:
            # a class still arrives when the manifest holds more of it
            # than has been seen
            return [(l, w, h, 1.0 if n - self.seen_by_class.get((l, w, h), 0) > 0 else 0.0)
                    for (l, w, h), n in self.manifest.items()]
        total_items = float(self.seen_count) + sum(self.counts.values())
        remaining = self.remaining
        out = []
        for (l, w, h), count in self.counts.items():
            p = count / max(total_items, 1e-9)
            arrive = 1.0 - (1.0 - p) ** remaining if remaining > 0 else 0.0
            out.append((l, w, h, float(arrive)))
        return out


SOFT_ALT = "pocket-alt"


class SoftAwareScorer(RoomScorer):
    """The room scorer with soft tops as dead ground: the cover rule
    forbids hard cargo on soft, so a soft box's top is no level for the
    hard classes.  A candidate box named ``pocket-alt`` is treated as
    soft too."""

    def heightmap(self, board, container_idx: int, extra: AABB | None = None):
        model, xs, ys, height = super().heightmap(board, container_idx, extra)
        container = board.container(container_idx)
        boxes = [b for packed, (b, _s, _p) in zip(container.get("packed_items", []), packed_aabbs_local(container))
                 if packed.get("is_soft")]
        if extra is not None and getattr(extra, "name", "") == SOFT_ALT:
            boxes.append(extra)
        for b in boxes:
            ix = (xs > float(b.minimum[0])) & (xs < float(b.maximum[0]))
            iy = (ys > float(b.minimum[1])) & (ys < float(b.maximum[1]))
            if ix.any() and iy.any():
                height[np.ix_(iy, ix)] = np.inf
        return model, xs, ys, height


class PocketGuard:
    """See the module docstring."""

    def __init__(self, config):
        self.config = config
        self.margin = float(getattr(config, "pocket_guard_margin", 0.25))
        self.budget = float(getattr(config, "pocket_guard_seconds", 0.8))
        self.min_probability = float(getattr(config, "pocket_guard_min_probability", 0.5))
        self.min_footprint = float(getattr(config, "pocket_guard_min_footprint", 0.2))
        self.max_candidates = int(getattr(config, "pocket_guard_candidates", 120))
        self.anchor_step = float(getattr(config, "pocket_guard_anchor_step", 0.06))
        self.min_support = float(getattr(config, "pocket_guard_min_support", 0.6))
        self.scorer = SoftAwareScorer(config, [], cell=float(getattr(config, "room_selector_cell", 0.05)),
                                      tolerance=float(getattr(config, "room_selector_tolerance", 0.02)))
        self.frequencies: ClassFrequencies | None = None
        self.calls = 0
        self.overrides = 0
        self.seconds = 0.0

    def _ensure(self, containers: int) -> ClassFrequencies:
        if self.frequencies is None:
            self.frequencies = ClassFrequencies(
                prior_count=float(getattr(self.config, "pocket_guard_prior", 4.0)),
                items_per_container=float(getattr(self.config, "pocket_guard_items_per_container", 41.0)),
                containers=containers)
        return self.frequencies

    def set_manifest(self, items: list, containers: int) -> None:
        """Task A: the whole stream is known."""
        self._ensure(containers).set_manifest(items)

    def observe(self, pool: list, containers: int) -> None:
        self._ensure(containers).observe(pool)

    def classes(self) -> list[tuple[float, float, float, float]]:
        """The hard classes with a large footprint still likely to arrive,
        weighted by that chance."""
        if self.frequencies is None:
            return []
        return [(l, w, h, p) for l, w, h, p in self.frequencies.arrival_probabilities()
                if l * w >= self.min_footprint and p >= self.min_probability]

    def alternative(self, board, profile, mass: float, container_idx: int, chosen_box: AABB, deadline: float):
        """The pose after which the load keeps the most slots for the
        expected hard classes, as ``(stack candidate, container index,
        chosen's slots, best's slots)``, or None when the ladder's pose is
        within the margin of the best (or nothing is expected)."""
        from wedge_rl.stack import stack_candidates

        classes = self.classes()
        if not classes:
            return None
        self.calls += 1
        t0 = time.perf_counter()
        try:
            self.scorer.classes = classes
            chosen_score = self.scorer.slots(board, container_idx, extra=dataclasses.replace(chosen_box, name=SOFT_ALT))
            cfg = dataclasses.replace(self.config, stack_soft_min_support=0.0, stack_soft_standing=False)
            best = None
            for ci in range(len(board.containers)):
                if time.perf_counter() > deadline:
                    break
                cands = stack_candidates(board.model(ci), board.container(ci), cfg, profile,
                                         max_candidates=self.max_candidates, mass=float(mass), tower_min=None,
                                         extra_clearance=0.0, z_top=None, dense=self.anchor_step)
                cands = [c for c in cands if c.on_floor or c.support_ratio >= self.min_support]
                for c in cands:
                    if time.perf_counter() > deadline:
                        break
                    s = self.scorer.slots(board, ci, extra=dataclasses.replace(c.box, name=SOFT_ALT))
                    # ties go to the lower pose, then the ladder's own container
                    key = (round(s, 3), -round(c.bottom, 3), 1 if ci == container_idx else 0)
                    if best is None or key > best[0]:
                        best = (key, c, ci, s)
        finally:
            self.seconds += time.perf_counter() - t0
        if best is None or best[3] <= chosen_score + self.margin:
            return None
        self.overrides += 1
        return best[1], best[2], chosen_score, best[3]
