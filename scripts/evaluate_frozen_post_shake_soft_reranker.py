"""Evaluate a discovery-frozen post-shake soft model once on late roots."""

from __future__ import annotations

import argparse
import json
import pathlib
from typing import Any

try:
    from scripts.develop_post_shake_soft_reranker import (
        DIRECTIONAL, LABEL_FAMILY, METRIC, feature_sets,
    )
    from scripts.evaluate_counterfactual_afterstate_value import (
        _predict_ridge, _read_jsonl, predict_ridge_model,
    )
except ModuleNotFoundError:
    from develop_post_shake_soft_reranker import (
        DIRECTIONAL, LABEL_FAMILY, METRIC, feature_sets,
    )
    from evaluate_counterfactual_afterstate_value import (
        _predict_ridge, _read_jsonl, predict_ridge_model,
    )


def _score(predictions: dict[str, str], rows: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "correct": sum(
            predictions.get(row["teacher_id"])
            == row[LABEL_FAMILY][METRIC]["relation"]
            for row in rows
        ),
        "total": len(rows),
    }


def evaluate(policy: dict[str, Any], discovery: list[dict[str, Any]], late: list[dict[str, Any]]) -> dict[str, Any]:
    if policy.get("status") != "late_evaluation_licensed":
        raise ValueError("discovery promotion gate did not license late evaluation")
    if policy.get("late_holdout_accessed_for_selection") is not False:
        raise ValueError("policy was not selected discovery-only")
    if policy.get("target") != METRIC or policy.get("label_family") != LABEL_FAMILY:
        raise ValueError("policy target contract mismatch")
    eligible_discovery = [
        row for row in discovery
        if row.get(LABEL_FAMILY, {}).get(METRIC, {}).get("relation") in DIRECTIONAL
    ]
    eligible_late = [
        row for row in late
        if row.get(LABEL_FAMILY, {}).get(METRIC, {}).get("relation") in DIRECTIONAL
    ]
    features = feature_sets()
    selected_name = policy["selected_model"]
    selected = predict_ridge_model(policy["model"], eligible_late, features[selected_name])
    action = _predict_ridge(
        eligible_discovery, eligible_late, METRIC, features["action_geometry"],
        label_family=LABEL_FAMILY,
    )
    immediate = {row["teacher_id"]: "higher_afterstate_better" for row in eligible_late}
    scores = {
        "selected": _score(selected, eligible_late),
        "action_geometry": _score(action, eligible_late),
        "immediate_score": _score(immediate, eligible_late),
    }
    passed = (
        bool(eligible_late)
        and scores["selected"]["correct"] > scores["action_geometry"]["correct"]
        and scores["selected"]["correct"] > scores["immediate_score"]["correct"]
    )
    return {
        "schema_version": 1,
        "protocol": "one_shot_frozen_discovery_model_on_late_roots",
        "target": METRIC,
        "selected_model": selected_name,
        "directional_late_rows": len(eligible_late),
        "scores": scores,
        "live_shadow_gate": {
            "passed": passed,
            "decision": (
                "build_live_pybullet_afterstate_shadow_reranker"
                if passed else "do_not_connect_model_to_live_agent"
            ),
            "contract": "selected strictly beats both action geometry and immediate score",
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    if report.get("status") == "skipped_discovery_gate_failed":
        return "\n".join([
            "# Frozen post-shake soft reranker: late gate", "",
            "Late roots were not read because the discovery promotion gate failed.", "",
        ])
    lines = [
        "# Frozen post-shake soft reranker: late gate", "",
        f"Directional late rows: **{report['directional_late_rows']}**", "",
        "| Model | Correct |", "|---|---:|",
    ]
    for name, result in report["scores"].items():
        lines.append(f"| {name} | {result['correct']}/{result['total']} |")
    gate = report["live_shadow_gate"]
    lines.extend(["", f"Live-shadow gate: **{'PASS' if gate['passed'] else 'FAIL'}** ({gate['decision']}).", ""])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", type=pathlib.Path, required=True)
    parser.add_argument("--discovery", type=pathlib.Path, required=True)
    parser.add_argument("--late", type=pathlib.Path, required=True)
    parser.add_argument("--json-output", type=pathlib.Path, required=True)
    parser.add_argument("--markdown-output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    policy = json.loads(args.policy.read_text(encoding="utf-8"))
    if policy.get("status") != "late_evaluation_licensed":
        # Preserve the sealed split when discovery has not licensed opening it.
        report = {
            "schema_version": 1,
            "status": "skipped_discovery_gate_failed",
            "target": METRIC,
            "late_holdout_read": False,
        }
    else:
        report = evaluate(
            policy, _read_jsonl(args.discovery), _read_jsonl(args.late),
        )
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    args.markdown_output.write_text(render_markdown(report), encoding="utf-8")
    print(args.markdown_output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
