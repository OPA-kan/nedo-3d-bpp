"""
How far would Task C get if the search never missed a safe placement?

An episode dies once, so it reveals exactly one failure reason. Everything
after that is invisible, and every fix measured so far has only moved the
death one step (anchor fallback: c001-k1 died at 18, then at 19). That leaves
the question this script answers open: is the search a step away from the real
ceiling, or many steps?

The chain: run the episode normally. Whenever it would end, hand it a
physically safe placement the exhaustive oracle found and keep going. Repeat
until the oracle itself finds nothing -- a state where no safe placement
exists under either anchor generator with unlimited time. That state is the
real ceiling, and the number of rescues before it is what the search is
costing.

Two rescue policies, because they answer different questions:

- ``search`` rescues only the no-candidate deaths (unsafe_protocol_fallback).
  The agent's own picks stand, including ones that fail physically, so the
  ceiling measured is "perfect search, current ranking".
- ``all`` also replaces a chosen action that fails physically. That removes
  bad picks as well, so what remains is only true dead ends.

Neither is a policy. Both use information no agent has -- the oracle's
physical validation of a candidate before committing to it -- so the numbers
are upper bounds, not achievable scores. Report them as ceilings.
"""
from __future__ import annotations

import argparse
import copy
import json
import pathlib
import sys
import time
from typing import Any

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
SIMULATOR = ROOT / "simulator"

from scripts.measure_anchor_recall import (  # noqa: E402
    LivePhysicsOracle,
    enrich_score,
    enumerate_dual_settled_oracle,
    enumerate_oracle_candidates,
    json_safe,
    load_agent_module,
    policy_observation,
)

RESCUE_POLICIES = ("search", "all")


def action_record(action: dict[str, Any], observation: dict[str, Any]):
    """The agent's own action in the shape the physics oracle validates."""
    pool_index = int(action["item_idx"])
    item = observation["pool_list"][pool_index]
    return {
        "pool_index": pool_index,
        "item_index": int(item.get("index", pool_index)),
        "container_index": int(action["container_idx"]),
        "orientation": int(action["orientation"]),
        "action_center": [float(value) for value in action["place_pos"]],
    }


def probe_records(
    env, records: list[dict[str, Any]], stop_when_safe: bool
) -> tuple[list[dict[str, Any]], int]:
    """
    Physically validate records in order, restoring the world each time.

    ``stop_when_safe`` returns at the first physically safe record. Callers
    that only need "is there one" pay for one settle instead of hundreds; the
    exhaustive walk happens exactly when the answer is no, which is the case
    that has to be complete anyway.
    """
    oracle = LivePhysicsOracle(env)
    base_state = env.client.saveState()
    validated: list[dict[str, Any]] = []
    checked = 0
    try:
        for record in records:
            env.client.restoreState(stateId=base_state)
            source_item = env.stream_manager.get_item(
                int(record["pool_index"])
            )
            if source_item is None:
                continue
            probe = oracle._clone_item(source_item)
            if probe.spawn(
                env.client,
                initial_pos=(0.0, 0.0, 5.0),
                initial_orn=(0.0, 0.0, 0.0, 1.0),
            ) is None:
                raise RuntimeError("failed to create physics probe item")
            try:
                physical = oracle.validate_spawned(record, probe)
            finally:
                if probe.pybullet_id is not None:
                    probe.remove(client=env.client)
            checked += 1
            enriched = dict(record)
            enriched["physical"] = physical
            validated.append(enriched)
            if stop_when_safe and physical.get("is_physically_valid"):
                break
    finally:
        env.client.restoreState(stateId=base_state)
        env.client.removeState(base_state)
    return validated, checked


def oracle_candidates(agent_module, observation) -> list[dict[str, Any]]:
    """Every candidate both generators can reach, no deadline, scored."""
    settled, settled_complete, _stats = enumerate_dual_settled_oracle(
        agent_module, observation, max_candidates=None
    )
    release, release_complete, _release_stats = enumerate_oracle_candidates(
        agent_module,
        observation,
        generator_mode="cartesian",
        attempt_kind="release",
        max_candidates=None,
    )
    if not (settled_complete and release_complete):
        raise RuntimeError(
            "oracle enumeration was truncated; a dead end cannot be "
            "declared from an incomplete set"
        )
    records = [
        enrich_score(agent_module, observation, record)
        for record in list(settled) + list(release)
    ]
    # Best first by the agent's own ranking, so the rescue removes the search
    # failure without also replacing the ranking with a better one.
    records.sort(key=lambda record: -float(record["score"]))
    for rank, record in enumerate(records):
        record["oracle_rank"] = rank
    return records


def rescue_action(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "item_idx": int(record["pool_index"]),
        "container_idx": int(record["container_index"]),
        "place_pos": np.asarray(record["action_center"], dtype=np.float32),
        "orientation": int(record["orientation"]),
    }


def run_chain(
    agent_module,
    task_config: dict[str, Any],
    *,
    case_id: str,
    rescue_policy: str,
    max_rescues: int,
) -> dict[str, Any]:
    if str(SIMULATOR) not in sys.path:
        sys.path.insert(0, str(SIMULATOR))
    from src.ground_handling.env import GroundHandlingEnv

    env = GroundHandlingEnv(config=task_config, verbose=False, render_mode=None)
    solver = agent_module.Agent("")
    chain: list[dict[str, Any]] = []
    outcome = "episode_completed"
    placed = 0
    rescues = 0
    started = time.perf_counter()
    try:
        env.reset_settings()
        solver.get_init_states(env.get_init_states())
        env.reset_item_stream()
        raw_observation, _info = env.reset(seed=42)
        terminated = truncated = False
        step = 0
        while not terminated and not truncated:
            observation = policy_observation(env, raw_observation)
            action = solver.policy(observation)
            source = solver.last_action_source
            entry = {"step": step, "action_source": source}

            needs_oracle = source == "unsafe_protocol_fallback"
            if not needs_oracle:
                probed, _checked = probe_records(
                    env, [action_record(action, observation)], True
                )
                own_ok = bool(
                    probed and probed[0]["physical"]["is_physically_valid"]
                )
                entry["own_action_physically_safe"] = own_ok
                if not own_ok:
                    entry["reason"] = "chosen_action_fails_physics"
                    needs_oracle = rescue_policy == "all"
                    if not needs_oracle:
                        entry["chain_ends"] = True
            else:
                entry["reason"] = "search_returned_no_candidate"

            if needs_oracle:
                if rescues >= max_rescues:
                    entry["chain_ends"] = True
                    entry["reason"] = "rescue_budget_exhausted"
                    outcome = "rescue_budget_exhausted"
                    chain.append(entry)
                    break
                oracle_started = time.perf_counter()
                records = oracle_candidates(agent_module, observation)
                validated, checked = probe_records(env, records, True)
                safe = [
                    record
                    for record in validated
                    if record["physical"]["is_physically_valid"]
                ]
                entry["oracle_candidates"] = len(records)
                entry["oracle_physically_checked"] = checked
                entry["oracle_seconds"] = round(
                    time.perf_counter() - oracle_started, 2
                )
                if not safe:
                    entry["reason"] = "true_dead_end"
                    entry["chain_ends"] = True
                    outcome = "true_dead_end"
                    chain.append(entry)
                    break
                best = safe[0]
                entry["rescued_with"] = {
                    "kind": best.get("kind"),
                    "orientation": int(best["orientation"]),
                    "score": float(best["score"]),
                    "rank_among_oracle": int(best["oracle_rank"]),
                }
                action = rescue_action(best)
                rescues += 1
                entry["rescued"] = True

            chain.append(entry)
            raw_observation, _reward, terminated, truncated, info = env.step(
                action
            )
            status = (info or {}).get("status", {})
            entry["executed_status"] = dict(status)
            if all(
                bool(status.get(flag))
                for flag in ("is_included", "is_valid", "is_placed_safe")
            ):
                placed += 1
            elif not entry.get("chain_ends"):
                # A rescue that the oracle validated must survive execution;
                # if it does not, the oracle and the executor disagree and the
                # ceiling is unmeasurable rather than merely lower.
                entry["oracle_execution_disagreement"] = bool(
                    entry.get("rescued")
                )
                entry["chain_ends"] = True
                outcome = (
                    "oracle_execution_disagreement"
                    if entry.get("rescued")
                    else "executed_action_failed"
                )
            step += 1
    finally:
        try:
            env.close()
        except Exception:
            pass
    reasons: dict[str, int] = {}
    for entry in chain:
        reason = entry.get("reason")
        if reason:
            reasons[reason] = reasons.get(reason, 0) + 1
    return {
        "case_id": case_id,
        "rescue_policy": rescue_policy,
        "outcome": outcome,
        "steps": len(chain),
        "placed": placed,
        "rescues": rescues,
        "reason_counts": reasons,
        "seconds": round(time.perf_counter() - started, 1),
        "chain": chain,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=pathlib.Path, required=True)
    parser.add_argument("--case", required=True)
    parser.add_argument(
        "--rescue", choices=RESCUE_POLICIES, default="search"
    )
    parser.add_argument("--max-rescues", type=int, default=25)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()

    config = json.loads(args.config.read_text(encoding="utf-8"))
    if args.case not in config:
        raise SystemExit(f"unknown case {args.case!r}: {', '.join(config)}")
    agent_module = load_agent_module()
    result = run_chain(
        agent_module,
        copy.deepcopy(config[args.case]),
        case_id=args.case,
        rescue_policy=args.rescue,
        max_rescues=args.max_rescues,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(json_safe(result), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(
        f"{result['case_id']} [{result['rescue_policy']}] "
        f"placed={result['placed']} rescues={result['rescues']} "
        f"outcome={result['outcome']} {result['seconds']}s"
    )
    print(json.dumps(result["reason_counts"], ensure_ascii=False))
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
