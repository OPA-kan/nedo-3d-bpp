"""Boards with their remaining return, for a value network.

Replays the ladder's episode on each rollout scene and turns every state
into a training example: the board tensor before the decision, and the
number of items the fixed policy still places from there (the Monte-Carlo
return under pi_0, exact because the model is deterministic).  Every
alternative the rollout labelled becomes another example: the board after
that alternative, with the return the rollout measured for it.  That is
ten to twenty times more supervision per scene than the per-candidate
labels alone, from the same rollouts.

v1 uses single-container scenes only, so the return of a container tensor
is the return of the episode.
"""

from __future__ import annotations

import json
import pathlib
import time

import numpy as np

from rule_alpha import layer1

from .rollouts import EpisodeState, read_jsonl
from .tensor import board_tensor, summary_vector


def _match(survivors, record):
    cand = record["candidate"]
    centre = np.asarray(cand["center"], dtype=np.float64)
    for c in survivors:
        if int(c.orientation.index) != int(cand["orientation"]):
            continue
        if int(c.container_idx) != int(cand["container_idx"]):
            continue
        if np.max(np.abs(np.asarray(c.box.center) - centre)) < 2e-3:
            return c
    return None


def build_scene(scene, arm, records: list[dict]) -> dict:
    """Tensors and targets for one scene; returns arrays ready for np.savez."""
    config = arm.config
    by_step: dict = {}
    for r in records:
        by_step.setdefault(int(r["step"]), []).append(r)

    state = EpisodeState(scene, arm)
    boards, targets, aux, kinds, steps = [], [], [], [], []
    trajectory = []   # (step, tensor, summary) of the main line, targets filled at the end
    branch_seconds = 0.0
    while state.pool:
        action, decision = state.decide()
        if action is None:
            break
        step = state.steps
        X, summary = board_tensor(state.board, 0, config)
        trajectory.append((step, X, summary))
        pool_index = int(action["item_idx"])
        profile = decision.placement.profile
        survivors = list(decision.survivors or [])
        for r in by_step.get(step, []):
            # the ladder's own pick is kept as a branch too (kind 2), so the
            # held-out ranking check can compare the model's pick with it
            t0 = time.perf_counter()
            candidate = _match(survivors, r)
            if candidate is None:
                continue
            # compaction runs against the board the candidate was generated
            # on (the agent's, unchanged), so there is no need to rebuild it
            archetype = sorted(candidate.archetypes)[0] if candidate.archetypes else "alternative"
            placement = layer1.build_placement(
                candidate, archetype, state.agent.board, candidate.container_idx, profile, config
            )
            branch = state.clone()
            branch.apply_placement(placement, pool_index)
            Xb, sb = board_tensor(branch.board, 0, config)
            boards.append(Xb); targets.append(float(r["outcome"]["placed_h"]) - 1.0)
            aux.append(summary_vector(sb)); kinds.append(2 if r["is_ladder"] else 1); steps.append(step)
            branch_seconds += time.perf_counter() - t0
        state.apply_placement(decision.placement, pool_index)
    total = state.steps
    for step, X, summary in trajectory:
        boards.append(X); targets.append(float(total - step))
        aux.append(summary_vector(summary)); kinds.append(0); steps.append(step)
    return {
        "X": np.stack(boards).astype(np.float16) if boards else np.zeros((0, 16, 1, 1), np.float16),
        "y": np.asarray(targets, dtype=np.float32),
        "aux": np.stack(aux).astype(np.float32) if aux else np.zeros((0, 9), np.float32),
        "kind": np.asarray(kinds, dtype=np.int8),
        "step": np.asarray(steps, dtype=np.int16),
        "scene": np.array(scene.name),
        "total_placed": np.array(total),
        "branch_seconds": np.array(branch_seconds),
    }


def build_from_rollouts(rollout_dir: pathlib.Path, out_dir: pathlib.Path, arm, scenes_by_name: dict,
                        only_single_container: bool = True, resume: bool = True, log=print) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    done = 0
    for path in sorted(pathlib.Path(rollout_dir).glob("*.jsonl")):
        name = path.stem
        scene = scenes_by_name.get(name)
        if scene is None:
            continue
        if only_single_container and len(scene.containers) != 1:
            continue
        target = out_dir / f"{name}.npz"
        if resume and target.exists():
            done += 1
            continue
        started = time.perf_counter()
        data = build_scene(scene, arm, read_jsonl([path]))
        np.savez_compressed(target, **data)
        done += 1
        log(f"[{name}] {len(data['y'])} boards ({int((data['kind'] >= 1).sum())} branches) "
            f"in {time.perf_counter() - started:.0f}s")
    return done


def load_boards(paths):
    Xs, ys, auxs, kinds, names = [], [], [], [], []
    for p in paths:
        d = np.load(p)
        if len(d["y"]) == 0:
            continue
        Xs.append(d["X"].astype(np.float32)); ys.append(d["y"]); auxs.append(d["aux"])
        kinds.append(d["kind"]); names.extend([str(d["scene"])] * len(d["y"]))
    return (np.concatenate(Xs), np.concatenate(ys), np.concatenate(auxs),
            np.concatenate(kinds), np.asarray(names))
