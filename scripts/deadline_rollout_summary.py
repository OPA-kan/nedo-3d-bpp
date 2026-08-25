"""Pure summary helpers for deadline-aware rollout audits."""

from __future__ import annotations

from typing import Any


def summarize(roots: list[dict[str, Any]]) -> dict[str, Any]:
    times = [float(root["decision_seconds"]) for root in roots]
    interventions = [
        root for root in roots
        if root["terminal_selected_candidate_id"]
        != root["incumbent_candidate_id"]
    ]
    ordered = sorted(times)
    p95 = None
    if ordered:
        position = (len(ordered) - 1) * 0.95
        lower = int(position)
        upper = min(lower + 1, len(ordered) - 1)
        weight = position - lower
        p95 = ordered[lower] * (1.0 - weight) + ordered[upper] * weight
    return {
        "roots": len(roots),
        "interventions": len(interventions),
        "terminal_action_recall": (
            sum(root["matches_terminal_action"] for root in roots) / len(roots)
            if roots else None
        ),
        "intervention_action_recall": (
            sum(root["matches_terminal_action"] for root in interventions)
            / len(interventions) if interventions else None
        ),
        "terminal_selected_available_recall": (
            sum(root["terminal_selected_available"] for root in roots)
            / len(roots) if roots else None
        ),
        "mean_decision_seconds": sum(times) / len(times) if times else None,
        "p95_decision_seconds": p95,
        "max_decision_seconds": max(times) if times else None,
        "within_10s_rate": (
            sum(value <= 10.0 for value in times) / len(times)
            if times else None
        ),
        "search_deadline_met_rate": (
            sum(root["search"]["deadline_met"] for root in roots) / len(roots)
            if roots else None
        ),
        "depth_counts": {
            str(depth): sum(
                root["search"]["common_total_depth"] == depth for root in roots
            )
            for depth in sorted({
                root["search"]["common_total_depth"] for root in roots
            })
        },
    }
