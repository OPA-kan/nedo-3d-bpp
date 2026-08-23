"""Single-agent mainline runner (Phase 2).

One agent places the stream with the rank-0 legacy policy. At every
step, the union of legacy top-k and strategy-free coverage proposals is
measured — each candidate executed for one bounded physical step in a
fresh replayed environment — producing JointOutcomeSample v3 rows under
``behavior_contract = single_agent_v1``: raw component vectors, full
candidate provenance, world identity, and unsafe attempts kept as
negative support evidence. Execution and termination depend only on the
ranked legacy support, so trajectories are physically identical to the
frozen two-player rank-0 runs of the same seeds — the refactor's
verification gate.

Contract: reports/self-play-packing/single-agent-mainline-contract.md
"""

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
    capture_replay_contract,
    replay_action_prefix,
    stable_id,
    state_tensor_from_snapshot,
)
from scripts.coverage_action_sampler import coverage_candidates  # noqa: E402
from scripts.exogenous_world import ExogenousWorld  # noqa: E402
from scripts.run_self_play_packing import (  # noqa: E402
    _candidate_action,
    _candidate_record,
    _candidate_selection,
    _candidate_set_id,
    _compact_evaluation,
    _safe,
    _status,
)
from scripts.single_agent_packing import (  # noqa: E402
    BEHAVIOR_CONTRACT,
    GENUINE_TERMINATIONS,
    component_delta_vector,
    suffix_value_heads,
)


def _fresh_env(task_config: dict[str, Any]):
    from src.ground_handling.env import GroundHandlingEnv

    return GroundHandlingEnv(
        config=copy.deepcopy(task_config), verbose=False, render_mode=None,
    )


def measure_candidates(
    task_config: dict[str, Any], *, env, observation, candidates,
    executed_actions, case_id: str, environment_seed: int, step: int,
    root_id: str,
) -> list[dict[str, Any]]:
    """Execute each union candidate one bounded step in a fresh replay."""
    observed = policy_observation(env, observation)
    expected_snapshot = state_snapshot(
        env, observed, case_id=case_id, step=int(step)
    )
    expected_fingerprint = board_fingerprint(expected_snapshot)
    contract = capture_replay_contract(
        env, executed_actions, seed=environment_seed
    )
    rows = []
    for candidate in candidates:
        preview = _fresh_env(task_config)
        try:
            rebuilt = replay_action_prefix(
                preview, contract,
                expected_fingerprint=expected_fingerprint,
                expected_snapshot=expected_snapshot,
                snapshot_factory=lambda current, raw: state_snapshot(
                    current, policy_observation(current, raw),
                    case_id=case_id, step=int(step),
                ),
            )
            if not rebuilt.matched:
                raise RuntimeError(
                    f"measurement preview reconstruction failed: {rebuilt.error}"
                )
            before = cumulative_metrics(preview)
            action = _candidate_action(candidate)
            raw_observation, _r, terminated, truncated, info = preview.step(
                action
            )
            status = _status(info)
            safe = _safe(status)
            world = ExogenousWorld(
                base_seed=int(environment_seed),
                root_id=root_id,
                sample_index=0,
                future_stream_id=contract.get("future_stream_id"),
            )
            row = {
                "schema_version": 3,
                "behavior_contract": BEHAVIOR_CONTRACT,
                "contract": "single_agent_bounded_component_measurement",
                "world_realization": "degenerate_deterministic_stream",
                "root_id": root_id,
                "step": int(step),
                "root_candidate_id": _candidate_record(candidate)[
                    "candidate_id"
                ],
                "root_candidate_provenance": _candidate_record(candidate)[
                    "proposal_provenance"
                ],
                "exogenous_world_id": world.world_id,
                "exogenous_world_sample_index": 0,
                "exogenous_world": world.identity,
                "physical_safe": bool(safe),
                "status": status,
                "termination": (
                    "stream_exhausted" if (safe and terminated)
                    else "simulator_truncated" if truncated
                    else "bounded_step" if safe
                    else "rejected"
                ),
            }
            if safe:
                after = cumulative_metrics(preview)
                heads = component_delta_vector(before, after)
                leaf_observed = policy_observation(preview, raw_observation)
                leaf_snapshot = state_snapshot(
                    preview, leaf_observed, case_id=case_id, step=int(step) + 1
                )
                row.update({
                    "heads": heads,
                    "raw_outcome_vector": {
                        name: head.get("value")
                        for name, head in heads.items()
                    },
                    "head_eligibility": {
                        name: bool(head.get("target_eligible"))
                        for name, head in heads.items()
                    },
                    "leaf_state": state_tensor_from_snapshot(leaf_snapshot),
                    "leaf_board_fingerprint": board_fingerprint(leaf_snapshot),
                })
            rows.append(row)
        finally:
            preview.close()
    return rows


def run_episode(
    agent_module, task_config: dict[str, Any], *, case_id: str,
    environment_seed: int, attempt_budget: int, top_k: int,
    max_steps: int, coverage_per_step: int, coverage_sample_budget: int,
    coverage_seed: int | None, output_dir: pathlib.Path,
) -> dict[str, Any]:
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
            observed = policy_observation(env, observation)
            snapshot = state_snapshot(
                env, observed, case_id=case_id, step=step
            )
            fingerprint = board_fingerprint(snapshot)
            root_id = stable_id("single-agent-root", {
                "board": fingerprint,
                "placements": len(executed),
            })
            snapshot_path = output_dir / f"step-{step:03d}-state.json"
            snapshot["behavior_contract"] = BEHAVIOR_CONTRACT
            snapshot_path.write_text(
                json.dumps(json_safe(snapshot), ensure_ascii=False, indent=2)
                + "\n",
                encoding="utf-8",
            )
            legacy = list(provider(env, observation, int(top_k)))
            coverage = (
                coverage_candidates(
                    observed,
                    coverage_seed=int(coverage_seed) + step,
                    budget=int(coverage_sample_budget),
                    z_mode="volume",
                )
                if coverage_per_step > 0 else []
            )
            union = legacy + coverage
            if not legacy:
                termination = "no_retained_candidate"
                break
            # Measurement decides safety; every attempt is recorded, and
            # unsafe rows stay as negative support evidence. The support
            # id covers the safe comparison set: legacy-safe plus at most
            # coverage_per_step safe coverage candidates.
            by_id = {
                _candidate_record(candidate)["candidate_id"]: candidate
                for candidate in union
            }
            measured = measure_candidates(
                task_config, env=env, observation=observation,
                candidates=union, executed_actions=executed,
                case_id=case_id, environment_seed=environment_seed,
                step=step, root_id=root_id,
            )
            safe_by_id = {
                row["root_candidate_id"]: row
                for row in measured if row["physical_safe"]
            }
            support_ids = [
                _candidate_record(candidate)["candidate_id"]
                for candidate in legacy
                if _candidate_record(candidate)["candidate_id"] in safe_by_id
            ]
            coverage_kept = 0
            for candidate in coverage:
                identifier = _candidate_record(candidate)["candidate_id"]
                if identifier in safe_by_id:
                    if coverage_kept >= max(coverage_per_step, 0):
                        continue
                    support_ids.append(identifier)
                    coverage_kept += 1
            candidate_set_id = _candidate_set_id(
                [by_id[identifier] for identifier in support_ids]
            ) if support_ids else None
            support = set(support_ids)
            for row in measured:
                row["candidate_set_id"] = candidate_set_id
                row["in_comparison_support"] = (
                    row["root_candidate_id"] in support
                )
                row["outcome_sample_id"] = stable_id(
                    "joint-outcome-sample-v3", {
                        "root_id": root_id,
                        "candidate_set_id": candidate_set_id,
                        "root_candidate_id": row["root_candidate_id"],
                        "exogenous_world_id": row["exogenous_world_id"],
                        "termination": row["termination"],
                    },
                )
            legacy_safe = [
                candidate for candidate in legacy
                if _candidate_record(candidate)["candidate_id"] in safe_by_id
            ]
            if not legacy_safe:
                termination = "no_safe_retained_candidate"
                break
            chosen = min(
                legacy_safe,
                key=lambda candidate: (
                    int(_candidate_selection(candidate).get("rank", 10**9)),
                    _candidate_record(candidate)["candidate_id"],
                ),
            )
            metrics_before = cumulative_metrics(env)
            action = _candidate_action(chosen)
            observation, _r, terminated, truncated, info = env.step(action)
            executed.append(action)
            if not _safe(_status(info)):
                termination = "selected_action_failure"
                break
            records.append({
                "step": step,
                "root_id": root_id,
                "snapshot_path": snapshot_path.name,
                "board_fingerprint": fingerprint,
                "candidate_set_id": candidate_set_id,
                "candidate_count": len(measured),
                "safe_candidate_count": len(safe_by_id),
                "measurement_samples": measured,
                "selected_candidate_id": _candidate_record(chosen)[
                    "candidate_id"
                ],
                "action": action,
                "metrics_before": metrics_before,
            })
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
                (
                    "shake_peak_kinetic_energy",
                    "post_shake_peak_kinetic_energy",
                ),
                ("shake_items_toppled", "post_shake_items_toppled"),
            ):
                if source in shake:
                    final_metrics[target] = shake[source]
        value_targets = [
            {
                "step": record["step"],
                "value_target_semantics": (
                    "V^pi_behavior_observed_suffix_not_V_star"
                ),
                "value_target_eligible": termination in GENUINE_TERMINATIONS,
                "value_heads": suffix_value_heads(
                    record["metrics_before"], final_metrics,
                    termination=termination,
                ),
            }
            for record in records
        ]
        return {
            "behavior_contract": BEHAVIOR_CONTRACT,
            "steps": len(records),
            "termination": termination,
            "genuine_termination": termination in GENUINE_TERMINATIONS,
            "records": records,
            "value_targets": value_targets,
            "final_metrics": final_metrics,
            "evaluation": evaluation,
            "executed_actions": [json_safe(a) for a in executed],
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
    parser.add_argument("--max-steps", type=int, default=40)
    parser.add_argument("--coverage-candidates-per-step", type=int, default=0)
    parser.add_argument("--coverage-sample-budget", type=int, default=0)
    parser.add_argument("--coverage-seed", type=int, default=None)
    parser.add_argument("--output-dir", type=pathlib.Path, required=True)
    args = parser.parse_args()
    require_supported_python()
    if args.coverage_candidates_per_step > 0 and args.coverage_seed is None:
        raise SystemExit("coverage collection needs an explicit seed")
    config = json.loads(args.config.read_text(encoding="utf-8"))
    task_config = config[args.case] if args.case in config else config
    agent_module = load_agent_module()
    episode = run_episode(
        agent_module, task_config, case_id=args.case,
        environment_seed=args.environment_seed,
        attempt_budget=args.attempt_budget, top_k=args.top_k,
        max_steps=args.max_steps,
        coverage_per_step=args.coverage_candidates_per_step,
        coverage_sample_budget=args.coverage_sample_budget,
        coverage_seed=args.coverage_seed,
        output_dir=args.output_dir / "episode-000",
    )
    manifest = {
        "schema_version": 1,
        "experiment": "single-agent packing mainline",
        "behavior_contract": BEHAVIOR_CONTRACT,
        "case_id": args.case,
        "environment_seed": args.environment_seed,
        "candidate_contract": {
            "provider": "placement_core_item_stratified_fixed_attempts",
            "attempt_budget": args.attempt_budget,
            "top_k": args.top_k,
            "measurement": "fresh_replay_single_bounded_step",
            "coverage_union": (
                {
                    "z_mode": "volume",
                    "candidates_per_step": args.coverage_candidates_per_step,
                    "sample_budget": args.coverage_sample_budget,
                    "seed": args.coverage_seed,
                }
                if args.coverage_candidates_per_step > 0 else None
            ),
            "execution_and_termination": "legacy_rank0_only",
        },
        "episodes": [episode],
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    path = args.output_dir / "manifest.json"
    path.write_text(
        json.dumps(json_safe(manifest), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    samples = sum(
        len(record["measurement_samples"]) for record in episode["records"]
    )
    print(
        f"steps={episode['steps']} termination={episode['termination']} "
        f"measurement_samples={samples}"
    )
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
