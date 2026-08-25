"""Measure H1/H3/H5 physical prefixes against frozen terminal truth.

The terminal oracle remains the label.  This audit replays the exact recorded
behavior-policy roots and caps each root-candidate continuation after a fixed
number of rank-0 physical steps.  A cap therefore produces an achieved vector,
never a learned suffix value.  Results quantify how much terminal action recall
is available inside a production-sized physical-step budget.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "simulator") not in sys.path:
    sys.path.insert(0, str(ROOT / "simulator"))

from scripts.build_counterfactual_graph import build_candidate_provider  # noqa: E402
from scripts.build_replay_dataset import (  # noqa: E402
    json_safe,
    load_agent_module,
    policy_observation,
    require_supported_python,
    state_snapshot,
)
from scripts.build_terminal_rollout_trigger_dataset import pareto_ids  # noqa: E402
from scripts.counterfactual_graph import board_fingerprint  # noqa: E402
from scripts.run_self_play_packing import _safe, _status  # noqa: E402
from scripts.run_single_agent_packing import _fresh_env  # noqa: E402
from scripts.run_vector_mcts import vector_search_root  # noqa: E402
from scripts.rollout_checkpoint_summary import summarize_roots  # noqa: E402


def choose_checkpoint_candidate(
    candidate_order: list[str], *, incumbent: str,
    frontier: list[str],
) -> str:
    """Use the same conservative Pareto switch contract as live rollout."""
    frontier_set = set(frontier)
    if incumbent in frontier_set:
        return incumbent
    return next(
        (candidate for candidate in candidate_order if candidate in frontier_set),
        incumbent,
    )


def _candidates_at_prefix(
    agent_module, task_config: dict[str, Any], *, case_id: str,
    environment_seed: int, prefix_actions: list[Any], attempt_budget: int,
    top_k: int, step: int,
):
    provider = build_candidate_provider(
        agent_module, attempt_budget=attempt_budget,
        scan_all_visible_items=True,
    )
    env = _fresh_env(task_config)
    try:
        env.reset_settings()
        env.reset_item_stream()
        observation, _info = env.reset(seed=environment_seed)
        for index, action in enumerate(prefix_actions):
            observation, _reward, terminated, truncated, info = env.step(action)
            if not _safe(_status(info)) or terminated or truncated:
                raise RuntimeError(f"prefix failed at action {index}")
        observed = policy_observation(env, observation)
        snapshot = state_snapshot(env, observed, case_id=case_id, step=step)
        return list(provider(env, observation, int(top_k))), board_fingerprint(snapshot)
    finally:
        env.close()


def audit(
    manifest: dict[str, Any], trigger_dataset: dict[str, Any],
    task_config: dict[str, Any], *, cell: str, caps: list[int],
    attempt_budget: int, top_k: int, rollout_top_k: int,
) -> dict[str, Any]:
    agent_module = load_agent_module()
    case_id = str(manifest["case_id"])
    environment_seed = int(manifest["environment_seed"])
    targets = {
        str(row["root_id"]): row
        for row in trigger_dataset.get("rows") or []
        if str(row.get("cell")) == cell
        and (
            row.get("terminal_intervention")
            or row.get("terminal_resurrection_present")
        )
    }
    records = [
        record
        for episode in manifest.get("episodes") or []
        for record in episode.get("records") or []
    ]
    roots = []
    prefix_actions: list[Any] = []
    for record in records:
        root_id = str(record["root_id"])
        if root_id in targets:
            source = targets[root_id]
            candidates, observed_fingerprint = _candidates_at_prefix(
                agent_module, task_config, case_id=case_id,
                environment_seed=environment_seed,
                prefix_actions=prefix_actions,
                attempt_budget=attempt_budget, top_k=top_k,
                step=int(record["step"]),
            )
            if observed_fingerprint != str(record["board_fingerprint"]):
                raise RuntimeError(f"{root_id}: prefix fingerprint mismatch")
            source_order = [
                str(row["root_candidate_id"])
                for row in source["candidates"] if row.get("safe")
            ]
            root = {
                "root_id": root_id,
                "cell": cell,
                "step": int(record["step"]),
                "incumbent_candidate_id": str(source["incumbent_candidate_id"]),
                "terminal_selected_candidate_id": str(source["selected_candidate_id"]),
                "terminal_pareto_candidates": list(
                    source["terminal_pareto_candidates"]
                ),
                "target_reason": {
                    "terminal_intervention": bool(source["terminal_intervention"]),
                    "terminal_resurrection": bool(
                        source["terminal_resurrection_present"]
                    ),
                },
                "checkpoints": {},
            }
            source_search_seconds = float(
                (source.get("search_timing") or {}).get(
                    "search_total_seconds", 0.0
                )
            )
            decision_seconds = float(
                (source.get("decision_timing") or {}).get(
                    "decision_total_seconds", source_search_seconds
                )
            )
            non_search_seconds = max(0.0, decision_seconds - source_search_seconds)
            for cap in caps:
                result = vector_search_root(
                    agent_module, task_config, case_id=case_id,
                    environment_seed=environment_seed,
                    prefix_actions=list(prefix_actions),
                    root_candidates=candidates,
                    attempt_budget=attempt_budget,
                    deep_top_k=top_k, expansions=0, max_depth=1,
                    step=int(record["step"]), leaf_eval="measured",
                    rollout_top_k=rollout_top_k,
                    rollout_max_steps=cap, terminal_audit=True,
                    allocation="frontier",
                    item_symmetry_cache_shadow=True,
                    item_symmetry_terminal_cache=True,
                )
                checkpoint_candidates = [
                    {
                        "root_candidate_id": row["root_candidate_id"],
                        "safe": row["safe"],
                        "checkpoint_vector": row.get(
                            "terminal_checkpoint_vector"
                        ),
                        "termination": row.get("terminal_termination"),
                        "continuation_steps": row.get(
                            "terminal_continuation_steps"
                        ),
                        "physical_step_equivalents": row.get(
                            "terminal_physical_step_equivalents"
                        ),
                    }
                    for row in result["root_candidates"]
                ]
                observed_ids = {
                    str(row["root_candidate_id"])
                    for row in checkpoint_candidates if row["safe"]
                }
                if observed_ids != set(source_order):
                    raise RuntimeError(f"{root_id}: candidate support mismatch")
                frontier = pareto_ids(
                    checkpoint_candidates, "checkpoint_vector"
                )
                selected = choose_checkpoint_candidate(
                    source_order,
                    incumbent=str(source["incumbent_candidate_id"]),
                    frontier=frontier,
                )
                search_seconds = float(
                    (result.get("timing") or {}).get(
                        "search_total_seconds", 0.0
                    )
                )
                root["checkpoints"][str(cap)] = {
                    "continuation_cap": cap,
                    "total_depth": cap + 1,
                    "pareto_candidates": frontier,
                    "selected_candidate_id": selected,
                    "matches_terminal_action": (
                        selected == str(source["selected_candidate_id"])
                    ),
                    "search_seconds": search_seconds,
                    "estimated_decision_seconds": non_search_seconds + search_seconds,
                    "physical_step_equivalents": int(
                        result["terminal_rollout_physical_step_equivalents"]
                    ),
                    "candidates": checkpoint_candidates,
                }
            roots.append(root)
        prefix_actions.append(record["action"])
    missing = sorted(set(targets) - {root["root_id"] for root in roots})
    if missing:
        raise RuntimeError(f"target roots missing from manifest: {missing}")
    return {
        "contract": "bounded_physical_rollout_checkpoint_oracle_v1",
        "cell": cell,
        "case_id": case_id,
        "environment_seed": environment_seed,
        "continuation_caps": caps,
        "total_depths": [cap + 1 for cap in caps],
        "selection_contract": "checkpoint_pareto_conservative_incumbent",
        "value_model": None,
        "roots": roots,
        "summary": summarize_roots(roots, caps),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=pathlib.Path, required=True)
    parser.add_argument("--trigger-dataset", type=pathlib.Path, required=True)
    parser.add_argument("--config", type=pathlib.Path, required=True)
    parser.add_argument("--cell", required=True)
    parser.add_argument("--caps", default="0,2,4")
    parser.add_argument("--attempt-budget", type=int, default=128)
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--rollout-top-k", type=int, default=3)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    require_supported_python()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    dataset = json.loads(args.trigger_dataset.read_text(encoding="utf-8"))
    config = json.loads(args.config.read_text(encoding="utf-8"))
    task_config = config[manifest["case_id"]]
    caps = sorted({int(value) for value in args.caps.split(",")})
    if not caps or caps[0] < 0:
        raise ValueError("caps must be non-negative")
    result = audit(
        manifest, dataset, task_config, cell=args.cell, caps=caps,
        attempt_budget=args.attempt_budget, top_k=args.top_k,
        rollout_top_k=args.rollout_top_k,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(json_safe(result), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result["summary"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
