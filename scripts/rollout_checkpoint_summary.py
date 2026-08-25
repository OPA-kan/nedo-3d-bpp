"""Pure aggregation helpers for bounded rollout checkpoint audits."""

from __future__ import annotations

from typing import Any


def summarize_roots(
    roots: list[dict[str, Any]], caps: list[int]
) -> dict[str, dict[str, Any]]:
    """Summarize checkpoint recall and latency without simulator imports."""
    summary: dict[str, dict[str, Any]] = {}
    interventions = sum(
        row["terminal_selected_candidate_id"]
        != row["incumbent_candidate_id"]
        for row in roots
    )
    for cap in caps:
        key = str(cap)
        eligible = [row for row in roots if key in row["checkpoints"]]
        decision_seconds = [
            float(row["checkpoints"][key]["estimated_decision_seconds"])
            for row in eligible
        ]
        matches = sum(
            row["checkpoints"][key]["selected_candidate_id"]
            == row["terminal_selected_candidate_id"]
            for row in eligible
        )
        recovered = sum(
            row["terminal_selected_candidate_id"]
            != row["incumbent_candidate_id"]
            and row["checkpoints"][key]["selected_candidate_id"]
            == row["terminal_selected_candidate_id"]
            for row in eligible
        )
        ordered = sorted(decision_seconds)
        p95 = None
        if ordered:
            position = (len(ordered) - 1) * 0.95
            lower = int(position)
            upper = min(lower + 1, len(ordered) - 1)
            weight = position - lower
            p95 = ordered[lower] * (1.0 - weight) + ordered[upper] * weight
        summary[key] = {
            "continuation_cap": cap,
            "total_depth": cap + 1,
            "roots": len(eligible),
            "terminal_action_recall": matches / len(eligible) if eligible else None,
            "intervention_action_recall": (
                recovered / interventions if interventions else None
            ),
            "mean_decision_seconds": (
                sum(decision_seconds) / len(decision_seconds)
                if decision_seconds else None
            ),
            "p95_decision_seconds": p95,
            "within_10s_rate": (
                sum(value <= 10.0 for value in decision_seconds)
                / len(decision_seconds)
                if decision_seconds else None
            ),
        }
    return summary
