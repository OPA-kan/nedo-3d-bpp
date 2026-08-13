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


def aggregate_fallback_reports(
    policy: dict[str, Any], reports: list[dict[str, Any]],
) -> dict[str, Any]:
    """Apply a frozen multi-run gate to full-coverage fallback reports."""
    target_ids = [str(report["target_run_id"]) for report in reports]
    if len(set(target_ids)) != len(target_ids):
        raise ValueError("target run IDs must be unique")
    gate = policy["fallback_confirmation_gate"]
    forbidden_ids = {
        str(value)
        for value in policy.get("forbidden_confirmation_run_ids", [])
    }
    eligible_policy_status = (
        policy.get("status") == "frozen_awaiting_new_physical_run"
    )
    eligible_targets = not bool(set(target_ids) & forbidden_ids)
    totals = {
        "rows": 0, "afterstate_rows": 0, "correct": 0,
        "action_geometry_correct": 0,
    }
    paired = {"wins": 0, "ties": 0, "losses": 0}
    per_run = []
    for report in reports:
        result = report["consensus_with_action_fallback"]
        comparison = result["paired_vs_action_geometry"]
        for name in totals:
            totals[name] += int(result[name])
        for name in paired:
            paired[name] += int(comparison[name])
        per_run.append({
            "target_run_id": str(report["target_run_id"]),
            "rows": int(result["rows"]),
            "afterstate_rows": int(result["afterstate_rows"]),
            "correct": int(result["correct"]),
            "action_geometry_correct": int(result["action_geometry_correct"]),
            "non_regression": (
                int(result["correct"])
                >= int(result["action_geometry_correct"])
            ),
        })
    paired["exact_two_sided_sign_p"] = _exact_two_sided_sign_p(
        paired["wins"], paired["losses"]
    )
    enough_runs = len(reports) >= int(gate["minimum_target_runs"])
    no_regression = all(row["non_regression"] for row in per_run)
    significant = (
        paired["wins"] > paired["losses"]
        and paired["exact_two_sided_sign_p"]
        < float(gate["maximum_pooled_exact_sign_p"])
    )
    passed = (
        eligible_policy_status
        and eligible_targets
        and enough_runs
        and (
            no_regression
            if gate.get("require_no_target_run_regression", False)
            else True
        )
        and significant
    )
    return {
        "schema_version": 1,
        "policy_status_at_evaluation": policy.get("status"),
        "target_run_ids": target_ids,
        "per_run": per_run,
        **totals,
        "paired_vs_action_geometry": paired,
        "confirmation_gate": gate,
        "gate_checks": {
            "eligible_policy_status": eligible_policy_status,
            "eligible_confirmation_targets": eligible_targets,
            "enough_target_runs": enough_runs,
            "no_target_run_regression": no_regression,
            "pooled_exact_significant_advantage": significant,
        },
        "gate_passed": passed,
    }


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
        action_geometry = predictions["action_geometry"][teacher_id]
        covered = packed == packed_visible
        fallback_prediction = packed if covered else action_geometry
        rows.append({
            "teacher_id": teacher_id,
            "actual": actual,
            "packed": packed,
            "packed_visible": packed_visible,
            "action_geometry": action_geometry,
            "covered": covered,
            "consensus_correct": covered and packed == actual,
            "fallback_prediction": fallback_prediction,
            "fallback_correct": fallback_prediction == actual,
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
    fallback_paired = {"wins": 0, "ties": 0, "losses": 0}
    for row in rows:
        fallback = row["fallback_correct"]
        action = row["action_geometry"] == row["actual"]
        outcome = (
            "wins" if fallback and not action
            else "losses" if action and not fallback
            else "ties"
        )
        fallback_paired[outcome] += 1
    fallback_paired["exact_two_sided_sign_p"] = _exact_two_sided_sign_p(
        fallback_paired["wins"], fallback_paired["losses"]
    )
    fallback_report = {
        "decision": (
            "use packed/packed+visible consensus when they agree; otherwise "
            "use action geometry"
        ),
        "rows": len(rows),
        "afterstate_rows": len(covered),
        "correct": sum(row["fallback_correct"] for row in rows),
        "action_geometry_correct": sum(
            row["action_geometry"] == row["actual"] for row in rows
        ),
        "paired_vs_action_geometry": fallback_paired,
    }
    gate = policy.get("confirmation_gate")
    passed = bool(
        gate is not None
        and coverage >= float(gate["minimum_coverage"])
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
        "consensus_with_action_fallback": fallback_report,
        "confirmation_gate": gate,
        "aggregate_fallback_gate_required": (
            "fallback_confirmation_gate" in policy
        ),
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
        "- Consensus+fallback correct: "
        f"{report['consensus_with_action_fallback']['correct']}/"
        f"{report['consensus_with_action_fallback']['rows']} "
        "(action geometry="
        f"{report['consensus_with_action_fallback']['action_geometry_correct']}/"
        f"{report['consensus_with_action_fallback']['rows']})",
        "- Consensus+fallback vs action W/T/L: "
        f"{report['consensus_with_action_fallback']['paired_vs_action_geometry']['wins']}/"
        f"{report['consensus_with_action_fallback']['paired_vs_action_geometry']['ties']}/"
        f"{report['consensus_with_action_fallback']['paired_vs_action_geometry']['losses']} "
        "(exact two-sided p="
        f"{report['consensus_with_action_fallback']['paired_vs_action_geometry']['exact_two_sided_sign_p']:.4g})",
        (
            "- Preregistered gate: **aggregate evaluation required**"
            if report.get("aggregate_fallback_gate_required")
            else f"- Preregistered gate: **{'PASS' if report['gate_passed'] else 'FAIL'}**"
        ),
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
