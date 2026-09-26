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

import numpy as np

from rule_alpha import layer1

from .rollouts import EpisodeState


class SearchSelector:
    """``selector(survivors, chosen, chosen_archetype, board, container_idx, profile)``
    for ``layer1.choose_for_item``: the survivor with the best full
    continuation, the ladder's own pick on ties."""

    def __init__(self, scene, inner_arm, k: int = 6, log=None, streams: int = 0, horizon: int = 999,
                 seed: int = 0, pool_only: bool = False):
        self.scene = scene
        self.inner_arm = inner_arm
        self.k = k
        self.log = log
        # ``pool_only``: the continuation runs over the items the agent can
        # see (the current pool, set by the arm before every decision) and
        # nothing after them -- the search a Task B agent may run; scored by
        # the items it places, the fill breaking ties
        self.pool_only = pool_only
        self.pool = []
        # ``streams`` > 0: the continuation does not read the true stream (a
        # Task C agent cannot) but ``streams`` imagined ones, each ``horizon``
        # items drawn from the SKU mix, and the fills are averaged -- the
        # search an agent could run, as against the ceiling with the true stream
        self.streams = streams
        self.horizon = horizon
        self.rng = np.random.default_rng(seed)
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

    def _futures(self, remaining) -> list[list[dict]]:
        if self.pool_only:
            return [[]]
        if self.streams <= 0:
            return [remaining]
        from wedge_rl.stack import sample_future

        return [sample_future(self.rng, self.horizon, start_index=100000 + 1000 * s) for s in range(self.streams)]

    def _score(self, candidate, archetype, board, profile, futures) -> float:
        fills = []
        for future in futures:
            rest = [dict(i) for i in self.pool if int(i["index"]) != int(profile.index)] if self.pool_only else []
            branch = EpisodeState(self.scene, self.inner_arm, containers=copy.deepcopy(board.containers),
                                  queue=copy.deepcopy(future), pool=[dict(profile.item)] + rest)
            placement = layer1.build_placement(candidate, archetype, branch.agent.board, candidate.container_idx,
                                               profile, branch.config)
            branch.apply_placement(placement, 0)
            branch.run(self.horizon if self.streams > 0 else 999)
            summary = branch.summary()
            if self.pool_only:
                fills.append(float(summary["placed_count"]) + float(summary["fill_volume"]) / 1000.0)
            else:
                fills.append(float(summary["fill_volume"]))
        return float(np.mean(fills))

    def __call__(self, survivors, chosen, chosen_archetype, board, container_idx, profile):
        self.decisions += 1
        if len(survivors) < 2:
            return None
        t0 = time.perf_counter()
        order = [chosen] + [c for c in survivors if c is not chosen][: max(0, self.k - 1)]
        futures = self._futures(self._remaining(board, int(profile.index)))
        best, best_score, chosen_score = None, -1.0, None
        for cand in order:
            archetype = chosen_archetype if cand is chosen else (sorted(cand.archetypes)[0] if cand.archetypes else "alternative")
            score = self._score(cand, archetype, board, profile, futures)
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


class ItemSearchAgent:
    """Task B: which of the visible items goes next.  For each of the first
    ``k`` pool items in the ladder's own order, the item is placed by the
    ladder (its own pose) on a copy of the board and the rest of the pool
    is continued by the ladder; the item whose continuation places the
    most (the fill breaking ties) goes.  The pose search over the ladder's
    survivors gained nothing on Task B (+0.12 items a scene); this is the
    order, which is what the planner has over the ladder."""

    def __init__(self, scene, inner_arm, k: int = 4, log=None):
        self.scene = scene
        self.inner_arm = inner_arm
        self.agent = inner_arm(scene)
        self.k = k
        self.log = log
        self.decisions = 0
        self.searched = 0
        self.overrides = 0
        self.seconds = []

    def get_init_states(self, init_states):
        return self.agent.get_init_states(init_states)

    def optimize(self, item_list):
        return self.agent.optimize(item_list)

    @property
    def last_decision(self):
        return self.agent.last_decision

    @property
    def config(self):
        return self.agent.config

    def _continuation(self, containers, pool, first_index: int) -> float:
        rest = [dict(i) for i in pool if int(i["index"]) != first_index]
        first = next(dict(i) for i in pool if int(i["index"]) == first_index)
        branch = EpisodeState(self.scene, self.inner_arm, containers=copy.deepcopy(containers),
                              queue=[], pool=[first] + rest)
        action, decision = branch.decide()
        if action is None or int(action["item_idx"]) != 0:
            return -1.0  # the ladder would not place this item first
        branch.apply_placement(decision.placement, 0)
        branch.run(999)
        summary = branch.summary()
        return float(summary["placed_count"]) + float(summary["fill_volume"]) / 1000.0

    def policy(self, observation):
        self.decisions += 1
        pool = observation.get("pool_list", [])
        if len(pool) < 2:
            return self.agent.policy(observation)
        t0 = time.perf_counter()
        from rule_alpha import classify as cls

        config = self.agent.config
        profiles = [(i, cls.classify_item(int(item["index"]), item, config)) for i, item in enumerate(pool)]
        ordered = layer1.pool_order(profiles, config)
        candidates = [int(pr.index) for _pi, pr in ordered[: self.k]]
        scores = {idx: self._continuation(observation["container_list"], pool, idx) for idx in candidates}
        self.searched += 1
        best = max(scores, key=lambda i: scores[i])
        ladder_first = candidates[0]
        self.seconds.append(time.perf_counter() - t0)
        if self.log:
            self.log("  [item search] %s -> best %d (ladder %d) %.0fs" % (
                {i: round(s, 2) for i, s in scores.items()}, best, ladder_first, self.seconds[-1]))
        if scores[best] <= scores[ladder_first] + 1e-9 or scores[best] < 0:
            return self.agent.policy(observation)
        self.overrides += 1
        # the chosen item alone in the pool: the ladder's own pose for it
        pool_index = next(i for i, item in enumerate(pool) if int(item["index"]) == best)
        narrowed = dict(observation)
        narrowed["pool_list"] = [pool[pool_index]]
        action = self.agent.policy(narrowed)
        if action is None:
            return self.agent.policy(observation)
        action = dict(action)
        action["item_idx"] = pool_index
        return action

    def stats(self) -> dict:
        return {"decisions": self.decisions, "searched": self.searched, "overrides": self.overrides,
                "seconds_mean": (sum(self.seconds) / len(self.seconds)) if self.seconds else 0.0,
                "seconds_max": max(self.seconds) if self.seconds else 0.0}
