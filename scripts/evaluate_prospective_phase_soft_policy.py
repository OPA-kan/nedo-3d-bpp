"""Evaluate the frozen phase-conditioned soft policy on one future H3 run."""

from __future__ import annotations

import argparse
import json
import pathlib
from typing import Any

try:
    from scripts.develop_post_shake_soft_reranker import (
        LABEL_FAMILY, METRIC, _correct, _eligible,
    )
    from scripts.evaluate_counterfactual_afterstate_value import (
        _read_jsonl, predict_ridge_model,
    )
    from scripts.train_phase_conditioned_soft_policy import (
        feature_sets, phase_observables, teacher_signature,
    )
except ModuleNotFoundError:
    from develop_post_shake_soft_reranker import (
        LABEL_FAMILY, METRIC, _correct, _eligible,
    )
    from evaluate_counterfactual_afterstate_value import (
        _read_jsonl, predict_ridge_model,
    )
    from train_phase_conditioned_soft_policy import (
        feature_sets, phase_observables, teacher_signature,
    )


def evaluate(
    policy: dict[str, Any], manifest: dict[str, Any], rows: list[dict[str, Any]],
) -> dict[str, Any]:
    if policy.get("status") != "prospective_evaluation_only":
        raise ValueError("policy is not a prospective phase artifact")
    if policy.get("target") != METRIC or policy.get("label_family") != LABEL_FAMILY:
        raise ValueError("policy target contract mismatch")
    target_run_id = str(manifest["source_run_id"])
    if target_run_id == str(policy["source_run_id"]):
        raise ValueError("prospective evaluation requires a different physical run")
    eligible = _eligible(rows)
    training_signatures = set(policy["training_teacher_signatures"])
    target_signatures = {teacher_signature(row) for row in eligible}
    overlap = training_signatures & target_signatures
    features = feature_sets()
    predictions = {
        name: predict_ridge_model(policy["models"][name], eligible, values)
        for name, values in features.items()
    }
    immediate = {
        row["teacher_id"]: "higher_afterstate_better" for row in eligible
    }
    counts = {
        "immediate_score": _correct(immediate, eligible),
        **{name: _correct(values, eligible) for name, values in predictions.items()},
    }
    selected_name = str(policy["selected_model"])
    selected = counts[selected_name]
    passed = (
        len(eligible) >= 20
        and not overlap
        and all(
            selected > counts[baseline]
            for baseline in (
                "immediate_score", "action_geometry", "pooled_afterstate"
            )
        )
    )
    phase_rows = []
    for row in eligible:
        phase = phase_observables(row["source_state_tensor"])
        phase_rows.append({
            "teacher_id": row["teacher_id"],
            "root_step_telemetry_only": int(row["root_step"]),
            "progress": phase[1],
            "fill": phase[3],
            "actual": row[LABEL_FAMILY][METRIC]["relation"],
            "phase_prediction": predictions[
                "phase_conditioned_soft_topology"
            ][row["teacher_id"]],
        })
    return {
        "schema_version": 1,
        "protocol": "frozen_previous_run_policy_on_whole_future_physical_run",
        "training_run_id": str(policy["source_run_id"]),
        "target_run_id": target_run_id,
        "directional_rows": len(eligible),
        "teacher_signature_overlap": len(overlap),
        "models": {
            name: {"correct": correct, "total": len(eligible)}
            for name, correct in counts.items()
        },
        "selected_model": selected_name,
        "promotion_gate": {
            "passed": passed,
            "decision": (
                "license_live_phase_shadow"
                if passed else "do_not_connect_phase_model_to_live_agent"
            ),
        },
        "phase_rows": phase_rows,
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Prospective phase-conditioned soft policy", "",
        f"Training / target run: **{report['training_run_id']} / "
        f"{report['target_run_id']}**",
        f"Directional rows: **{report['directional_rows']}**; signature overlap: "
        f"**{report['teacher_signature_overlap']}**.", "",
        "| Model | Correct |", "|---|---:|",
    ]
    for name, result in report["models"].items():
        lines.append(f"| {name} | {result['correct']}/{result['total']} |")
    gate = report["promotion_gate"]
    lines.extend([
        "", f"Promotion gate: **{'PASS' if gate['passed'] else 'FAIL'}** "
        f"({gate['decision']}).", "",
    ])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", type=pathlib.Path, required=True)
    parser.add_argument("--teacher-dir", type=pathlib.Path, required=True)
    parser.add_argument("--json-output", type=pathlib.Path, required=True)
    parser.add_argument("--markdown-output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    policy = json.loads(args.policy.read_text(encoding="utf-8"))
    manifest = json.loads(
        (args.teacher_dir / "manifest.json").read_text(encoding="utf-8")
    )
    rows = (
        _read_jsonl(args.teacher_dir / "distributional_discovery.jsonl")
        + _read_jsonl(args.teacher_dir / "distributional_late_holdout.jsonl")
    )
    report = evaluate(policy, manifest, rows)
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    args.markdown_output.write_text(render_markdown(report), encoding="utf-8")
    print(args.markdown_output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
