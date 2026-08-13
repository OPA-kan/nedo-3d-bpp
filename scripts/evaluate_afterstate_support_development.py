"""Evaluate the preregistered support-gated fill policy run-held-out."""

from __future__ import annotations

import argparse
import json
import pathlib
from typing import Any

import numpy as np

try:
    from scripts.evaluate_counterfactual_afterstate_value import (
        _eligible, _features, _predict_ridge, _state_block_delta, load_run,
    )
except ModuleNotFoundError:
    from evaluate_counterfactual_afterstate_value import (
        _eligible, _features, _predict_ridge, _state_block_delta, load_run,
    )


BLOCKS = ("packed", "packed_visible")


def _support_reference(rows: list[dict[str, Any]], block: str):
    values = np.asarray([_state_block_delta(row, block) for row in rows])
    scales = np.std(values, axis=0)
    scales[scales == 0.0] = 1.0
    standardized = values / scales
    distances = np.linalg.norm(
        standardized[:, None] - standardized[None, :], axis=2
    )
    np.fill_diagonal(distances, np.inf)
    return scales, standardized, float(np.quantile(distances.min(axis=1), 0.95))


def evaluate(
    base_runs: list[dict[str, Any]], development_runs: list[dict[str, Any]],
) -> dict[str, Any]:
    base_ids = {run["run_id"] for run in base_runs}
    development_ids = [run["run_id"] for run in development_runs]
    if base_ids & set(development_ids):
        raise ValueError("base and development runs must be disjoint")
    if len(set(development_ids)) != len(development_ids):
        raise ValueError("development run IDs must be unique")
    folds = []
    for target in development_runs:
        train = [
            row
            for run in base_runs + [
                run for run in development_runs if run is not target
            ]
            for row in run["discovery"]
        ]
        eligible_train = _eligible(train, "fill_score_proxy")
        test = _eligible(target["late"], "fill_score_proxy")
        predictions = {
            block: _predict_ridge(
                train, test, "fill_score_proxy",
                lambda row, block=block: _state_block_delta(row, block),
            )
            for block in BLOCKS
        }
        action = _predict_ridge(
            train, test, "fill_score_proxy",
            lambda row: _features(
                row, include_action=True, include_afterstate=False
            ),
        )
        support = {
            block: _support_reference(eligible_train, block)
            for block in BLOCKS
        }
        rows = []
        for row in test:
            teacher_id = row["teacher_id"]
            actual = row["continuation_labels"]["fill_score_proxy"]["relation"]
            distances = {}
            supported = True
            for block, (scales, reference, threshold) in support.items():
                value = np.asarray(_state_block_delta(row, block)) / scales
                distance = float(np.min(np.linalg.norm(reference - value, axis=1)))
                distances[block] = {"distance": distance, "threshold": threshold}
                supported &= distance <= threshold
            agreement = (
                predictions["packed"][teacher_id]
                == predictions["packed_visible"][teacher_id]
            )
            covered = supported and agreement
            predicted = predictions["packed"][teacher_id] if agreement else None
            rows.append({
                "teacher_id": teacher_id,
                "case_id": row.get("case_id"),
                "actual": actual,
                "predicted": predicted,
                "supported": supported,
                "agreement": agreement,
                "covered": covered,
                "correct": covered and predicted == actual,
                "action_geometry": action[teacher_id],
                "afterstate_distance": distances,
            })
        covered = [row for row in rows if row["covered"]]
        folds.append({
            "target_run_id": target["run_id"],
            "training_run_ids": [
                run["run_id"] for run in base_runs + development_runs
                if run is not target
            ],
            "directional_rows": len(rows),
            "covered_rows": len(covered),
            "correct": sum(row["correct"] for row in covered),
            "action_geometry_correct_on_covered": sum(
                row["action_geometry"] == row["actual"] for row in covered
            ),
            "rows": rows,
        })
    total = sum(fold["directional_rows"] for fold in folds)
    covered = sum(fold["covered_rows"] for fold in folds)
    correct = sum(fold["correct"] for fold in folds)
    action = sum(fold["action_geometry_correct_on_covered"] for fold in folds)
    coverage = covered / total if total else 0.0
    passed = coverage >= 0.75 and covered - correct == 0 and correct >= action
    return {
        "schema_version": 1,
        "base_run_ids": [run["run_id"] for run in base_runs],
        "development_run_ids": development_ids,
        "split_contract": "each development stream variant held out in full",
        "total_directional_rows": total,
        "covered_rows": covered,
        "coverage": coverage,
        "correct": correct,
        "errors": covered - correct,
        "action_geometry_correct_on_covered": action,
        "acceptance_gate": {
            "minimum_coverage": 0.75,
            "maximum_errors": 0,
            "no_regression_vs_action_geometry": True,
            "passed": passed,
        },
        "folds": folds,
        "claim": (
            "Development-only run-held-out evaluation after the collection "
            "independence gate. Sealed confirmation runs are not inputs."
        ),
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Afterstate support-gate development evaluation", "",
        f"- Directional rows: {report['total_directional_rows']}",
        f"- Coverage: {report['covered_rows']}/{report['total_directional_rows']} "
        f"({report['coverage']:.1%})",
        f"- Correct/errors: {report['correct']}/{report['errors']}",
        f"- Action geometry on covered rows: "
        f"{report['action_geometry_correct_on_covered']}/{report['covered_rows']}",
        f"- Acceptance gate: **{'PASS' if report['acceptance_gate']['passed'] else 'FAIL'}**",
        "", "| Held-out variant run | Rows | Covered | Correct | Action |",
        "|---|---:|---:|---:|---:|",
    ]
    for fold in report["folds"]:
        lines.append(
            f"| {fold['target_run_id']} | {fold['directional_rows']} | "
            f"{fold['covered_rows']} | {fold['correct']} | "
            f"{fold['action_geometry_correct_on_covered']} |"
        )
    lines.extend(["", f"> {report['claim']}", ""])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-dir", type=pathlib.Path, action="append", required=True)
    parser.add_argument("--development-dir", type=pathlib.Path, action="append", required=True)
    parser.add_argument("--json-output", type=pathlib.Path, required=True)
    parser.add_argument("--markdown-output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    report = evaluate(
        [load_run(path) for path in args.base_dir],
        [load_run(path) for path in args.development_dir],
    )
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    args.markdown_output.write_text(render_markdown(report), encoding="utf-8")
    print(args.markdown_output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
