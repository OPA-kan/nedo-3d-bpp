"""Counterfactual labels for candidates, from greedy continuations.

At every decision the ladder makes on the analytic model, the survivors it
chose among are sampled, each sampled candidate is applied to a copy of the
board, and the episode is continued greedily (same rules) for ``horizon``
more decisions.  What that continuation achieves -- how many items it still
places before it declines, how much volume, what board it leaves -- is the
label for the candidate.  A ranker trained on these labels learns "which
candidate leaves the most packable board", which is the question the ladder
answers by hand.

Only the analytic model is used here; ``stable-findings.md`` established that
its episodes track the physics with no bias in placed count.  Labels are
horizon-truncated on purpose: the full continuation costs the whole episode
per candidate, and the bench's own findings say most of a placement's effect
on the future is visible within a few steps.
"""

from __future__ import annotations

import copy
import json
import pathlib
import random
import time

import numpy as np

from rule_alpha import classify as cls
from rule_alpha import layer1

from .analytic import analytic_metrics

NUMERIC_FEATURE_SKIP = {"largest_residual_rect_dims"}


class EpisodeState:
    """A replayable analytic episode: board, agent, remaining stream, pool."""

    def __init__(self, scene, arm, containers=None, queue=None, pool=None):
        self.scene = scene
        self.arm = arm
        self.config = arm.config
        self.containers = containers if containers is not None else scene.rule_alpha_containers()
        self.agent = arm(scene)
        self.agent.get_init_states({
            "optimize": scene.optimize, "lookahead_k": scene.look_ahead,
            "container_list": self.containers,
        })
        self.board = layer1.Board(self.containers, self.config)
        items = [dict(i) for i in scene.items]
        if queue is None:
            if scene.optimize:
                order = self.agent.optimize([dict(i) for i in items])
                by_index = {int(i["index"]): i for i in items}
                items = [by_index[int(i)] for i in order]
            self.queue = items
            self.pool = []
            self._refill()
        else:
            self.queue = list(queue)
            self.pool = list(pool)
        self.steps = 0

    def _refill(self):
        while len(self.pool) < self.scene.look_ahead and self.queue:
            self.pool.append(self.queue.pop(0))

    def clone(self) -> "EpisodeState":
        new = EpisodeState(
            self.scene, self.arm,
            containers=copy.deepcopy(self.board.containers),
            queue=copy.deepcopy(self.queue), pool=copy.deepcopy(self.pool),
        )
        new.steps = self.steps
        return new

    def observation(self) -> dict:
        return {
            "optimize": self.scene.optimize, "lookahead_k": self.scene.look_ahead,
            "container_list": self.board.containers,
            "pool_list": [dict(i) for i in self.pool],
        }

    def decide(self):
        """Ask the agent; returns (action, decision) or (None, None) when it declines."""
        if not self.pool:
            return None, None
        action = self.agent.policy(self.observation())
        if action is None:
            return None, None
        return action, self.agent.last_decision

    def apply_placement(self, placement, pool_index: int) -> None:
        placement.step = self.steps + 1
        self.board.apply(placement)
        self.pool.pop(pool_index)
        self._refill()
        self.steps += 1

    def apply_candidate(self, candidate, archetype: str, pool_index: int, profile) -> None:
        # the candidate was generated on the agent's board (rebuilt from the
        # same container dicts), so compaction has to run against that board
        placement = layer1.build_placement(
            candidate, archetype, self.agent.board, candidate.container_idx, profile, self.config
        )
        self.apply_placement(placement, pool_index)

    def run(self, max_steps: int, milestones=(3, 5, 10)) -> dict:
        """Greedy continuation; returns how it went, with the count at a few
        truncation points so shorter-horizon labels can be read off later."""
        placed = 0
        declined = False
        at = {}
        for step in range(max_steps):
            if not self.pool:
                break
            action, decision = self.decide()
            if action is None:
                declined = True
                break
            self.apply_placement(decision.placement, int(action["item_idx"]))
            placed += 1
            if placed in milestones:
                at[placed] = placed
        for m in milestones:
            at.setdefault(m, min(placed, m))
        return {"placed": placed, "declined": declined, "stream_empty": not self.pool,
                "placed_at": {str(m): at[m] for m in milestones}}

    def summary(self) -> dict:
        metrics = analytic_metrics(self.board, len(self.scene.items))
        reach = sum(self.board.floor_reach(i)[0] for i in range(len(self.board.models)))
        plateau = max(
            (self.board.plateau_stats(i).get("largest", 0.0) for i in range(len(self.board.models))),
            default=0.0,
        )
        return {
            "placed_count": metrics["placed_count"],
            "fill_volume": metrics["fill_volume"],
            "com_z_ratio": metrics["com_z_above_floor_ratio"],
            "priority_covered": metrics["priority_covered"],
            "soft_covered": metrics["soft_covered"],
            "reach_free": float(reach),
            "largest_hard_plateau": float(plateau),
        }


def _numeric_features(candidate) -> dict:
    out = {}
    for key, value in candidate.features.items():
        if key in NUMERIC_FEATURE_SKIP:
            continue
        if isinstance(value, (bool, np.bool_)):
            out[key] = float(value)
        elif isinstance(value, (int, float, np.integer, np.floating)):
            out[key] = float(value)
    return out


def _candidate_record(candidate, profile) -> dict:
    o = candidate.orientation
    return {
        "surface": candidate.surface, "role": candidate.role, "family": candidate.family,
        "orientation": int(o.index), "dx": float(o.dx), "dy": float(o.dy), "dz": float(o.dz),
        "tipping_ratio": float(o.tipping_ratio),
        "archetypes": sorted(candidate.archetypes),
        "center": [round(float(v), 4) for v in candidate.box.center],
        "container_idx": int(candidate.container_idx),
        "features": _numeric_features(candidate),
        "item": {
            "class": profile.cargo_class, "is_soft": bool(profile.is_soft),
            "is_prioritized": bool(profile.is_prioritized), "mass": float(profile.mass),
            "volume": float(profile.volume), "elongation": float(profile.elongation),
        },
    }


def sample_candidates(survivors, chosen, k: int, rng: random.Random) -> list:
    """The ladder's pick plus up to k-1 others, one per (surface, role) first."""
    picked = [chosen]
    others = [c for c in survivors if c is not chosen]
    rng.shuffle(others)
    groups: dict = {}
    for c in others:
        groups.setdefault((c.surface, c.role), []).append(c)
    keys = list(groups)
    rng.shuffle(keys)
    for key in keys:
        if len(picked) >= k:
            break
        picked.append(groups[key].pop(0))
    rest = [c for key in keys for c in groups[key]]
    rng.shuffle(rest)
    for c in rest:
        if len(picked) >= k:
            break
        picked.append(c)
    return picked


def rollout_scene(scene, arm, horizon: int, k: int, seed: int = 0,
                  max_decisions: int = 400, min_survivors: int = 2) -> list[dict]:
    """Follow the ladder through one episode; label sampled alternatives at each step."""
    rng = random.Random(seed)
    state = EpisodeState(scene, arm)
    records: list[dict] = []
    while state.pool and state.steps < max_decisions:
        action, decision = state.decide()
        if action is None:
            break
        pool_index = int(action["item_idx"])
        survivors = list(decision.survivors or [])
        profile = decision.placement.profile
        before = state.summary()
        if len(survivors) >= min_survivors:
            chosen = decision.chosen
            sampled = sample_candidates(survivors, chosen, k, rng)
            for cand_index, candidate in enumerate(sampled):
                t0 = time.perf_counter()
                branch = state.clone()
                # the branch's agent must see the same board the candidate
                # came from: rebuild by asking it once, then apply the candidate
                branch.agent.policy(branch.observation())
                archetype = decision.placement.archetype if candidate is chosen else (
                    sorted(candidate.archetypes)[0] if candidate.archetypes else "alternative"
                )
                branch.apply_candidate(candidate, archetype, pool_index, profile)
                run = branch.run(horizon)
                after = branch.summary()
                records.append({
                    "scene": scene.name, "step": state.steps, "cand": cand_index,
                    "is_ladder": candidate is chosen,
                    "ladder_archetype": decision.placement.archetype,
                    "n_survivors": len(survivors), "n_sampled": len(sampled),
                    "items_left": len(state.queue) + len(state.pool),
                    "candidate": _candidate_record(candidate, profile),
                    "outcome": {
                        "placed_h": 1 + run["placed"],
                        "placed_at": {m: 1 + n for m, n in run["placed_at"].items()},
                        "declined": run["declined"],
                        "stream_empty": run["stream_empty"],
                        "horizon": horizon,
                        "fill_gain": after["fill_volume"] - before["fill_volume"],
                        "com_z_ratio": after["com_z_ratio"],
                        "priority_covered_delta": after["priority_covered"] - before["priority_covered"],
                        "soft_covered_delta": after["soft_covered"] - before["soft_covered"],
                        "reach_free_after": after["reach_free"],
                        "largest_hard_plateau_after": after["largest_hard_plateau"],
                    },
                    "seconds": round(time.perf_counter() - t0, 3),
                })
        state.apply_placement(decision.placement, pool_index)
    return records


def write_jsonl(records: list[dict], path: pathlib.Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for record in records:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def read_jsonl(paths) -> list[dict]:
    out = []
    for path in paths:
        with pathlib.Path(path).open(encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    out.append(json.loads(line))
    return out
