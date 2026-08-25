"""Replay hard roots with OOF-selected, deadline-aware physical rollout."""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time
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
from scripts.deadline_physical_rollout import (  # noqa: E402
    deadline_checkpoint_search,
)
from scripts.deadline_rollout_summary import summarize  # noqa: E402
from scripts.evaluate_budgeted_rollout_allocation import (  # noqa: E402
    allocated_candidates,
)
from scripts.run_self_play_packing import (  # noqa: E402
    _candidate_action,
    _candidate_record,
    _safe,
    _status,
    build_exact_physical_legal_filter,
)
from scripts.run_single_agent_packing import _fresh_env  # noqa: E402


ALTERNATE_MODES = ("allocator", "ranker_next")


def ranker_order_candidates(
    oof_row: dict[str, Any], *, budget: int
) -> list[str]:
    """Keep the incumbent and add alternates in provider rank order.

    This is the zero-cost trivial baseline arm: candidate_ids are stored in
    provider rank order (incumbent at rank 0), so the first alternates are the
    ranker's next-best actions. No model score participates.
    """
    candidate_ids = [str(value) for value in oof_row["candidate_ids"]]
    incumbent_index = int(oof_row["incumbent_index"])
    incumbent = candidate_ids[incumbent_index]
    alternatives = [
        index for index in range(len(candidate_ids))
        if index != incumbent_index
    ]
    chosen = {incumbent}
    chosen.update(
        candidate_ids[index] for index in alternatives[: max(0, budget - 1)]
    )
    return [candidate for candidate in candidate_ids if candidate in chosen]


def choose_from_checkpoint(
    candidate_order: list[str], *, incumbent: str,
    candidates: list[dict[str, Any]],
) -> tuple[str, list[str]]:
    frontier = pareto_ids(candidates, "checkpoint_vector")
    if incumbent in frontier:
        return incumbent, frontier
    selected = next(
        (candidate for candidate in candidate_order if candidate in frontier),
        incumbent,
    )
    return selected, frontier


def audit(
    manifest: dict[str, Any], trigger_dataset: dict[str, Any],
    oof_report: dict[str, Any], task_config: dict[str, Any], *, cell: str,
    attempt_budget: int, top_k: int, rollout_top_k: int,
    candidate_budget: int, decision_budget_seconds: float,
    live_action_reserve_seconds: float, max_continuation_steps: int,
    safety_factor: float, alternate_mode: str = "allocator",
) -> dict[str, Any]:
    if alternate_mode not in ALTERNATE_MODES:
        raise ValueError(f"unsupported alternate mode: {alternate_mode}")
    targets = {
        str(row["root_id"]): row
        for row in trigger_dataset.get("rows") or []
        if str(row.get("cell")) == cell
        and (row.get("terminal_intervention")
             or row.get("terminal_resurrection_present"))
    }
    oof_rows = {
        str(row["root_id"]): row
        for row in (oof_report.get("candidate_allocator") or {}).get(
            "oof_rows", []
        )
    }
    missing = sorted(root_id for root_id in targets if root_id not in oof_rows)
    if missing:
        raise ValueError(f"missing OOF rows: {missing[:3]}")

    agent_module = load_agent_module()
    provider = build_candidate_provider(
        agent_module, attempt_budget=attempt_budget,
        scan_all_visible_items=True,
    )
    case_id = str(manifest["case_id"])
    environment_seed = int(manifest["environment_seed"])
    legal_filter = build_exact_physical_legal_filter(
        task_config, case_id=case_id, environment_seed=environment_seed,
    )
    records = [
        record for episode in manifest.get("episodes") or []
        for record in episode.get("records") or []
    ]
    env = _fresh_env(task_config)
    roots = []
    executed: list[Any] = []
    try:
        env.reset_settings()
        env.reset_item_stream()
        observation, _info = env.reset(seed=environment_seed)
        for record_index, record in enumerate(records):
            root_id = str(record["root_id"])
            if root_id in targets:
                decision_started = time.perf_counter()
                observed = policy_observation(env, observation)
                snapshot = state_snapshot(
                    env, observed, case_id=case_id, step=int(record["step"]),
                )
                fingerprint = board_fingerprint(snapshot)
                if fingerprint != str(record["board_fingerprint"]):
                    raise RuntimeError(f"{root_id}: board fingerprint mismatch")
                provider_started = time.perf_counter()
                candidates = list(provider(env, observation, int(top_k)))
                provider_seconds = time.perf_counter() - provider_started
                by_id = {
                    str(_candidate_record(candidate)["candidate_id"]): candidate
                    for candidate in candidates
                }
                oof_row = oof_rows[root_id]
                expected_ids = set(map(str, oof_row["candidate_ids"]))
                missing_ids = sorted(expected_ids - set(by_id))
                if missing_ids:
                    raise RuntimeError(
                        f"{root_id}: candidate support missing {missing_ids}"
                    )
                if alternate_mode == "ranker_next":
                    allocated_ids = ranker_order_candidates(
                        oof_row, budget=candidate_budget
                    )
                else:
                    allocated_ids = allocated_candidates(
                        oof_row, budget=candidate_budget
                    )
                allocated = [by_id[candidate_id] for candidate_id in allocated_ids]
                deadline_at = (
                    decision_started + decision_budget_seconds
                    - live_action_reserve_seconds
                )
                search = deadline_checkpoint_search(
                    task_config,
                    environment_seed=environment_seed,
                    prefix_actions=list(executed),
                    candidates=allocated,
                    provider=provider,
                    legal_filter=legal_filter,
                    top_k=rollout_top_k,
                    root_step=int(record["step"]),
                    deadline_at=deadline_at,
                    max_continuation_steps=max_continuation_steps,
                    safety_factor=safety_factor,
                    minimum_reserve_seconds=live_action_reserve_seconds,
                )
                incumbent = str(targets[root_id]["incumbent_candidate_id"])
                selected, frontier = choose_from_checkpoint(
                    allocated_ids, incumbent=incumbent,
                    candidates=search["candidates"],
                )
                terminal_selected = str(targets[root_id]["selected_candidate_id"])
            else:
                decision_started = None
                provider_seconds = None
                allocated_ids = []
                search = None
                incumbent = selected = terminal_selected = None
                frontier = []

            replay_action = record["action"]
            action_started = time.perf_counter()
            observation, _reward, terminated, truncated, info = env.step(
                replay_action
            )
            live_action_seconds = time.perf_counter() - action_started
            executed.append(replay_action)
            if decision_started is not None:
                decision_seconds = time.perf_counter() - decision_started
                roots.append({
                    "root_id": root_id,
                    "cell": cell,
                    "step": int(record["step"]),
                    "incumbent_candidate_id": incumbent,
                    "allocated_candidate_ids": allocated_ids,
                    "checkpoint_pareto_candidates": frontier,
                    "selected_candidate_id": selected,
                    "terminal_selected_candidate_id": terminal_selected,
                    "terminal_selected_available": terminal_selected in allocated_ids,
                    "matches_terminal_action": selected == terminal_selected,
                    "provider_seconds": provider_seconds,
                    "live_action_seconds": live_action_seconds,
                    "decision_seconds": decision_seconds,
                    "decision_budget_met": decision_seconds <= decision_budget_seconds,
                    "search": search,
                })
            if not _safe(_status(info)) or terminated or truncated:
                if record_index != len(records) - 1:
                    raise RuntimeError("recorded prefix terminated early")
                break
    finally:
        env.close()
    return {
        "contract": "deadline_rollout_hard_state_audit_v1",
        "alternate_mode": alternate_mode,
        "cell": cell,
        "case_id": case_id,
        "candidate_budget": candidate_budget,
        "decision_budget_seconds": decision_budget_seconds,
        "live_action_reserve_seconds": live_action_reserve_seconds,
        "max_continuation_steps": max_continuation_steps,
        "max_total_depth": max_continuation_steps + 1,
        "safety_factor": safety_factor,
        "value_model": None,
        "summary": summarize(roots),
        "roots": roots,
    }


def main() -> int:
    require_supported_python()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=pathlib.Path, required=True)
    parser.add_argument("--trigger-dataset", type=pathlib.Path, required=True)
    parser.add_argument("--oof-report", type=pathlib.Path, required=True)
    parser.add_argument("--task-config", type=pathlib.Path, required=True)
    parser.add_argument("--cell", required=True)
    parser.add_argument("--attempt-budget", type=int, default=128)
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--rollout-top-k", type=int, default=3)
    parser.add_argument("--candidate-budget", type=int, default=2)
    parser.add_argument("--decision-budget-seconds", type=float, default=10.0)
    parser.add_argument("--live-action-reserve-seconds", type=float, default=0.25)
    parser.add_argument("--max-continuation-steps", type=int, default=2)
    parser.add_argument("--safety-factor", type=float, default=1.35)
    parser.add_argument(
        "--alternate-mode", choices=ALTERNATE_MODES, default="allocator",
    )
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    config = json.loads(args.task_config.read_text(encoding="utf-8"))
    report = audit(
        manifest,
        json.loads(args.trigger_dataset.read_text(encoding="utf-8")),
        json.loads(args.oof_report.read_text(encoding="utf-8")),
        config[manifest["case_id"]],
        cell=args.cell,
        attempt_budget=args.attempt_budget,
        top_k=args.top_k,
        rollout_top_k=args.rollout_top_k,
        candidate_budget=args.candidate_budget,
        decision_budget_seconds=args.decision_budget_seconds,
        live_action_reserve_seconds=args.live_action_reserve_seconds,
        max_continuation_steps=args.max_continuation_steps,
        safety_factor=args.safety_factor,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(json_safe(report), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report["summary"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
