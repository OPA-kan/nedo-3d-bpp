"""Execute a V-free single-agent terminal-rollout improvement policy.

At each live state, every bounded legacy root candidate is physically forced
and then continued by the frozen rank-0 policy to a genuine terminal.  The
incumbent rank-0 action is replaced only when it is absent from the complete
terminal Pareto frontier.  No component weights and no learned value are used.
Any censored terminal comparison fails safe to the incumbent.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import platform
import sys
import time
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "simulator") not in sys.path:
    sys.path.insert(0, str(ROOT / "simulator"))

from scripts.build_counterfactual_graph import (  # noqa: E402
    build_candidate_provider,
    cumulative_metrics,
)
from scripts.build_replay_dataset import (  # noqa: E402
    json_safe,
    load_agent_module,
    policy_observation,
    require_supported_python,
    state_snapshot,
)
from scripts.counterfactual_graph import (  # noqa: E402
    board_fingerprint,
    item_symmetry_board_fingerprint,
    stable_id,
)
from scripts.run_self_play_packing import (  # noqa: E402
    _candidate_action,
    _candidate_record,
    _candidate_selection,
    _compact_evaluation,
    _safe,
    _status,
)
from scripts.run_single_agent_packing import _fresh_env  # noqa: E402
from scripts.run_vector_mcts import vector_search_root  # noqa: E402
from scripts.single_agent_packing import GENUINE_TERMINATIONS  # noqa: E402

POLICIES = {"legacy", "terminal-rollout"}
BEHAVIOR_CONTRACT = "single_agent_terminal_rollout_policy_v3_wall_clock"
TIMING_CONTRACT = "decision_wall_clock_v1"


def _rank_key(candidate: Any) -> tuple[int, str]:
    return (
        int(_candidate_selection(candidate).get("rank", 10**9)),
        str(_candidate_record(candidate)["candidate_id"]),
    )


def choose_root_candidate(
    candidates: list[Any], search_result: dict[str, Any], *, policy: str,
) -> tuple[Any | None, dict[str, Any]]:
    """Choose conservatively from physically safe root candidates."""
    if policy not in POLICIES:
        raise ValueError(f"unsupported policy: {policy}")
    safe_ids = {
        str(row["root_candidate_id"])
        for row in search_result.get("root_candidates") or []
        if row.get("safe")
    }
    ranked = sorted(
        (
            candidate for candidate in candidates
            if str(_candidate_record(candidate)["candidate_id"]) in safe_ids
        ),
        key=_rank_key,
    )
    if not ranked:
        return None, {
            "policy": policy,
            "reason": "no_safe_candidate",
            "switched": False,
            "incumbent_candidate_id": None,
            "selected_candidate_id": None,
        }
    incumbent = ranked[0]
    incumbent_id = str(_candidate_record(incumbent)["candidate_id"])
    chosen = incumbent
    reason = "legacy_rank0"
    if policy == "terminal-rollout":
        if not search_result.get("terminal_truth_complete"):
            reason = "terminal_truth_censored"
        else:
            frontier = {
                str(value)
                for value in search_result.get("terminal_pareto_candidates") or []
            }
            if incumbent_id in frontier:
                reason = "incumbent_terminal_pareto"
            else:
                alternatives = [
                    candidate for candidate in ranked
                    if str(_candidate_record(candidate)["candidate_id"])
                    in frontier
                ]
                if alternatives:
                    chosen = alternatives[0]
                    reason = "terminal_dominance_switch"
                else:
                    reason = "terminal_frontier_empty"
    selected_id = str(_candidate_record(chosen)["candidate_id"])
    return chosen, {
        "policy": policy,
        "reason": reason,
        "switched": selected_id != incumbent_id,
        "incumbent_candidate_id": incumbent_id,
        "selected_candidate_id": selected_id,
    }


def _search_record(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "leaf_eval": result.get("leaf_eval"),
        "terminal_truth_complete": bool(
            result.get("terminal_truth_complete")
        ),
        "terminal_censored_candidates": result.get(
            "terminal_censored_candidates"
        ),
        "terminal_pareto_candidates": result.get(
            "terminal_pareto_candidates"
        ),
        "physical_steps": int(result.get("physical_steps", 0)),
        "physical_step_equivalents": int(
            result.get("physical_step_equivalents", 0)
        ),
        "terminal_rollout_physical_steps": int(
            result.get("terminal_rollout_physical_steps", 0)
        ),
        "terminal_rollout_physical_step_equivalents": int(
            result.get(
                "terminal_rollout_physical_step_equivalents", 0
            )
        ),
        "terminal_rollout_legal_filter_symmetry_reused": int(
            result.get(
                "terminal_rollout_legal_filter_symmetry_reused", 0
            )
        ),
        "item_symmetry_cache_shadow": result.get(
            "item_symmetry_cache_shadow"
        ),
        "item_symmetry_terminal_cache": result.get(
            "item_symmetry_terminal_cache"
        ),
        "timing": result.get("timing"),
        "root_candidates": [
            {
                key: row.get(key)
                for key in (
                    "root_candidate_id", "stable_item_index", "safe",
                    "one_step_vector", "terminal_genuine",
                    "terminal_termination", "terminal_vector",
                    "terminal_continuation_actions",
                    "terminal_physical_step_equivalents",
                    "terminal_legal_filter_symmetry_reused",
                    "terminal_symmetry_cache_hit",
                    "terminal_symmetry_cache_source",
                )
            }
            for row in result.get("root_candidates") or []
        ],
    }


def run_episode(
    agent_module, task_config: dict[str, Any], *, case_id: str,
    environment_seed: int, attempt_budget: int, top_k: int,
    rollout_top_k: int, rollout_max_steps: int, max_steps: int,
    policy: str, output_dir: pathlib.Path,
) -> dict[str, Any]:
    if policy not in POLICIES:
        raise ValueError(f"unsupported policy: {policy}")
    provider = build_candidate_provider(
        agent_module, attempt_budget=attempt_budget,
        scan_all_visible_items=True,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    env = _fresh_env(task_config)
    try:
        env.reset_settings()
        env.reset_item_stream()
        observation, _info = env.reset(seed=environment_seed)
        executed: list[Any] = []
        records = []
        termination = None
        for step in range(max_steps):
            decision_started = time.perf_counter()
            phase_started = time.perf_counter()
            observed = policy_observation(env, observation)
            snapshot = state_snapshot(
                env, observed, case_id=case_id, step=step,
            )
            fingerprint = board_fingerprint(snapshot)
            symmetry_fingerprint = item_symmetry_board_fingerprint(snapshot)
            root_id = stable_id("terminal-rollout-policy-root", {
                "board": fingerprint,
                "placements": len(executed),
            })
            snapshot_path = output_dir / f"step-{step:03d}-state.json"
            snapshot["behavior_contract"] = BEHAVIOR_CONTRACT
            snapshot["item_symmetry_fingerprint"] = symmetry_fingerprint
            snapshot_path.write_text(
                json.dumps(json_safe(snapshot), ensure_ascii=False, indent=2)
                + "\n",
                encoding="utf-8",
            )
            state_capture_seconds = time.perf_counter() - phase_started
            phase_started = time.perf_counter()
            candidates = list(provider(env, observation, int(top_k)))
            provider_seconds = time.perf_counter() - phase_started
            if not candidates:
                termination = "no_retained_candidate"
                break
            leaf_eval = "rollout" if policy == "terminal-rollout" else "measured"
            phase_started = time.perf_counter()
            search = vector_search_root(
                agent_module, task_config, case_id=case_id,
                environment_seed=environment_seed,
                prefix_actions=list(executed),
                root_candidates=candidates,
                attempt_budget=attempt_budget,
                deep_top_k=top_k,
                expansions=0,
                max_depth=1,
                step=step,
                leaf_eval=leaf_eval,
                rollout_top_k=rollout_top_k,
                rollout_max_steps=rollout_max_steps,
                allocation="frontier",
                item_symmetry_cache_shadow=True,
                item_symmetry_terminal_cache=(
                    policy == "terminal-rollout"
                ),
            )
            search_seconds = time.perf_counter() - phase_started
            phase_started = time.perf_counter()
            chosen, selection = choose_root_candidate(
                candidates, search, policy=policy,
            )
            selection_seconds = time.perf_counter() - phase_started
            if chosen is None:
                termination = "no_safe_retained_candidate"
                break
            before = cumulative_metrics(env)
            action = _candidate_action(chosen)
            phase_started = time.perf_counter()
            observation, _reward, terminated, truncated, info = env.step(action)
            live_action_seconds = time.perf_counter() - phase_started
            executed.append(action)
            status = _status(info)
            timing = {
                "contract": TIMING_CONTRACT,
                "state_capture_seconds": state_capture_seconds,
                "provider_seconds": provider_seconds,
                "search_seconds": search_seconds,
                "selection_seconds": selection_seconds,
                "live_action_seconds": live_action_seconds,
                "decision_total_seconds": (
                    time.perf_counter() - decision_started
                ),
            }
            records.append({
                "step": int(step),
                "root_id": root_id,
                "snapshot_path": snapshot_path.name,
                "board_fingerprint": fingerprint,
                "item_symmetry_fingerprint": symmetry_fingerprint,
                "selection": selection,
                "action": json_safe(action),
                "metrics_before": before,
                "search": _search_record(search),
                "timing": timing,
                "status": status,
            })
            if not _safe(status):
                termination = "selected_action_failure"
                break
            if truncated:
                termination = "simulator_truncated"
                break
            if terminated:
                termination = "stream_exhausted"
                break
        else:
            termination = "max_steps"
        final_metrics = cumulative_metrics(env)
        evaluation = None
        if termination in GENUINE_TERMINATIONS:
            evaluation = _compact_evaluation(env.evaluate())
            shake = (evaluation or {}).get("shake_response") or {}
            for source, target in (
                ("shake_max_shift", "post_shake_max_shift"),
                ("shake_peak_kinetic_energy", "post_shake_peak_kinetic_energy"),
                ("shake_items_toppled", "post_shake_items_toppled"),
            ):
                if source in shake:
                    final_metrics[target] = shake[source]
        return {
            "behavior_contract": BEHAVIOR_CONTRACT,
            "policy": policy,
            "steps": len(records),
            "termination": termination,
            "genuine_termination": termination in GENUINE_TERMINATIONS,
            "records": records,
            "final_metrics": final_metrics,
            "evaluation": evaluation,
            "executed_actions": [json_safe(action) for action in executed],
            "terminal_dominance_switches": sum(
                bool(record["selection"]["switched"])
                for record in records
            ),
            "terminal_truth_complete_roots": sum(
                bool(record["search"]["terminal_truth_complete"])
                for record in records
            ),
            "terminal_truth_censored_roots": sum(
                not bool(record["search"]["terminal_truth_complete"])
                for record in records
                if policy == "terminal-rollout"
            ),
            "search_physical_steps": sum(
                int(record["search"]["physical_steps"])
                for record in records
            ),
            "search_physical_step_equivalents": sum(
                int(record["search"]["physical_step_equivalents"])
                for record in records
            ),
            "terminal_rollout_physical_steps": sum(
                int(record["search"]["terminal_rollout_physical_steps"])
                for record in records
            ),
            "terminal_rollout_physical_step_equivalents": sum(
                int(record["search"][
                    "terminal_rollout_physical_step_equivalents"
                ])
                for record in records
            ),
            "terminal_rollout_legal_filter_symmetry_reused": sum(
                int(record["search"][
                    "terminal_rollout_legal_filter_symmetry_reused"
                ])
                for record in records
            ),
            "terminal_symmetry_cache_hits": sum(
                int((record["search"].get(
                    "item_symmetry_terminal_cache"
                ) or {}).get("hits", 0))
                for record in records
            ),
            "terminal_symmetry_cache_saved_physical_steps": sum(
                int((record["search"].get(
                    "item_symmetry_terminal_cache"
                ) or {}).get("saved_physical_steps", 0))
                for record in records
            ),
            "terminal_symmetry_cache_saved_physical_step_equivalents": sum(
                int((record["search"].get(
                    "item_symmetry_terminal_cache"
                ) or {}).get("saved_physical_step_equivalents", 0))
                for record in records
            ),
        }
    finally:
        env.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=pathlib.Path, required=True)
    parser.add_argument("--case", required=True)
    parser.add_argument("--environment-seed", type=int, default=42)
    parser.add_argument("--attempt-budget", type=int, default=128)
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--rollout-top-k", type=int, default=3)
    parser.add_argument("--rollout-max-steps", type=int, default=40)
    parser.add_argument("--max-steps", type=int, default=40)
    parser.add_argument("--policy", choices=sorted(POLICIES), required=True)
    parser.add_argument("--output-dir", type=pathlib.Path, required=True)
    args = parser.parse_args()
    require_supported_python()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    task_config = config[args.case] if args.case in config else config
    episode = run_episode(
        load_agent_module(), task_config, case_id=args.case,
        environment_seed=args.environment_seed,
        attempt_budget=args.attempt_budget,
        top_k=args.top_k,
        rollout_top_k=args.rollout_top_k,
        rollout_max_steps=args.rollout_max_steps,
        max_steps=args.max_steps,
        policy=args.policy,
        output_dir=args.output_dir / "episode-000",
    )
    manifest = {
        "schema_version": 1,
        "experiment": "single-agent terminal rollout policy",
        "behavior_contract": BEHAVIOR_CONTRACT,
        "case_id": args.case,
        "environment_seed": args.environment_seed,
        "policy": args.policy,
        "selection_contract": (
            "terminal_pareto_dominance_switch_else_legacy_rank0"
            if args.policy == "terminal-rollout" else "legacy_safe_rank0"
        ),
        "value_model": None,
        "timing_contract": {
            "decision": TIMING_CONTRACT,
            "search": "vector_search_wall_clock_v1",
            "sla_seconds": 10.0,
            "clock": "time.perf_counter",
            "platform": platform.platform(),
            "python": platform.python_version(),
            "sample_scope": (
                "decisions_that_execute_a_live_action; terminal provider-empty "
                "checks without an action are not episode records"
            ),
        },
        "candidate_contract": {
            "provider": "placement_core_item_stratified_fixed_attempts",
            "attempt_budget": args.attempt_budget,
            "top_k": args.top_k,
        },
        "rollout_contract": {
            "policy": "frozen_rank0_exact_physical_filter",
            "top_k": args.rollout_top_k,
            "max_continuation_steps": args.rollout_max_steps,
            "censor_on_cap": True,
            "identical_item_terminal_cache": True,
        } if args.policy == "terminal-rollout" else None,
        "episodes": [episode],
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    output = args.output_dir / "manifest.json"
    output.write_text(
        json.dumps(json_safe(manifest), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"policy={args.policy} steps={episode['steps']} "
        f"termination={episode['termination']} "
        f"switches={episode['terminal_dominance_switches']} "
        f"rollout_physical_steps={episode['terminal_rollout_physical_steps']}"
    )
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
