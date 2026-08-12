"""Evaluate the discovery-selected representation once on a new late split."""

from __future__ import annotations

import argparse
import json
import pathlib
from typing import Any, Callable

try:
    from scripts.evaluate_counterfactual_teacher_baseline import (
        DIRECTIONAL,
        _action_pair,
        _read_jsonl,
    )
    from scripts.evaluate_counterfactual_teacher_discovery import (
        _predict_ridge_fold,
        local_pair_vector,
    )
except ModuleNotFoundError:  # direct `python scripts/...py` execution
    from evaluate_counterfactual_teacher_baseline import (
        DIRECTIONAL,
        _action_pair,
        _read_jsonl,
    )
    from evaluate_counterfactual_teacher_discovery import (
        _predict_ridge_fold,
        local_pair_vector,
    )


EXPECTED_POLICY = {
    "fill_score_proxy": "action_only_ridge",
    "com_z": "candidate_local_state_ridge",
    "surface_total_variation": "candidate_local_state_ridge",
    "placed_count": "abstain_no_directional_discovery_rows",
    "priority_misrouted": "abstain_no_directional_discovery_rows",
    "soft_covered_by_other": "abstain_insufficient_directional_discovery_rows",
}


def _score(
    predictions: dict[str, str], rows: list[dict[str, Any]], metric: str,
) -> dict[str, int]:
    directional = [
        row for row in rows
        if row["labels"][metric]["relation"] in DIRECTIONAL
    ]
    return {
        "correct": sum(
            predictions.get(row["teacher_id"])
            == row["labels"][metric]["relation"]
            for row in directional
        ),
        "total": len(directional),
    }


def evaluate_frozen_policy(
    policy: dict[str, Any], discovery: list[dict[str, Any]],
    late: list[dict[str, Any]],
) -> dict[str, Any]:
    if policy.get("axes") != EXPECTED_POLICY:
        raise ValueError("policy axes do not match the preregistered contract")
    if policy.get("late_holdout_accessed_for_selection") is not False:
        raise ValueError("policy was not selected discovery-only")
    axes = {}
    for metric in ("fill_score_proxy", "com_z", "surface_total_variation"):
        action = _predict_ridge_fold(
            discovery, late, metric, _action_pair
        )
        local = _predict_ridge_fold(
            discovery, late, metric, local_pair_vector
        )
        selected_name = policy["axes"][metric]
        selected = action if selected_name == "action_only_ridge" else local
        axes[metric] = {
            "selected_model": selected_name,
            "selected": _score(selected, late, metric),
            "action_only_ridge": _score(action, late, metric),
            "candidate_local_state_ridge": _score(local, late, metric),
        }
    local_pooled = sum(
        axes[metric]["candidate_local_state_ridge"]["correct"]
        for metric in ("com_z", "surface_total_variation")
    )
    action_pooled = sum(
        axes[metric]["action_only_ridge"]["correct"]
        for metric in ("com_z", "surface_total_variation")
    )
    wins = sum(
        axes[metric]["candidate_local_state_ridge"]["correct"]
        > axes[metric]["action_only_ridge"]["correct"]
        for metric in ("com_z", "surface_total_variation")
    )
    gate = wins >= 1 and local_pooled >= action_pooled
    return {
        "schema_version": 1,
        "protocol": "one_shot_new_late_split_frozen_discovery_policy",
        "discovery_rows": len(discovery),
        "late_rows": len(late),
        "axes": axes,
        "candidate_local_gate": {
            "passed": gate,
            "axes_beating_action_only": wins,
            "candidate_local_pooled_correct": local_pooled,
            "action_only_pooled_correct": action_pooled,
            "decision": (
                "justify_larger_state_model"
                if gate else "do_not_scale_current_state_representation"
            ),
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Frozen counterfactual representation late evaluation",
        "",
        f"Discovery / new late rows: **{report['discovery_rows']} / {report['late_rows']}**",
        "",
        "| Axis | Frozen model | Selected | Action ridge | Candidate-local ridge |",
        "|---|---|---:|---:|---:|",
    ]
    for metric, axis in report["axes"].items():
        value = lambda name: f"{axis[name]['correct']}/{axis[name]['total']}"
        lines.append(
            f"| {metric} | {axis['selected_model']} | {value('selected')} | "
            f"{value('action_only_ridge')} | {value('candidate_local_state_ridge')} |"
        )
    gate = report["candidate_local_gate"]
    lines.extend([
        "",
        f"Candidate-local gate: **{'PASS' if gate['passed'] else 'FAIL'}** "
        f"({gate['decision']}; pooled {gate['candidate_local_pooled_correct']} "
        f"vs action {gate['action_only_pooled_correct']}).",
        "",
    ])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", type=pathlib.Path, required=True)
    parser.add_argument("--discovery", type=pathlib.Path, required=True)
    parser.add_argument("--late", type=pathlib.Path, required=True)
    parser.add_argument("--json-output", type=pathlib.Path, required=True)
    parser.add_argument("--markdown-output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    report = evaluate_frozen_policy(
        json.loads(args.policy.read_text(encoding="utf-8")),
        _read_jsonl(args.discovery),
        _read_jsonl(args.late),
    )
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    args.markdown_output.write_text(render_markdown(report), encoding="utf-8")
    print(args.markdown_output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
