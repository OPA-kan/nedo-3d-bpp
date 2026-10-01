"""The pocket guard: soft cargo on the floor keeps the pockets the hard
cargo still to come will need.

On the v28 end states of the Task C physics suite, 52 of the 87 small
boxes on the floor -- every one of them soft -- stand where the biggest
hard box left unplaced would otherwise have a floor pose (29 of 48
episodes; 19 of 57 on Task B, 13 episodes); no small hard box does.  The
ladder's soft archetypes put a soft box on a floor edge when it arrives
early, with nothing to stand it on yet, and that edge is the pocket a
0.65 x 0.45 or 0.75 x 0.56 box needs later.

``SoftPocketSelector`` is a ``layer1.choose_for_item`` selector that acts
on soft items only, when the ladder's pick is a floor pose: among the
survivors it takes the one after which the load keeps the most level,
reachable floor slots for the hard classes still expected
(``room.RoomScorer``), when that beats the ladder's pick by a margin.
Which classes are expected, and how much each weighs, comes from
``ClassFrequencies``: a Dirichlet prior over the sample stream's hard
classes updated with every item seen, and the chance that a class still
arrives before the stream ends (the remaining count from the sample's
items per container, less what has been seen).  Late in the episode
nothing is expected any more and the guard stands down.
"""

from __future__ import annotations

import math
import time

import numpy as np

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

    @property
    def remaining(self) -> float:
        return max(0.0, self.expected_total - self.seen_count)

    def arrival_probabilities(self) -> list[tuple[float, float, float, float]]:
        """(l, w, h, P(at least one more of this class arrives)) per hard
        class, where the per-item probability is the class's posterior
        share of all items seen (soft ones included in the denominator)."""
        total_items = float(self.seen_count) + sum(self.counts.values())
        remaining = self.remaining
        out = []
        for (l, w, h), count in self.counts.items():
            p = count / max(total_items, 1e-9)
            arrive = 1.0 - (1.0 - p) ** remaining if remaining > 0 else 0.0
            out.append((l, w, h, float(arrive)))
        return out


class SoftPocketSelector:
    """See the module docstring.  Returns ``(candidate, archetype)`` to
    override the ladder's pick, or None."""

    def __init__(self, config):
        self.config = config
        self.margin = float(getattr(config, "pocket_guard_margin", 0.25))
        self.budget = float(getattr(config, "pocket_guard_seconds", 0.6))
        self.min_probability = float(getattr(config, "pocket_guard_min_probability", 0.5))
        self.min_footprint = float(getattr(config, "pocket_guard_min_footprint", 0.2))
        self.k = int(getattr(config, "pocket_guard_k", 12))
        self.scorer = RoomScorer(config, [], cell=float(getattr(config, "room_selector_cell", 0.05)),
                                 tolerance=float(getattr(config, "room_selector_tolerance", 0.02)))
        self.frequencies: ClassFrequencies | None = None
        self.calls = 0
        self.overrides = 0
        self.seconds = 0.0

    def start(self, containers: int) -> None:
        self.frequencies = ClassFrequencies(
            prior_count=float(getattr(self.config, "pocket_guard_prior", 4.0)),
            items_per_container=float(getattr(self.config, "pocket_guard_items_per_container", 41.0)),
            containers=containers)

    def observe(self, pool: list, containers: int) -> None:
        if self.frequencies is None:
            self.start(containers)
        self.frequencies.observe(pool)

    def classes(self) -> list[tuple[float, float, float, float]]:
        """The hard classes with a large footprint still likely to arrive,
        weighted by that chance."""
        if self.frequencies is None:
            return []
        out = []
        for l, w, h, p in self.frequencies.arrival_probabilities():
            if l * w >= self.min_footprint and p >= self.min_probability:
                out.append((l, w, h, p))
        return out

    def __call__(self, survivors, chosen, chosen_archetype, board, container_idx, profile):
        if not getattr(profile, "is_soft", False) or chosen is None or chosen.surface != "floor":
            return None
        if len(survivors) < 2:
            return None
        classes = self.classes()
        if not classes:
            return None
        self.calls += 1
        t0 = time.perf_counter()
        self.scorer.classes = classes
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
        label = sorted(pick.archetypes)[0] if pick.archetypes else chosen_archetype
        return pick, f"pocket/{label}"
