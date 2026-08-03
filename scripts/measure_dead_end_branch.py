"""
Replay the last choice before a true dead end and ask which board feature
separates the actions that survive it from the ones that do not.

The search ceiling measurement showed Task C dies against a real wall: at the
terminal state the oracle enumerates the whole anchor space of both generators
and finds ZERO candidates -- and finds them zero *before* physics, so the dead
end is static. That matters here, because it means a static expansion of the
branch is exact for this question rather than a proxy, and the whole analysis
costs enumeration instead of settles.

The design is pairwise within one state, which is the form that survived in
this repository when AUC did not (mechanics-features used within-snapshot
discordant-pair accuracy). At the step before the wall, every physically safe
action is a legitimate choice the agent could have made. Some of them leave a
board the next item can use and some do not. Same state, same item, both safe
now: the only difference is what they did to the future.

Two labels come out of it, and they answer different questions:

- ``kills_stream``: the actual next arrival has no candidate after this
  action. Correct for this configuration's arrival order and only that one.
- ``extinct_classes``: how many of the seven published baggage types have no
  candidate after this action. Independent of arrival order, which is what a
  board value is supposed to be about.

No policy is computed and nothing is ranked. This selects a feature to test.
"""
from __future__ import annotations

import argparse
import collections
import copy
import hashlib
import json
import pathlib
import sys
import time
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
SIMULATOR = ROOT / "simulator"

from scripts.measure_anchor_recall import (  # noqa: E402
    enrich_score,
    enumerate_dual_settled_oracle,
    enumerate_oracle_candidates,
    json_safe,
    load_agent_module,
    policy_observation,
)
from scripts.measure_board_value import BAGGAGE_TYPES, type_representative  # noqa: E402
from scripts.measure_search_ceiling import (  # noqa: E402
    oracle_candidates,
    probe_records,
    rescue_action,
)

# Slot geometry. A slot is what an independent alternative actually is: two
# placements a few millimetres apart are one escape route, not two. The cell
# is coarse on purpose -- the point is to stop counting grid resolution.
SLOT_XY_CELL = 0.25
SLOT_Z_BAND = 0.10


def slot_of(record: dict[str, Any]) -> tuple[int, int, int, int]:
    centre = record["center"]
    size = record["size"]
    bottom = float(centre[2]) - float(size[2]) / 2.0
    return (
        int(record["container_index"]),
        int(round(float(centre[0]) / SLOT_XY_CELL)),
        int(round(float(centre[1]) / SLOT_XY_CELL)),
        int(round(bottom / SLOT_Z_BAND)),
    )


def enumerate_for_item(
    agent_module, containers, item, pool_index=0
) -> tuple[list[dict[str, Any]], bool]:
    """Every candidate both generators can reach for one item, no deadline."""
    observation = {"pool_list": [item], "container_list": containers}
    indexed = [(pool_index, item)]
    settled, settled_ok, _stats = enumerate_dual_settled_oracle(
        agent_module, observation, indexed_items=indexed
    )
    release, release_ok, _release_stats = enumerate_oracle_candidates(
        agent_module,
        observation,
        generator_mode="cartesian",
        attempt_kind="release",
        indexed_items=indexed,
    )
    return list(settled) + list(release), bool(settled_ok and release_ok)


def board_after(agent_module, containers, item, action_record):
    """T_a(s): the container state this action would leave behind."""
    simulated = copy.deepcopy(containers)
    decision = agent_module.PlacementDecision(
        action={
            "item_idx": 0,
            "container_idx": int(action_record["container_index"]),
            "place_pos": list(action_record["action_center"]),
            "orientation": int(action_record["orientation"]),
        },
        candidate=agent_module.AABB(
            tuple(float(v) for v in action_record["center"]),
            tuple(float(v) for v in action_record["size"]),
            str(action_record.get("kind", "candidate")),
        ),
        score=float(action_record.get("score", 0.0)),
    )
    agent_module.apply_placement_decision(item, decision, simulated)
    return simulated


def board_features(
    agent_module, containers, next_item
) -> dict[str, Any]:
    """
    Per-class survival on the board a candidate would leave.

    Class weights are the published type prior. A Task C agent never learns
    the remaining multiset, so weighting by what is actually left would be an
    information leak (see docs/theory/TASK_C_BOARD_VALUE.md section 1).
    """
    per_class = []
    slots_by_class: dict[str, set] = {}
    for index, entry in enumerate(BAGGAGE_TYPES):
        representative = type_representative(entry, index)
        records, complete = enumerate_for_item(
            agent_module, containers, representative
        )
        slots = {slot_of(record) for record in records}
        slots_by_class[entry["name"]] = slots
        per_class.append(
            {
                "class": entry["name"],
                "candidates": len(records),
                "slots": len(slots),
                "complete": complete,
                "extinct": not records,
            }
        )

    # Concentration: spread each class's arrival weight evenly over the slots
    # it can still use, then find the slot the most future demand lands on.
    load: dict[tuple, float] = collections.defaultdict(float)
    weight = 1.0 / len(BAGGAGE_TYPES)
    for slots in slots_by_class.values():
        if not slots:
            continue
        share = weight / len(slots)
        for slot in slots:
            load[slot] += share
    union = set().union(*slots_by_class.values()) if slots_by_class else set()

    stream_records, stream_complete = enumerate_for_item(
        agent_module, containers, next_item
    )
    return {
        "per_class": per_class,
        "extinct_classes": sum(1 for row in per_class if row["extinct"]),
        "min_class_slots": min(row["slots"] for row in per_class),
        "total_slots": len(union),
        "mean_class_slots": sum(row["slots"] for row in per_class)
        / len(per_class),
        "concentration_max": max(load.values()) if load else 1.0,
        "next_item_candidates": len(stream_records),
        "next_item_slots": len({slot_of(r) for r in stream_records}),
        "kills_stream": not stream_records,
        "enumeration_complete": bool(
            stream_complete and all(row["complete"] for row in per_class)
        ),
    }


def replay_digest(observation) -> str:
    """
    Fingerprint of the replayed board, so replay-to-replay physics
    divergence is measurable instead of silently absorbed into branch
    labels. Millimetre rounding: settle noise below that is not what the
    horizon labels are trying to detect.
    """
    rows = []
    for container in observation.get("container_list", []):
        for packed in container.get("packed_items", []):
            pos = None
            for key in ("pos", "place_pos", "position", "center"):
                if packed.get(key) is not None:
                    pos = packed[key]
                    break
            rows.append(
                (
                    int(packed.get("index", -1)),
                    tuple(
                        round(float(v), 3) for v in (pos or (0.0, 0.0, 0.0))
                    ),
                )
            )
    rows.sort()
    payload = json.dumps(rows, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()[:16]


def continue_with_oracle_best(
    agent_module, env, raw_observation, step, horizon
) -> dict[str, Any]:
    """
    Play on from here with the oracle's best safe candidate each step.

    The one-step label is not enough to find the last recoverable action. At
    c001-k1 step 18 the next item is placeable under every choice, yet the
    wall still arrives at step 20 -- a one-step lookahead cannot see it. This
    plays forward under ideal search and ideal picks, so the only thing that
    can stop it is the wall itself.
    """
    placed = 0
    reached = step
    outcome = "horizon_reached"
    while reached < step + horizon:
        observation = policy_observation(env, raw_observation)
        records = oracle_candidates(agent_module, observation)
        validated, _checked = probe_records(env, records, 1)
        safe = [
            record
            for record in validated
            if record["physical"]["is_physically_valid"]
        ]
        if not safe:
            outcome = "true_dead_end"
            break
        raw_observation, _r, terminated, truncated, info = env.step(
            rescue_action(safe[0])
        )
        status = (info or {}).get("status", {})
        if all(
            bool(status.get(flag))
            for flag in ("is_included", "is_valid", "is_placed_safe")
        ):
            placed += 1
        else:
            outcome = "oracle_execution_disagreement"
            break
        reached += 1
        if terminated or truncated:
            outcome = "episode_ended"
            break
    return {
        "continued_placed": placed,
        "reached_step": reached,
        "continuation_outcome": outcome,
    }


def replay_to_step(agent_module, task_config, target_step, actions=None):
    """
    Replay to the state before ``target_step``.

    Without ``actions`` this re-RUNS the live policy, and the live policy is
    deadline-driven, so two replays of the same case under different CPU
    conditions can pick different placements and land on different boards
    (measured: two distinct millimetre-digest basins within one serial
    process). Callers that compare branches from "the same state" must
    therefore capture the action sequence from one reference replay
    (returned as the last element) and pass it back via ``actions`` for
    every subsequent replay, which replays the captured actions verbatim
    and never consults the policy.
    """
    if str(SIMULATOR) not in sys.path:
        sys.path.insert(0, str(SIMULATOR))
    from src.ground_handling.env import GroundHandlingEnv

    env = GroundHandlingEnv(config=task_config, verbose=False, render_mode=None)
    solver = agent_module.Agent("")
    env.reset_settings()
    solver.get_init_states(env.get_init_states())
    env.reset_item_stream()
    raw_observation, _info = env.reset(seed=42)
    step = 0
    rescues = []
    executed_actions = []
    while step < target_step:
        if actions is not None:
            action = copy.deepcopy(actions[step])
            executed_actions.append(action)
            raw_observation, _r, terminated, truncated, _info = env.step(
                action
            )
            if terminated or truncated:
                raise RuntimeError(
                    f"episode ended at step {step} before the target "
                    f"{target_step}"
                )
            step += 1
            continue
        observation = policy_observation(env, raw_observation)
        action = solver.policy(observation)
        if solver.last_action_source == "unsafe_protocol_fallback":
            # The branch point only exists on the rescued trajectory: the
            # shipped agent dies before reaching it. Rescue exactly the way
            # measure_search_ceiling does -- oracle candidate, ranked by the
            # agent's own score, first physically safe one -- so the replay
            # reproduces the chain that found the dead end rather than some
            # other path to a similar state.
            records = oracle_candidates(agent_module, observation)
            validated, _checked = probe_records(env, records, 1)
            safe = [
                record
                for record in validated
                if record["physical"]["is_physically_valid"]
            ]
            if not safe:
                raise RuntimeError(
                    f"step {step} is already a dead end; the branch point "
                    f"{target_step} is unreachable"
                )
            action = rescue_action(safe[0])
            rescues.append(
                {"step": step, "rank": int(safe[0]["oracle_rank"])}
            )
        executed_actions.append(copy.deepcopy(action))
        raw_observation, _r, terminated, truncated, _info = env.step(action)
        if terminated or truncated:
            raise RuntimeError(
                f"episode ended at step {step} before the target {target_step}"
            )
        step += 1
    return (
        env,
        solver,
        policy_observation(env, raw_observation),
        rescues,
        executed_actions,
    )


def continue_with_policy(
    agent_module, solver, env, raw_observation, step, horizon
) -> dict[str, Any]:
    """
    Play on with the live policy instead of the oracle.

    Two reasons to prefer this for ceiling questions. It measures the label
    that improvement work actually targets -- what the agent achieves from
    this board -- rather than what an unlimited enumeration achieves. And it
    is an order of magnitude cheaper per step, which is what makes branching
    early in the episode affordable. Run it under POLICY_ATTEMPT_BUDGET so
    the search is work-bounded instead of deadline-bounded; a deadline
    policy's trajectory depends on CPU load, which is the exact
    contamination replay pinning removed.

    The poison fixed-coordinate fallback is NOT executed: reaching it is the
    death being measured, so it ends the continuation as
    ``policy_no_safe_action``.
    """
    placed = 0
    reached = step
    outcome = "horizon_reached"
    while reached < step + horizon:
        observation = policy_observation(env, raw_observation)
        action = solver.policy(observation)
        if solver.last_action_source == "unsafe_protocol_fallback":
            outcome = "policy_no_safe_action"
            break
        raw_observation, _r, terminated, truncated, info = env.step(action)
        status = (info or {}).get("status", {})
        if all(
            bool(status.get(flag))
            for flag in ("is_included", "is_valid", "is_placed_safe")
        ):
            placed += 1
        else:
            outcome = "policy_placement_failed"
            break
        reached += 1
        if terminated or truncated:
            outcome = "episode_ended"
            break
    return {
        "continued_placed": placed,
        "reached_step": reached,
        "continuation_outcome": outcome,
    }


def select_diverse(pinned, top_k):
    """
    Greedy farthest-point subset over placement centres.

    A score-ordered top-K is often one spatial cluster, which answers "does
    the ranker's preferred micro-variation matter" when the ceiling question
    needs "does ANY materially different choice matter". Keep the best-scored
    candidate as the seed, then repeatedly add the candidate farthest from
    the already-chosen set.
    """
    if len(pinned) <= top_k:
        return pinned
    chosen = [pinned[0]]
    rest = list(pinned[1:])
    while len(chosen) < top_k and rest:
        def distance(record):
            return min(
                sum(
                    (float(a) - float(b)) ** 2
                    for a, b in zip(record["center"], other["center"])
                )
                for other in chosen
            )
        best = max(rest, key=distance)
        rest.remove(best)
        chosen.append(best)
    return chosen


# Monte-Carlo rollout value: the board value the theory asks for, measured
# directly instead of through engineered features. Sample future arrival
# streams from the published 7-type prior (the exact information a Task C
# agent has), play each forward with a cheap geometric first-accept policy,
# and count placements until the arrived item has no accepted pose. No
# weights, no feature engineering; the number IS the quantity of interest.
MC_STREAMS = 24
MC_LATTICE = 0.10
MC_MAX_ROLLOUT = 40


def first_accepted_pose(agent_module, container, item, rng):
    """Cheapest competent placement: floor-up lattice scan, first accept."""
    components = agent_module.support_plane_components(
        agent_module.support_surfaces(container)
    )
    levels = sorted({round(float(c.top), 6) for c in components})
    length = float(container["length"])
    width = float(container["width"])
    orientations = list(agent_module.unique_orientations(item))
    rng.shuffle(orientations)
    offset_x = rng.uniform(0.0, MC_LATTICE)
    offset_y = rng.uniform(0.0, MC_LATTICE)
    xs, ys = [], []
    x = -length / 2.0 + offset_x
    while x < length / 2.0:
        xs.append(x)
        x += MC_LATTICE
    y = -width / 2.0 + offset_y
    while y < width / 2.0:
        ys.append(y)
        y += MC_LATTICE
    for level in levels:
        for orientation in orientations:
            dx, dy, dz = agent_module.get_rotated_dimensions(
                item["length"], item["width"], item["height"], orientation
            )
            for cx in xs:
                for cy in ys:
                    candidate = agent_module.AABB(
                        center=(cx, cy, level + dz / 2.0),
                        size=(dx, dy, dz),
                        name="mc_rollout",
                    )
                    if (
                        agent_module.Geometry.rejection_reason(
                            candidate, container
                        )
                        is None
                    ):
                        return orientation, candidate
    return None


def mc_rollout_value(
    agent_module, containers, *, streams=MC_STREAMS, seed=0
) -> dict[str, Any]:
    import random

    values = []
    for stream_index in range(streams):
        rng = random.Random(f"{seed}-{stream_index}")
        simulated = copy.deepcopy(containers)
        container = simulated[0]
        placed = 0
        while placed < MC_MAX_ROLLOUT:
            type_index = rng.randrange(len(BAGGAGE_TYPES))
            item = type_representative(BAGGAGE_TYPES[type_index], type_index)
            pose = first_accepted_pose(agent_module, container, item, rng)
            if pose is None:
                break
            orientation, candidate = pose
            decision = agent_module.PlacementDecision(
                action={
                    "item_idx": 0,
                    "container_idx": 0,
                    "place_pos": list(
                        agent_module.simulator_action_center(
                            candidate, container
                        )
                    ),
                    "orientation": int(orientation),
                },
                candidate=candidate,
                score=0.0,
            )
            agent_module.apply_placement_decision(item, decision, simulated)
            placed += 1
        values.append(placed)
    mean = sum(values) / len(values)
    return {
        "mc_streams": streams,
        "mc_value_mean": mean,
        "mc_value_min": min(values),
        "mc_value_max": max(values),
        "mc_values": values,
    }


def run_horizon(
    agent_module,
    task_config,
    *,
    case_id,
    branch_step,
    top_k,
    horizon,
    started,
    continue_with="oracle",
    pin_mode="top",
    mc_shadow=False,
) -> dict[str, Any]:
    """
    Backward search for the last recoverable action.

    Each candidate needs its own replay, because an executed step cannot be
    undone, so this is expensive by construction: K replays to the branch
    point plus K continuations. Reported so the cost of going one step further
    back is visible rather than discovered.
    """
    # Pin the top-K candidates ONCE, from a reference replay. The first
    # version re-derived the list inside every per-rank replay; physics
    # divergence across replays reshuffles enumeration scores and probe
    # outcomes, so "rank r" named a different placement in every replay and
    # the branch labels conflated choice with replay noise (the recorded
    # scores were non-monotone across ranks, which a stable sorted list
    # cannot produce). Executing pinned coordinates keeps the action
    # constant; the residual replay-to-replay state noise is made visible
    # via replay_digest instead of being silently absorbed.
    env, _solver, observation, _rescues, reference_actions = replay_to_step(
        agent_module, task_config, branch_step
    )
    try:
        reference_digest = replay_digest(observation)
        records = oracle_candidates(agent_module, observation)
        probe_target = top_k * 4 if pin_mode == "diverse" else top_k
        validated, _checked = probe_records(env, records, probe_target)
        safe_pool = [
            r
            for r in validated
            if r["physical"]["is_physically_valid"]
        ][:probe_target]
        if pin_mode == "diverse":
            pinned = select_diverse(safe_pool, top_k)
        else:
            pinned = safe_pool[:top_k]
    finally:
        try:
            env.close()
        except Exception:
            pass

    branches = []
    safe_count = len(pinned)
    for rank, candidate in enumerate(pinned):
        env, solver, observation, _rescues, _actions = replay_to_step(
            agent_module, task_config, branch_step, actions=reference_actions
        )
        try:
            raw_observation, _r, terminated, truncated, info = env.step(
                rescue_action(candidate)
            )
            status = (info or {}).get("status", {})
            executed = all(
                bool(status.get(flag))
                for flag in ("is_included", "is_valid", "is_placed_safe")
            )
            entry = {
                "rank_by_score": rank,
                "score": float(candidate["score"]),
                "kind": candidate.get("kind"),
                "orientation": int(candidate["orientation"]),
                "center": [float(v) for v in candidate["center"]],
                "size": [float(v) for v in candidate["size"]],
                "replay_digest": replay_digest(observation),
                "replay_matches_reference": (
                    replay_digest(observation) == reference_digest
                ),
                "executed_ok": executed,
            }
            if mc_shadow and executed:
                post = policy_observation(env, raw_observation)
                entry.update(
                    mc_rollout_value(
                        agent_module,
                        copy.deepcopy(post["container_list"]),
                        seed=rank,
                    )
                )
            if executed and not (terminated or truncated):
                if continue_with == "policy":
                    entry.update(
                        continue_with_policy(
                            agent_module,
                            solver,
                            env,
                            raw_observation,
                            branch_step + 1,
                            horizon,
                        )
                    )
                else:
                    entry.update(
                        continue_with_oracle_best(
                            agent_module,
                            env,
                            raw_observation,
                            branch_step + 1,
                            horizon,
                        )
                    )
            else:
                entry.update(
                    {
                        "continued_placed": 0,
                        "reached_step": branch_step + 1,
                        "continuation_outcome": (
                            "executed_ok"
                            if executed
                            else "execution_failed"
                        ),
                    }
                )
            entry["total_placed_from_branch"] = (
                int(executed) + int(entry["continued_placed"])
            )
            branches.append(entry)
            print(
                f"  rank {rank}: reached step {entry['reached_step']} "
                f"(+{entry['total_placed_from_branch']} placed) "
                f"{entry['continuation_outcome']}",
                flush=True,
            )
        finally:
            try:
                env.close()
            except Exception:
                pass
    reach = {b["total_placed_from_branch"] for b in branches}
    return {
        "case_id": case_id,
        "branch_step": branch_step,
        "mode": "horizon",
        "horizon": horizon,
        "physically_safe_expanded": len(branches),
        "physically_safe_total": safe_count,
        "reference_digest": reference_digest,
        "continue_with": continue_with,
        "pin_mode": pin_mode,
        "policy_attempt_budget": int(agent_module.POLICY_ATTEMPT_BUDGET),
        "distinct_outcomes": len(reach),
        "choice_matters": len(reach) > 1,
        "seconds": round(time.perf_counter() - started, 1),
        "branches": branches,
    }


def run(
    agent_module,
    task_config: dict[str, Any],
    *,
    case_id: str,
    branch_step: int,
    top_k: int,
    horizon: int = 0,
    continue_with: str = "oracle",
    pin_mode: str = "top",
    mc_shadow: bool = False,
) -> dict[str, Any]:
    started = time.perf_counter()
    item_list = task_config["item_stream"]["item_list"]
    if branch_step + 1 >= len(item_list):
        raise SystemExit("branch step has no successor item in the stream")
    next_item = item_list[branch_step + 1]

    if horizon > 0:
        return run_horizon(
            agent_module,
            task_config,
            case_id=case_id,
            branch_step=branch_step,
            top_k=top_k,
            horizon=horizon,
            started=started,
            continue_with=continue_with,
            pin_mode=pin_mode,
            mc_shadow=mc_shadow,
        )
    env, _solver, observation, replay_rescues, _actions = replay_to_step(
        agent_module, task_config, branch_step
    )
    try:
        item = observation["pool_list"][0]
        records, complete = enumerate_for_item(
            agent_module, observation["container_list"], item
        )
        if not complete:
            raise RuntimeError("branch enumeration was truncated")
        records = [
            enrich_score(agent_module, observation, record)
            for record in records
        ]
        records.sort(key=lambda record: -float(record["score"]))
        validated, _checked = probe_records(env, records, top_k)
        safe = [
            record
            for record in validated
            if record["physical"]["is_physically_valid"]
        ]
        print(
            f"{case_id} step {branch_step}: {len(records)} candidates, "
            f"{len(safe)} physically safe",
            flush=True,
        )
        branches = []
        for rank, candidate in enumerate(safe[:top_k]):
            branch_started = time.perf_counter()
            simulated = board_after(
                agent_module, observation["container_list"], item, candidate
            )
            features = board_features(agent_module, simulated, next_item)
            features.update(
                {
                    "rank_by_score": rank,
                    "score": float(candidate["score"]),
                    "kind": candidate.get("kind"),
                    "orientation": int(candidate["orientation"]),
                    "seconds": round(time.perf_counter() - branch_started, 1),
                }
            )
            branches.append(features)
            print(
                f"  rank {rank}: kills_stream={features['kills_stream']} "
                f"extinct={features['extinct_classes']} "
                f"min_slots={features['min_class_slots']} "
                f"conc={features['concentration_max']:.3f} "
                f"({features['seconds']}s)",
                flush=True,
            )
    finally:
        try:
            env.close()
        except Exception:
            pass
    return {
        "case_id": case_id,
        "branch_step": branch_step,
        "next_item_index": int(next_item["index"]),
        "replay_rescues": replay_rescues,
        "replay_rescues": replay_rescues,
        "candidates": len(records),
        "physically_safe": len(safe),
        "expanded": len(branches),
        "seconds": round(time.perf_counter() - started, 1),
        "branches": branches,
    }


FEATURES = (
    "extinct_classes",
    "min_class_slots",
    "mean_class_slots",
    "total_slots",
    "concentration_max",
    "next_item_slots",
    "rank_by_score",
    "score",
)
# Lower is better for these; the rest are higher-is-better.
LOWER_IS_BETTER = frozenset(
    {"extinct_classes", "concentration_max", "rank_by_score"}
)


def pairwise(branches: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Within-state discordant-pair accuracy: over every (survivor, killer)
    pair, how often does the feature order them correctly?
    """
    survivors = [b for b in branches if not b["kills_stream"]]
    killers = [b for b in branches if b["kills_stream"]]
    report: dict[str, Any] = {
        "survivors": len(survivors),
        "killers": len(killers),
        "pairs": len(survivors) * len(killers),
        "features": {},
    }
    for feature in FEATURES:
        correct = ties = 0
        for good in survivors:
            for bad in killers:
                a, b = float(good[feature]), float(bad[feature])
                if a == b:
                    ties += 1
                elif (a < b) == (feature in LOWER_IS_BETTER):
                    correct += 1
        pairs = report["pairs"]
        report["features"][feature] = {
            "correct": correct,
            "ties": ties,
            "accuracy": (correct + 0.5 * ties) / pairs if pairs else None,
        }
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=pathlib.Path, required=True)
    parser.add_argument("--case", required=True)
    parser.add_argument("--branch-step", type=int, required=True)
    parser.add_argument("--top-k", type=int, default=8)
    parser.add_argument(
        "--horizon",
        type=int,
        default=0,
        help=(
            "Play on with oracle-best picks for this many steps after "
            "the branch, instead of scoring the board statically. Use "
            "this to find the last step where the CHOICE still changes "
            "the outcome; the static mode assumes you already know it."
        ),
    )
    parser.add_argument(
        "--continue-with",
        choices=["oracle", "policy"],
        default="oracle",
        help=(
            "horizon continuation: 'oracle' plays the enumerated best safe"
            " candidate each step; 'policy' plays the live agent (run under"
            " POLICY_ATTEMPT_BUDGET so the search is work-bounded, not"
            " deadline-bounded)"
        ),
    )
    parser.add_argument(
        "--pin-mode",
        choices=["top", "diverse"],
        default="top",
        help=(
            "'top' pins the K best-scored safe candidates; 'diverse' probes"
            " 4K and picks a farthest-point spatial subset, for ceiling"
            " questions where micro-variations of one cluster are not the"
            " point"
        ),
    )
    parser.add_argument(
        "--mc-shadow",
        action="store_true",
        help=(
            "compute the Monte-Carlo rollout value of each branch's"
            " post-placement board (prior-sampled streams, geometric"
            " first-accept rollout) alongside the horizon label, so the"
            " rollout value can be validated against measured outcomes"
            " before it is ever allowed to rank anything"
        ),
    )
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()

    config = json.loads(args.config.read_text(encoding="utf-8"))
    if args.case not in config:
        raise SystemExit(f"unknown case {args.case!r}: {', '.join(config)}")
    agent_module = load_agent_module()
    result = run(
        agent_module,
        copy.deepcopy(config[args.case]),
        case_id=args.case,
        branch_step=args.branch_step,
        top_k=args.top_k,
        horizon=args.horizon,
        continue_with=args.continue_with,
        pin_mode=args.pin_mode,
        mc_shadow=args.mc_shadow,
    )
    if result.get("mode") != "horizon":
        result["pairwise"] = pairwise(result["branches"])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(json_safe(result), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if result.get("mode") == "horizon":
        args.output.write_text(
            json.dumps(json_safe(result), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(
            f"branch step {result['branch_step']}: "
            f"choice_matters={result['choice_matters']} "
            f"distinct={result['distinct_outcomes']}"
        )
        print(args.output)
        return 0
    report = result["pairwise"]
    print(
        f"survivors={report['survivors']} killers={report['killers']} "
        f"pairs={report['pairs']}"
    )
    for feature, stats in report["features"].items():
        accuracy = stats["accuracy"]
        print(
            f"  {feature:22s} "
            f"{'n/a' if accuracy is None else f'{accuracy:.3f}'}"
        )
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
