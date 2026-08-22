"""Replay provider-zero boards and test bounded rescue proposal strategies."""

from __future__ import annotations

import argparse
import collections
import copy
import json
import pathlib
import sys
import time
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
SIMULATOR = ROOT / "simulator"
for path in (ROOT, SIMULATOR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from scripts.build_counterfactual_graph import (  # noqa: E402
    build_candidate_provider,
)
from scripts.build_replay_dataset import (  # noqa: E402
    load_agent_module,
    policy_observation,
    state_snapshot,
)
from scripts.counterfactual_graph import (  # noqa: E402
    board_fingerprint,
    replay_action_prefix,
)
from scripts.run_self_play_packing import (  # noqa: E402
    build_exact_physical_legal_filter,
)


STRATEGY_SPECS = {
    "deep4x": {"attempt_multiplier": 4, "candidate_stride": 1},
    "deep16x": {"attempt_multiplier": 16, "candidate_stride": 1},
    "stride4": {"attempt_multiplier": 1, "candidate_stride": 4},
    "stride16": {"attempt_multiplier": 1, "candidate_stride": 16},
}


def load_task_config(source_root: pathlib.Path, state: dict[str, Any]):
    manifest_path = source_root / state["source_manifest"]
    if not manifest_path.exists():
        raise FileNotFoundError(f"missing source manifest: {manifest_path}")
    scenario = str(state["case_id"]).removeprefix("m-")
    config_path = manifest_path.parent.parent / "configs" / f"{scenario}.json"
    cases = json.loads(config_path.read_text(encoding="utf-8"))
    if state["case_id"] not in cases:
        raise KeyError(f"missing {state['case_id']} in {config_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    attempt_budget = int(manifest["candidate_contract"]["attempt_budget"])
    return cases[state["case_id"]], attempt_budget


def resolve_strategies(
    baseline_attempt_budget: int,
    specs: dict[str, dict[str, int]] = STRATEGY_SPECS,
) -> dict[str, dict[str, int]]:
    if baseline_attempt_budget < 1:
        raise ValueError("baseline attempt budget must be positive")
    return {
        name: {
            "attempt_budget": (
                baseline_attempt_budget * int(spec["attempt_multiplier"])
            ),
            "candidate_stride": int(spec["candidate_stride"]),
        }
        for name, spec in specs.items()
    }


def _failure_channel(status: dict[str, Any]) -> str:
    for key in ("is_included", "is_valid", "is_placed_safe"):
        if status.get(key) is not True:
            return key
    return "safe"


def _candidate_summary(candidate: Any) -> dict[str, Any]:
    return {
        "candidate_id": str(candidate.candidate_id),
        "command_action": candidate.command_action,
        "selection": candidate.selection,
    }


def run_state(
    state: dict[str, Any], *, source_root: pathlib.Path, agent_module,
    strategy_specs: dict[str, dict[str, int]] = STRATEGY_SPECS,
) -> dict[str, Any]:
    from src.ground_handling.env import GroundHandlingEnv

    task_config, baseline_attempt_budget = load_task_config(source_root, state)
    strategies = resolve_strategies(
        baseline_attempt_budget, specs=strategy_specs
    )
    environment_seed = int(state["replay_contract"]["seed"])

    def env_factory():
        return GroundHandlingEnv(
            config=copy.deepcopy(task_config), verbose=False, render_mode=None
        )

    env = env_factory()
    try:
        rebuilt = replay_action_prefix(
            env,
            state["replay_contract"],
            expected_fingerprint=state["board_fingerprint"],
            snapshot_factory=lambda current, raw: state_snapshot(
                current,
                policy_observation(current, raw),
                case_id=state["case_id"],
                step=int(state["effective_step"]),
            ),
        )
        if not rebuilt.matched or rebuilt.observation is None:
            raise RuntimeError(
                f"provider-zero replay failed {state['board_fingerprint']}: "
                f"{rebuilt.error}; observed={rebuilt.observed_fingerprint}"
            )
        observed = policy_observation(env, rebuilt.observation)
        observed_fingerprint = board_fingerprint(state_snapshot(
            env,
            observed,
            case_id=state["case_id"],
            step=int(state["effective_step"]),
        ))
        baseline = build_candidate_provider(
            agent_module,
            attempt_budget=baseline_attempt_budget,
            scan_all_visible_items=True,
            candidate_stride=1,
        )(env, rebuilt.observation, 64)
        if baseline:
            raise RuntimeError(
                f"provider-zero invariant failed for {state['board_fingerprint']}: "
                f"baseline emitted {len(baseline)} proposal(s)"
            )
        legal_filter = build_exact_physical_legal_filter(
            task_config,
            case_id=state["case_id"],
            environment_seed=environment_seed,
            env_factory=env_factory,
        )
        outcomes = {}
        for name, spec in strategies.items():
            provider = build_candidate_provider(
                agent_module,
                attempt_budget=int(spec["attempt_budget"]),
                scan_all_visible_items=True,
                candidate_stride=int(spec["candidate_stride"]),
            )
            started = time.perf_counter()
            proposals = list(provider(env, rebuilt.observation, 64))
            generated = time.perf_counter()
            safe, audit = legal_filter(
                env=env,
                observation=rebuilt.observation,
                candidates=proposals,
                actions=list(state["replay_contract"]["action_prefix"]),
                step=int(state["effective_step"]),
            )
            filtered = time.perf_counter()
            channels = collections.Counter(
                _failure_channel(row.get("status", {}))
                for row in audit.get("candidates", [])
            )
            outcomes[name] = {
                "strategy": dict(spec),
                "proposal_count": len(proposals),
                "safe_count": len(safe),
                "rescued": bool(safe),
                "generation_seconds": generated - started,
                "physical_filter_seconds": filtered - generated,
                "failure_channels": dict(sorted(channels.items())),
                "safe_candidates": [_candidate_summary(row) for row in safe],
            }
    finally:
        env.close()

    return {
        "board_fingerprint": state["board_fingerprint"],
        "observed_fingerprint": observed_fingerprint,
        "case_id": state["case_id"],
        "effective_step": int(state["effective_step"]),
        "stratum": state["stratum"],
        "occurrence_count": int(state["occurrence_count"]),
        "baseline_attempt_budget": baseline_attempt_budget,
        "baseline_provider_confirmed_empty": True,
        "strategies": outcomes,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=pathlib.Path, required=True)
    parser.add_argument("--source-root", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument("--shard-index", type=int, default=0)
    parser.add_argument("--shard-count", type=int, default=1)
    args = parser.parse_args()
    if args.shard_count < 1 or not 0 <= args.shard_index < args.shard_count:
        raise SystemExit("invalid shard index/count")

    corpus = json.loads(args.corpus.read_text(encoding="utf-8"))
    states = [
        row for index, row in enumerate(corpus.get("states", []))
        if index % args.shard_count == args.shard_index
    ]
    agent_module = load_agent_module()
    rows = [
        run_state(row, source_root=args.source_root, agent_module=agent_module)
        for row in states
    ]
    payload = {
        "schema_version": 1,
        "experiment": "provider_zero_rescue",
        "complete": True,
        "shard_index": int(args.shard_index),
        "shard_count": int(args.shard_count),
        "assigned_state_count": len(states),
        "strategy_specs": STRATEGY_SPECS,
        "states": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
