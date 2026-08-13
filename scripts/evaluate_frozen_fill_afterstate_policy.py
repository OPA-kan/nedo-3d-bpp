"""Evaluate the frozen fill-only afterstate consensus on one new physical run."""

from __future__ import annotations

import argparse
import json
import pathlib
from typing import Any

try:
    from scripts.evaluate_counterfactual_afterstate_value import (
        LABEL_FAMILIES,
        _eligible,
        _exact_two_sided_sign_p,
        _features,
        _predict_ridge,
        _state_block_delta,
        load_run,
    )
except ModuleNotFoundError:
    from evaluate_counterfactual_afterstate_value import (
        LABEL_FAMILIES,
        _eligible,
        _exact_two_sided_sign_p,
        _features,
        _predict_ridge,
        _state_block_delta,
        load_run,
    )


def evaluate_frozen(
    policy: dict[str, Any], training_runs: list[dict[str, Any]],
    target: dict[str, Any], *, label_family: str = "continuation_labels",
) -> dict[str, Any]:
    if policy["status"] not in (
        "frozen_awaiting_new_physical_run",
        "confirmed_once_offline_not_live_ready",
        "replication_failed_not_shadow_ready",
    ):
        raise ValueError("policy was not frozen for confirmation")
    training_ids = [run["run_id"] for run in training_runs]
    if target["run_id"] in training_ids:
        raise ValueError("target run must not occur in training runs")
    train = [row for run in training_runs for row in run["discovery"]]
    test = _eligible(
        target["late"], "fill_score_proxy", label_family=label_family
    )
    predictions = {
        "packed": _predict_ridge(
            train, test, "fill_score_proxy",
            lambda row: _state_block_delta(row, "packed"),
            label_family=label_family,
        ),
        "packed_visible": _predict_ridge(
            train, test, "fill_score_proxy",
            lambda row: _state_block_delta(row, "packed_visible"),
            label_family=label_family,
        ),
        "action_geometry": _predict_ridge(
            train, test, "fill_score_proxy",
            lambda row: _features(
                row, include_action=True, include_afterstate=False
            ),
            label_family=label_family,
        ),
    }
    rows = []
    for row in test:
        teacher_id = row["teacher_id"]
        actual = row[label_family]["fill_score_proxy"]["relation"]
        packed = predictions["packed"][teacher_id]
        packed_visible = predictions["packed_visible"][teacher_id]
        rows.append({
            "teacher_id": teacher_id,
            "actual": actual,
            "packed": packed,
            "packed_visible": packed_visible,
            "action_geometry": predictions["action_geometry"][teacher_id],
            "covered": packed == packed_visible,
            "consensus_correct": packed == packed_visible and packed == actual,
        })
    covered = [row for row in rows if row["covered"]]
    coverage = len(covered) / len(rows) if rows else 0.0
    correct = sum(row["consensus_correct"] for row in covered)
    baselines = {
        name: sum(row[name] == row["actual"] for row in covered)
        for name in ("packed", "packed_visible", "action_geometry")
    }
    paired_vs_action = {"wins": 0, "ties": 0, "losses": 0}
    for row in covered:
        consensus = row["consensus_correct"]
        action = row["action_geometry"] == row["actual"]
        outcome = (
            "wins" if consensus and not action
            else "losses" if action and not consensus
            else "ties"
        )
        paired_vs_action[outcome] += 1
    paired_vs_action["exact_two_sided_sign_p"] = _exact_two_sided_sign_p(
        paired_vs_action["wins"], paired_vs_action["losses"]
    )
    gate = policy["confirmation_gate"]
    passed = (
        coverage >= float(gate["minimum_coverage"])
        and len(covered) - correct <= int(gate["maximum_errors"])
        and all(correct >= value for value in baselines.values())
    )
    return {
        "schema_version": 1,
        "label_family": label_family,
        "policy_status_at_evaluation": policy["status"],
        "training_run_ids": training_ids,
        "target_run_id": target["run_id"],
        "target_split": "complete late_holdout",
        "fill_directional_rows": len(rows),
        "covered_rows": len(covered),
        "coverage": coverage,
        "consensus_correct": correct,
        "consensus_errors": len(covered) - correct,
        "covered_row_baseline_correct": baselines,
        "paired_consensus_vs_action_geometry": paired_vs_action,
        "confirmation_gate": gate,
        "gate_passed": passed,
        "rows": rows,
        "claim": (
            "A fixed-policy synthetic physical evaluation. Each run must pass "
            "its preregistered gate; pooled accuracy does not override a "
            "failed replication or license live selection."
        ),
    }


def render_markdown(report: dict[str, Any]) -> str:
    return "\n".join([
        "# Frozen fill-afterstate policy confirmation", "",
        f"- Target physical run: {report['target_run_id']}",
        f"- Fill directional late rows: {report['fill_directional_rows']}",
        f"- Coverage: {report['covered_rows']}/{report['fill_directional_rows']} "
        f"({report['coverage']:.1%})",
        f"- Consensus correct/errors: {report['consensus_correct']}/"
        f"{report['consensus_errors']}",
        "- Covered-row baselines: "
        + ", ".join(
            f"{name}={value}/{report['covered_rows']}"
            for name, value in report["covered_row_baseline_correct"].items()
        ),
        "- Consensus vs action geometry W/T/L: "
        f"{report['paired_consensus_vs_action_geometry']['wins']}/"
        f"{report['paired_consensus_vs_action_geometry']['ties']}/"
        f"{report['paired_consensus_vs_action_geometry']['losses']} "
        "(exact two-sided p="
        f"{report['paired_consensus_vs_action_geometry']['exact_two_sided_sign_p']:.4g})",
        f"- Preregistered gate: **{'PASS' if report['gate_passed'] else 'FAIL'}**",
        "", f"> {report['claim']}", "",
    ])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", type=pathlib.Path, required=True)
    parser.add_argument("--training-dir", type=pathlib.Path, action="append", required=True)
    parser.add_argument("--target-dir", type=pathlib.Path, required=True)
    parser.add_argument("--json-output", type=pathlib.Path, required=True)
    parser.add_argument("--markdown-output", type=pathlib.Path, required=True)
    parser.add_argument(
        "--label-family", choices=LABEL_FAMILIES,
        default="continuation_labels",
    )
    args = parser.parse_args()
    policy = json.loads(args.policy.read_text(encoding="utf-8"))
    report = evaluate_frozen(
        policy, [
            load_run(path, label_family=args.label_family)
            for path in args.training_dir
        ],
        load_run(args.target_dir, label_family=args.label_family),
        label_family=args.label_family,
    )
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    args.markdown_output.write_text(render_markdown(report), encoding="utf-8")
    print(args.markdown_output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
