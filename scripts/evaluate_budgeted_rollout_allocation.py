"""Join OOF candidate allocation with bounded physical checkpoints.

This is an offline, group-excluded allocation audit.  The learned allocator
only chooses which root candidates receive physical continuation.  Achieved
checkpoint vectors still decide the action, and frozen genuine-terminal
rollouts remain the reference label.  No learned value is used.
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

from scripts.build_terminal_rollout_trigger_dataset import pareto_ids


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def allocated_candidates(
    oof_row: dict[str, Any], *, budget: int
) -> list[str]:
    """Keep the incumbent and add the highest-OOF-score alternatives."""
    candidate_ids = [str(value) for value in oof_row["candidate_ids"]]
    scores = [float(value) for value in oof_row["candidate_scores"]]
    if len(candidate_ids) != len(scores):
        raise ValueError("candidate ids and scores differ in length")
    incumbent_index = int(oof_row["incumbent_index"])
    incumbent = candidate_ids[incumbent_index]
    alternatives = sorted(
        (
            index for index in range(len(candidate_ids))
            if index != incumbent_index
        ),
        key=lambda index: (-scores[index], index),
    )
    chosen = {incumbent}
    chosen.update(
        candidate_ids[index] for index in alternatives[: max(0, budget - 1)]
    )
    return [candidate for candidate in candidate_ids if candidate in chosen]


def evaluate(
    checkpoint_report: dict[str, Any], oof_report: dict[str, Any],
    *, budgets: list[int], caps: list[int] | None = None,
    time_limit_seconds: float = 10.0, max_total_depth: int = 3,
) -> dict[str, Any]:
    roots = list(checkpoint_report.get("root_rows") or [])
    checkpoint_by_root = {str(root["root_id"]): root for root in roots}
    oof_rows = {
        str(row["root_id"]): row
        for row in (oof_report.get("candidate_allocator") or {}).get(
            "oof_rows", []
        )
    }
    missing = sorted(
        str(root["root_id"]) for root in roots
        if str(root["root_id"]) not in oof_rows
    )
    if missing:
        raise ValueError(f"missing OOF allocator rows: {missing[:3]}")
    if caps is None:
        caps = [int(value) for value in checkpoint_report["continuation_caps"]]
    interventions = sum(
        root["terminal_selected_candidate_id"]
        != root["incumbent_candidate_id"]
        for root in roots
    )
    points = []
    audit_rows = []
    for cap in caps:
        key = str(cap)
        for budget in budgets:
            matches = 0
            recovered = 0
            selected_available = 0
            times: list[float] = []
            branch_fractions: list[float] = []
            for root in roots:
                checkpoint = root["checkpoints"][key]
                oof_row = oof_rows[str(root["root_id"])]
                chosen = allocated_candidates(oof_row, budget=budget)
                chosen_set = set(chosen)
                candidates = [
                    row for row in checkpoint["candidates"]
                    if str(row["root_candidate_id"]) in chosen_set
                ]
                available = {str(row["root_candidate_id"]) for row in candidates}
                if set(chosen) != available:
                    raise ValueError(
                        f"{root['root_id']}: OOF/checkpoint candidate mismatch"
                    )
                frontier = pareto_ids(candidates, "checkpoint_vector")
                incumbent = str(root["incumbent_candidate_id"])
                selected = (
                    incumbent if incumbent in frontier else
                    next((candidate for candidate in chosen if candidate in frontier), incumbent)
                )
                terminal_selected = str(root["terminal_selected_candidate_id"])
                is_intervention = terminal_selected != incumbent
                matches += int(selected == terminal_selected)
                recovered += int(is_intervention and selected == terminal_selected)
                selected_available += int(terminal_selected in chosen_set)

                total_work = max(
                    1, sum(int(row["physical_step_equivalents"])
                           for row in checkpoint["candidates"])
                )
                chosen_work = sum(
                    int(row["physical_step_equivalents"]) for row in candidates
                )
                fraction = chosen_work / total_work
                branch_fractions.append(fraction)
                search_seconds = float(checkpoint["search_seconds"])
                non_search_seconds = max(
                    0.0,
                    float(checkpoint["estimated_decision_seconds"])
                    - search_seconds,
                )
                estimated_seconds = non_search_seconds + search_seconds * fraction
                times.append(estimated_seconds)
                audit_rows.append({
                    "root_id": root["root_id"],
                    "continuation_cap": cap,
                    "total_depth": cap + 1,
                    "candidate_budget": budget,
                    "allocated_candidates": chosen,
                    "frontier_candidates": frontier,
                    "selected_candidate_id": selected,
                    "terminal_selected_candidate_id": terminal_selected,
                    "matches_terminal_action": selected == terminal_selected,
                    "terminal_selected_available": terminal_selected in chosen_set,
                    "estimated_decision_seconds": estimated_seconds,
                    "physical_work_fraction": fraction,
                })
            points.append({
                "continuation_cap": cap,
                "total_depth": cap + 1,
                "candidate_budget": budget,
                "roots": len(roots),
                "terminal_selected_available_recall": (
                    selected_available / len(roots) if roots else None
                ),
                "terminal_action_recall": matches / len(roots) if roots else None,
                "intervention_action_recall": (
                    recovered / interventions if interventions else None
                ),
                "mean_physical_work_fraction": (
                    sum(branch_fractions) / len(branch_fractions)
                    if branch_fractions else None
                ),
                "estimated_mean_seconds": (
                    sum(times) / len(times) if times else None
                ),
                "estimated_p95_seconds": _percentile(times, 0.95),
                "estimated_max_seconds": max(times) if times else None,
                "estimated_within_10s_rate": (
                    sum(value <= 10.0 for value in times) / len(times)
                    if times else None
                ),
            })
    adaptive_points = []
    for budget in budgets:
        grouped: dict[str, list[dict[str, Any]]] = {}
        for row in audit_rows:
            if (
                row["candidate_budget"] == budget
                and row["total_depth"] <= max_total_depth
            ):
                grouped.setdefault(str(row["root_id"]), []).append(row)
        chosen_rows = []
        for root in roots:
            options = grouped[str(root["root_id"])]
            within = [
                row for row in options
                if row["estimated_decision_seconds"] <= time_limit_seconds
            ]
            chosen_rows.append(max(
                within or options,
                key=lambda row: (
                    row["total_depth"] if within else -row["total_depth"]
                ),
            ))
        times = [row["estimated_decision_seconds"] for row in chosen_rows]
        intervention_rows = [
            row for row in chosen_rows
            if row["terminal_selected_candidate_id"]
            != checkpoint_by_root[str(row["root_id"])]["incumbent_candidate_id"]
        ] if roots else []
        adaptive_points.append({
            "candidate_budget": budget,
            "max_total_depth": max_total_depth,
            "time_limit_seconds": time_limit_seconds,
            "roots": len(chosen_rows),
            "terminal_action_recall": (
                sum(row["matches_terminal_action"] for row in chosen_rows)
                / len(chosen_rows) if chosen_rows else None
            ),
            "intervention_action_recall": (
                sum(row["matches_terminal_action"] for row in intervention_rows)
                / len(intervention_rows) if intervention_rows else None
            ),
            "estimated_mean_seconds": (
                sum(times) / len(times) if times else None
            ),
            "estimated_p95_seconds": _percentile(times, 0.95),
            "estimated_max_seconds": max(times) if times else None,
            "estimated_within_budget_rate": (
                sum(value <= time_limit_seconds for value in times) / len(times)
                if times else None
            ),
            "depth_counts": {
                str(depth): sum(row["total_depth"] == depth for row in chosen_rows)
                for depth in sorted({row["total_depth"] for row in chosen_rows})
            },
        })
    return {
        "contract": "budgeted_physical_rollout_allocation_audit_v1",
        "checkpoint_contract": checkpoint_report.get("contract"),
        "allocator_contract": (
            oof_report.get("candidate_allocator") or {}
        ).get("contract"),
        "roots": len(roots),
        "interventions": interventions,
        "value_model": None,
        "latency_semantics": "proportional_to_physical_step_equivalents",
        "points": points,
        "adaptive_points": adaptive_points,
        "audit_rows": audit_rows,
    }


def markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Budgeted physical rollout allocation audit",
        "",
        f"- hard roots: {report['roots']}",
        f"- terminal interventions: {report['interventions']}",
        "- learned value used: no",
        "- candidate selection: group-OOF allocator",
        "",
        "| depth | candidates | terminal available | action recall | "
        "intervention recall | mean seconds | p95 seconds | <=10s |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for point in report["points"]:
        lines.append(
            f"| H{point['total_depth']} | {point['candidate_budget']} | "
            f"{point['terminal_selected_available_recall']:.3f} | "
            f"{point['terminal_action_recall']:.3f} | "
            f"{point['intervention_action_recall']:.3f} | "
            f"{point['estimated_mean_seconds']:.2f} | "
            f"{point['estimated_p95_seconds']:.2f} | "
            f"{point['estimated_within_10s_rate']:.3f} |"
        )
    lines.extend([
        "",
        "> Time is an offline estimate: measured checkpoint search time is "
        "scaled by retained physical-step equivalents; fixed non-search time "
        "is preserved.",
        "",
        "## Adaptive time budget",
        "",
        "| candidates | max depth | action recall | intervention recall | "
        "mean seconds | p95 seconds | max seconds | within budget |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|",
    ])
    for point in report["adaptive_points"]:
        lines.append(
            f"| {point['candidate_budget']} | H{point['max_total_depth']} | "
            f"{point['terminal_action_recall']:.3f} | "
            f"{point['intervention_action_recall']:.3f} | "
            f"{point['estimated_mean_seconds']:.2f} | "
            f"{point['estimated_p95_seconds']:.2f} | "
            f"{point['estimated_max_seconds']:.2f} | "
            f"{point['estimated_within_budget_rate']:.3f} |"
        )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoints", type=pathlib.Path, required=True)
    parser.add_argument("--oof-report", type=pathlib.Path, required=True)
    parser.add_argument("--candidate-budgets", type=int, nargs="+", default=[1, 2, 3])
    parser.add_argument("--continuation-caps", type=int, nargs="+")
    parser.add_argument("--time-limit-seconds", type=float, default=10.0)
    parser.add_argument("--max-total-depth", type=int, default=3)
    parser.add_argument("--json-output", type=pathlib.Path, required=True)
    parser.add_argument("--markdown-output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    report = evaluate(
        json.loads(args.checkpoints.read_text(encoding="utf-8")),
        json.loads(args.oof_report.read_text(encoding="utf-8")),
        budgets=args.candidate_budgets,
        caps=args.continuation_caps,
        time_limit_seconds=args.time_limit_seconds,
        max_total_depth=args.max_total_depth,
    )
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    args.markdown_output.write_text(markdown(report), encoding="utf-8")
    print(args.markdown_output.read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
