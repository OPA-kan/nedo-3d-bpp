"""The ladder's own future as the judge of its floor choices.

``FutureSelector`` is a ``layer1.choose_for_item`` selector
(``config.future_selector``): among the ladder's first ``k`` survivors
(its own pick always among them), each is applied to the board in turn
and the ladder itself -- the same rungs, no selector -- packs ``futures``
sampled continuations of the stream from there until it declines or
``length`` items are placed; the candidate after which the most items
stand replaces the ladder's pick when it beats it by ``margin`` items.

Why the ladder and not a packer: the rollout selector of v18
(``room.RolloutSelector``) judged the candidates by a heightmap packer
that fits 15-17 of 41 on an empty floor, where the ladder fits 19-27, and
lost; the value of a floor pose is what the ladder makes of the room it
leaves, so the ladder has to be the judge (docs/theory, section 10: the
virtual future rollout reuses the Task 1 macros).

The futures are drawn from the SKU mix: the sample's seven classes by
their frequencies (``room.SKU_MIX``), or, with ``future_selector_mix``
"seen", the classes placed and in view so far by their counts, the
sample's mix as the prior while fewer than ten have been seen.  The
rollout applies and withdraws its placements on the live board
(``Board.apply`` / ``Board.undo_last``), so the board is as it was when
the selector returns.
"""

from __future__ import annotations

import collections
import dataclasses
import math
import time

import numpy as np

from . import classify as cls
from . import layer1

# the official SKU mix: (length, width, height, mass, soft, weight)
SKU_MIX = [
    (0.55, 0.40, 0.24, 8.0, False, 13), (0.65, 0.45, 0.25, 13.0, False, 11),
    (0.75, 0.56, 0.27, 18.0, False, 4), (0.50, 0.40, 0.40, 10.0, True, 2),
    (0.45, 0.30, 0.20, 5.0, True, 2), (0.65, 0.35, 0.23, 12.0, True, 5),
    (0.60, 0.30, 0.25, 9.0, True, 4),
]
PRIOR_WEIGHT = 10.0


class FutureSelector:
    def __init__(self, config):
        self.config = config
        self.k = int(getattr(config, "future_selector_k", 3))
        self.futures = int(getattr(config, "future_selector_futures", 2))
        self.length = int(getattr(config, "future_selector_length", 24))
        self.margin = float(getattr(config, "future_selector_margin", 0.5))
        self.budget = float(getattr(config, "future_selector_seconds", 0.0))
        self.mix_mode = str(getattr(config, "future_selector_mix", "seen"))
        self.rng = np.random.default_rng(int(getattr(config, "future_selector_seed", 7)))
        # the judge is the ladder alone: no selector of any kind inside
        self.inner = dataclasses.replace(
            config, future_selector=False, rollout_selector=False, room_selector=False,
            level_selector=False,
        )
        self.calls = 0
        self.overrides = 0
        self.seconds = 0.0
        self.decisions = 0
        self._serial = 0

    # -- the stream's classes ----------------------------------------------
    def _mix(self, board, profile):
        prior = {(l, w, h): (m, soft, float(wt)) for l, w, h, m, soft, wt in SKU_MIX}
        if self.mix_mode != "seen":
            return prior
        seen: collections.Counter = collections.Counter()
        masses: dict = {}
        for placements in board.placements:
            for p in placements:
                item = p.profile.item
                key = (float(item["length"]), float(item["width"]), float(item["height"]))
                seen[key] += 1
                masses[key] = (float(p.profile.mass), bool(p.profile.is_soft))
        item = profile.item
        key = (float(item["length"]), float(item["width"]), float(item["height"]))
        seen[key] += 1
        masses[key] = (float(profile.mass), bool(profile.is_soft))
        total = sum(seen.values())
        if total < 10:
            return prior
        mix = {}
        prior_total = sum(v[2] for v in prior.values())
        for key, (m, soft, wt) in prior.items():
            mix[key] = (m, soft, PRIOR_WEIGHT * wt / prior_total)
        for key, n in seen.items():
            m, soft = masses[key]
            old = mix.get(key, (m, soft, 0.0))
            mix[key] = (old[0], old[1], old[2] + float(n))
        return mix

    def sample_futures(self, board, profile):
        mix = self._mix(board, profile)
        keys = list(mix)
        weights = np.asarray([mix[k][2] for k in keys], dtype=float)
        p = weights / weights.sum()
        out = []
        for _ in range(self.futures):
            picks = self.rng.choice(len(keys), size=self.length, p=p)
            out.append([(keys[i], mix[keys[i]][0], mix[keys[i]][1]) for i in picks])
        return out

    # -- the rollout ---------------------------------------------------------
    def _profile(self, dims, mass, soft):
        self._serial += 1
        l, w, h = dims
        item = {"index": -1000 - self._serial, "length": l, "width": w, "height": h,
                "mass": mass, "is_soft": bool(soft), "is_prioritized": False}
        return cls.classify_item(int(item["index"]), item, self.inner)

    def rollout(self, board, future, deadline: float | None) -> float:
        placed = 0
        volume = 0.0
        applied: list[int] = []
        try:
            for dims, mass, soft in future:
                if deadline is not None and time.perf_counter() > deadline:
                    break
                profile = self._profile(dims, mass, soft)
                decision = layer1.choose_for_item(board, profile, self.inner)
                self.decisions += 1
                if decision is None:
                    break
                board.apply(decision.placement)
                applied.append(int(decision.placement.container_idx))
                placed += 1
                volume += float(decision.placement.volume)
        finally:
            for ci in reversed(applied):
                board.undo_last(ci)
        return placed + 0.01 * volume

    def score(self, board, container_idx, candidate, archetype, profile, futures, deadline) -> float:
        placement = layer1.build_placement(candidate, archetype, board, container_idx, profile, self.config)
        board.apply(placement)
        try:
            return float(np.mean([self.rollout(board, f, deadline) for f in futures]))
        finally:
            board.undo_last(container_idx)

    # -- the selector ----------------------------------------------------------
    def __call__(self, survivors, chosen, chosen_archetype, board, container_idx, profile):
        self.calls += 1
        if len(survivors) < 2:
            return None
        t0 = time.perf_counter()
        deadline = (t0 + self.budget) if self.budget > 0.0 else None
        pool = list(survivors[: self.k])
        if chosen not in pool:
            pool.append(chosen)
        futures = self.sample_futures(board, profile)
        scores = []
        for c in pool:
            if c is chosen:
                arch = chosen_archetype
            else:
                arch = sorted(c.archetypes)[0] if c.archetypes else "alternative"
            if deadline is not None and time.perf_counter() > deadline and c is not chosen:
                scores.append(-math.inf)
                continue
            scores.append(self.score(board, container_idx, c, arch, profile, futures, deadline))
        self.seconds += time.perf_counter() - t0
        i_chosen = next(i for i, c in enumerate(pool) if c is chosen)
        best = int(np.argmax(scores))
        if best == i_chosen or scores[best] <= scores[i_chosen] + self.margin:
            return None
        self.overrides += 1
        pick = pool[best]
        label = sorted(pick.archetypes)[0] if pick.archetypes else "alternative"
        return pick, f"future/{label}"
