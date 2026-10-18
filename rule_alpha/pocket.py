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
        # config.pocket_guard_phase_prior: while the phase switch reads the
        # high phase (every container's usable surface over the switch's
        # share), at least this many items are taken as still to come
        self.phase_floor: float = 0.0

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

    def set_seen(self, seen, prior_weight: float, min_seen: int) -> None:
        """config.pocket_mix "seen": the counts from the shared tracker
        (``rule_alpha.seen.SeenClasses``) with the foresight scheme --
        ``prior_weight`` pseudo-items over the sample's hard classes, the
        seen hard classes by their counts once ``min_seen`` items have
        been seen, the prior alone before that.  What ``observe`` counts
        (the items seen, the expected remainder) stays."""
        total = float(sum(w for _l, _w, _h, soft, w in SKU_MIX if not soft))
        counts: dict[tuple, float] = {}
        for l, w, h, soft, weight in SKU_MIX:
            if not soft:
                counts[self._key(l, w, h)] = float(prior_weight) * weight / total
        if int(seen.total) >= int(min_seen):
            for (l, w, h), n in seen.hard_classes():
                key = self._key(l, w, h)
                counts[key] = counts.get(key, 0.0) + float(n)
        self.counts = counts

    @property
    def remaining(self) -> float:
        return max(0.0, self.expected_total - self.seen_count, self.phase_floor)

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

    @staticmethod
    def _soft_tops(board, container_idx: int):
        boxes = [b for packed, (b, _s, _p) in zip(board.container(container_idx).get("packed_items", []),
                                                  packed_aabbs_local(board.container(container_idx)))
                 if packed.get("is_soft")]
        if not boxes:
            return np.zeros((0, 5))
        return np.array([[float(b.minimum[0]), float(b.maximum[0]), float(b.minimum[1]), float(b.maximum[1]),
                          float(b.maximum[2])] for b in boxes])

    @staticmethod
    def _rests_on(box: AABB, tops, tolerance: float = 0.02) -> bool:
        if tops is None or len(tops) == 0:
            return False
        bottom = float(box.minimum[2])
        near = np.abs(tops[:, 4] - bottom) <= tolerance
        if not near.any():
            return False
        t = tops[near]
        ox = np.minimum(t[:, 1], float(box.maximum[0])) - np.maximum(t[:, 0], float(box.minimum[0]))
        oy = np.minimum(t[:, 3], float(box.maximum[1])) - np.maximum(t[:, 2], float(box.minimum[1]))
        return bool(((ox > 0.01) & (oy > 0.01)).any())

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
        self.all_rooms = bool(getattr(config, "pocket_guard_all_rooms", False))
        self.tie_soft_top = bool(getattr(config, "pocket_guard_tie_soft_top", False))
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

    def observe(self, pool: list, containers: int, seen=None) -> None:
        """Every pool item, once; with ``seen`` (config.pocket_mix "seen")
        the class frequencies are then taken from that tracker."""
        freq = self._ensure(containers)
        freq.observe(pool)
        if seen is not None:
            freq.set_seen(seen, float(getattr(self.config, "pocket_mix_prior", 10.0)),
                          int(getattr(self.config, "pocket_mix_min_seen", 10)))

    def set_phase(self, phase_low: bool | None, containers: int) -> None:
        """The phase switch's reading (config.pocket_guard_phase_prior): in
        the high phase the board still has room the stream will fill, so
        the guard does not stand down on the count prior alone; in the low
        phase (or with no reading) the prior speaks."""
        freq = self._ensure(containers)
        if phase_low is None or phase_low:
            freq.phase_floor = 0.0
        else:
            freq.phase_floor = float(getattr(self.config, "pocket_guard_phase_items", 10.0)) * max(1, int(containers))

    def classes(self) -> list[tuple[float, float, float, float]]:
        """The hard classes with a large footprint still likely to arrive,
        weighted by that chance."""
        if self.frequencies is None:
            return []
        return [(l, w, h, p) for l, w, h, p in self.frequencies.arrival_probabilities()
                if l * w >= self.min_footprint and p >= self.min_probability]

    def alternative(self, board, profile, mass: float, container_idx: int, chosen_box: AABB, deadline: float,
                    soft: bool = True):
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
            # a soft box is dead ground for the hard classes; a hard one is
            # a level like any packed top
            alt_name = SOFT_ALT if soft else "pocket-hard"
            chosen_score = self.scorer.slots(board, container_idx, extra=dataclasses.replace(chosen_box, name=alt_name))
            cfg = dataclasses.replace(self.config, stack_soft_min_support=0.0, stack_soft_standing=False)
            best = None
            best_top = None  # the best pose on a soft top (pocket_guard_tie_soft_top)
            order = list(range(len(board.containers)))
            base: dict[int, float] = {}
            if self.all_rooms and len(order) > 1:
                # config.pocket_guard_all_rooms: every container's room
                # counts, so a pose is scored by the whole load's slots --
                # its own container's with the box, every other's as it
                # stands (the home container's slots alone made a pose in
                # a roomier container look better or worse than it is);
                # the home container is searched first, so a deadline cuts
                # the others
                order = [container_idx] + [ci for ci in order if ci != container_idx]
                for ci in order:
                    base[ci] = self.scorer.slots(board, ci)
                chosen_score = chosen_score + sum(v for ci, v in base.items() if ci != container_idx)
            for ci in order:
                if time.perf_counter() > deadline:
                    break
                cands = stack_candidates(board.model(ci), board.container(ci), cfg, profile,
                                         max_candidates=self.max_candidates, mass=float(mass), tower_min=None,
                                         extra_clearance=0.0, z_top=None, dense=self.anchor_step)
                cands = [c for c in cands if c.on_floor or c.support_ratio >= self.min_support]
                soft_tops = self._soft_tops(board, ci) if (self.tie_soft_top and soft) else None
                for c in cands:
                    if time.perf_counter() > deadline:
                        break
                    s = self.scorer.slots(board, ci, extra=dataclasses.replace(c.box, name=alt_name))
                    if base:
                        s += sum(v for cj, v in base.items() if cj != ci)
                    # ties go to the lower pose, then the ladder's own container;
                    # with config.pocket_guard_tie_soft_top a pose on a soft top
                    # first (a soft column keeps the floor the next soft box
                    # would take)
                    on_soft = 0
                    if soft_tops is not None and not c.on_floor:
                        on_soft = 1 if self._rests_on(c.box, soft_tops) else 0
                    key = (round(s, 3), on_soft, -round(c.bottom, 3), 1 if ci == container_idx else 0)
                    if best is None or key > best[0]:
                        best = (key, c, ci, s)
                    if on_soft and (best_top is None or key > best_top[0]):
                        best_top = (key, c, ci, s)
        finally:
            self.seconds += time.perf_counter() - t0
        if best is None:
            return None
        if best[3] <= chosen_score + self.margin:
            # config.pocket_guard_tie_soft_top: a soft top that keeps at
            # least the room the ladder's floor pose keeps wins without the
            # margin (the floor pose spreads the carpet, the column does not)
            if best_top is None or best_top[3] < chosen_score - 1e-9:
                return None
            best = best_top
        self.overrides += 1
        return best[1], best[2], chosen_score, best[3]
