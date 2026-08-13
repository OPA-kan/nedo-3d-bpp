"""Measure visible items with any physically safe one-step placement."""

from __future__ import annotations

import argparse
import copy
import json
import pathlib
import sys
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_counterfactual_graph import (  # noqa: E402
    build_candidate_provider,
    git_commit,
    scenario_axes,
)
from scripts.counterfactual_graph import (  # noqa: E402
    board_difference,
    board_fingerprint,
    canonical_action,
    replay_action_prefix,
)
from scripts.measure_anchor_recall import (  # noqa: E402
    DEFAULT_CONFIG,
    SIMULATOR,
    load_agent_module,
    policy_observation,
    state_snapshot,
)


def item_volume(item: dict[str, Any]) -> float:
    return float(item["length"]) * float(item["width"]) * float(item["height"])


def summarize_results(
    visible_items: list[dict[str, Any]], results: list[dict[str, Any]],
) -> dict[str, Any]:
    by_id = {int(item["index"]): item for item in visible_items}
    feasible_ids = sorted({
        int(row["stable_item_index"])
        for row in results if row["is_placed_safe"]
    })
    feasible = [by_id[index] for index in feasible_ids]
    return {
        "visible_item_count": len(visible_items),
        "candidate_action_count": len(results),
        "feasible_visible_item_count": len(feasible),
        "feasible_visible_item_volume": sum(map(item_volume, feasible)),
        "feasible_priority_count": sum(
            bool(item.get("is_prioritized")) for item in feasible
        ),
        "feasible_soft_count": sum(bool(item.get("is_soft")) for item in feasible),
        "feasible_stable_item_indices": feasible_ids,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=pathlib.Path, required=True)
    parser.add_argument("--config", type=pathlib.Path, default=DEFAULT_CONFIG)
    parser.add_argument("--case", required=True)
    parser.add_argument("--attempt-budget", type=int, default=512)
    parser.add_argument("--split", choices=("development", "validation"), required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    if args.output.exists() and not args.overwrite:
        raise SystemExit(f"output already exists: {args.output}")
    if args.attempt_budget < 1:
        raise SystemExit("attempt-budget must be positive")

    snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
    contract = snapshot.get("replay_contract")
    if not isinstance(contract, dict):
        raise SystemExit("snapshot has no replay_contract")
    configs = json.loads(args.config.read_text(encoding="utf-8"))
    if args.case not in configs:
        raise SystemExit(f"unknown config case: {args.case}")
    task_config = configs[args.case]
    expected = snapshot.get("board_fingerprint") or board_fingerprint(snapshot)
    case_id = str(snapshot.get("case_id", args.case))
    root_step = int(snapshot.get("step", 0))

    if str(SIMULATOR) not in sys.path:
        sys.path.insert(0, str(SIMULATOR))
    from src.ground_handling.env import GroundHandlingEnv

    agent_module = load_agent_module()

    def env_factory():
        return GroundHandlingEnv(
            config=copy.deepcopy(task_config), verbose=False, render_mode=None
        )

    def snapshot_factory(env, raw_observation):
        return state_snapshot(
            env, policy_observation(env, raw_observation),
            case_id=case_id, step=root_step,
        )

    def reconstruct():
        env = env_factory()
        rebuilt = replay_action_prefix(
            env, contract, expected_fingerprint=expected,
            snapshot_factory=snapshot_factory, expected_snapshot=snapshot,
        )
        if not rebuilt.matched or rebuilt.observation is None:
            difference = None
            if rebuilt.observation is not None:
                difference = board_difference(
                    snapshot, snapshot_factory(env, rebuilt.observation)
                )
            env.close()
            raise RuntimeError(
                f"root reconstruction failed: {rebuilt.error}; difference={difference}"
            )
        return env, rebuilt.observation

    env, raw_observation = reconstruct()
    try:
        observation = policy_observation(env, raw_observation)
        visible_items = list(observation.get("pool_list", []))
        provider = build_candidate_provider(
            agent_module, attempt_budget=args.attempt_budget,
            include_release_fallbacks=True,
            scan_all_visible_items=True,
        )
        candidates = provider(env, raw_observation, 1_000_000)
    finally:
        env.close()

    results = []
    for candidate in candidates:
        env, _raw_observation = reconstruct()
        try:
            _observation, _reward, terminated, truncated, info = env.step(
                canonical_action(candidate.command_action)
            )
            status = info.get("status", {}) if isinstance(info, dict) else {}
            results.append({
                "candidate_id": candidate.candidate_id,
                "stable_item_index": int(
                    candidate.selection["stable_item_index"]
                ),
                "candidate_kind": candidate.selection["candidate_kind"],
                "is_placed_safe": bool(status.get("is_placed_safe")),
                "is_valid": bool(status.get("is_valid")),
                "is_included": bool(status.get("is_included")),
                "terminated": bool(terminated),
                "truncated": bool(truncated),
            })
        finally:
            env.close()

    report = {
        "schema_version": 1,
        "contract": (
            "all visible items scanned independently with fixed attempts; "
            "best settled and release-fallback actions physically replayed"
        ),
        "commit": git_commit(),
        "case_id": case_id,
        "root_step": root_step,
        "split": args.split,
        "board_fingerprint": expected,
        "attempt_budget_per_item": int(args.attempt_budget),
        "scenario_axes": scenario_axes(task_config),
        **summarize_results(visible_items, results),
        "candidate_results": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
