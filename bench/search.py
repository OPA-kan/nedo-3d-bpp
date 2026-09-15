"""Search at play time over the ladder's own survivors: the manager's ceiling.

At every decision the ladder makes, the candidates it vetoed down to
(``Decision.survivors``) are each applied to a copy of the episode and the
episode is continued to the end with the inner arm (the ladder with the
stack option as Layer 2), on the analytic model.  The survivor whose
continuation fills most is taken.  This is one-step search with full
rollouts: it knows the rest of the stream, which a Task C agent does not,
and it costs minutes per decision, so it is a measurement, not an agent.
What a learned Layer-1 ranker could reach is bounded by it the way the
executors' beams bounded them.
"""

from __future__ import annotations

import copy
import time

from rule_alpha import layer1

from .rollouts import EpisodeState


class SearchSelector:
    """``selector(survivors, chosen, chosen_archetype, board, container_idx, profile)``
    for ``layer1.choose_for_item``: the survivor with the best full
    continuation, the ladder's own pick on ties."""

    def __init__(self, scene, inner_arm, k: int = 6, log=None):
        self.scene = scene
        self.inner_arm = inner_arm
        self.k = k
        self.log = log
        self.decisions = 0
        self.searched = 0
        self.overrides = 0
        self.seconds = []

    def _remaining(self, board: layer1.Board, current_index: int) -> list[dict]:
        placed = set()
        for container in board.containers:
            for packed in container.get("packed_items", []):
                placed.add(int(packed["index"]))
        return [dict(i) for i in self.scene.items if int(i["index"]) not in placed and int(i["index"]) != current_index]

    def _score(self, candidate, archetype, board, profile, remaining) -> float:
        branch = EpisodeState(self.scene, self.inner_arm, containers=copy.deepcopy(board.containers),
                              queue=copy.deepcopy(remaining), pool=[dict(profile.item)])
        placement = layer1.build_placement(candidate, archetype, branch.agent.board, candidate.container_idx,
                                           profile, branch.config)
        branch.apply_placement(placement, 0)
        branch.run(999)
        return float(branch.summary()["fill_volume"])

    def __call__(self, survivors, chosen, chosen_archetype, board, container_idx, profile):
        self.decisions += 1
        if len(survivors) < 2:
            return None
        t0 = time.perf_counter()
        order = [chosen] + [c for c in survivors if c is not chosen][: max(0, self.k - 1)]
        remaining = self._remaining(board, int(profile.index))
        best, best_score, chosen_score = None, -1.0, None
        for cand in order:
            archetype = chosen_archetype if cand is chosen else (sorted(cand.archetypes)[0] if cand.archetypes else "alternative")
            score = self._score(cand, archetype, board, profile, remaining)
            if cand is chosen:
                chosen_score = score
            if score > best_score + 1e-9:
                best, best_score = (cand, archetype), score
        self.searched += 1
        self.seconds.append(time.perf_counter() - t0)
        if self.log:
            self.log(f"  [search item {profile.index}] {len(order)} survivors, ladder {chosen_score:.2f}, "
                     f"best {best_score:.2f}, {self.seconds[-1]:.0f}s")
        if best is None or best[0] is chosen or best_score <= chosen_score + 1e-9:
            return None
        self.overrides += 1
        return best

    def stats(self) -> dict:
        return {"decisions": self.decisions, "searched": self.searched, "overrides": self.overrides,
                "seconds_mean": (sum(self.seconds) / len(self.seconds)) if self.seconds else 0.0,
                "seconds_max": max(self.seconds) if self.seconds else 0.0}
