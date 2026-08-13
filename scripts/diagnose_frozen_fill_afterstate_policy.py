"""Diagnose fixed-policy fill errors without training on evaluation runs."""

from __future__ import annotations

import argparse
import json
import pathlib
from typing import Any

import numpy as np

try:
    from scripts.evaluate_counterfactual_afterstate_value import (
        _eligible,
        _state_block_delta,
        load_run,
    )
except ModuleNotFoundError:  # direct script execution
    from evaluate_counterfactual_afterstate_value import (
        _eligible,
        _state_block_delta,
        load_run,
    )


BLOCKS = ("packed", "packed_visible")


def _distance_context(
    training_rows: list[dict[str, Any]], target_rows: list[dict[str, Any]],
    block: str,
) -> dict[str, Any]:
    training = np.asarray([
        _state_block_delta(row, block) for row in training_rows
    ], dtype=float)
    scales = np.std(training, axis=0)
    scales[scales == 0.0] = 1.0
    standardized = training / scales
    pairwise = np.linalg.norm(
        standardized[:, None, :] - standardized[None, :, :], axis=2
    )
    np.fill_diagonal(pairwise, np.inf)
    leave_one_out = np.min(pairwise, axis=1)
    targets = np.asarray([
        _state_block_delta(row, block) for row in target_rows
    ], dtype=float) / scales
    return {
        "training_leave_one_out": leave_one_out,
        "target_nearest": np.min(
            np.linalg.norm(
                targets[:, None, :] - standardized[None, :, :], axis=2
            ),
            axis=1,
        ),
    }


def diagnose(
    training_runs: list[dict[str, Any]], target: dict[str, Any],
    evaluation: dict[str, Any],
) -> dict[str, Any]:
    training_ids = [run["run_id"] for run in training_runs]
    if target["run_id"] in training_ids:
        raise ValueError("target run must not occur in training runs")
    if evaluation["target_run_id"] != target["run_id"]:
        raise ValueError("evaluation and target run do not match")
    training = _eligible([
        row for run in training_runs for row in run["discovery"]
    ], "fill_score_proxy")
    target_rows = _eligible(target["late"], "fill_score_proxy")
    by_id = {row["teacher_id"]: row for row in target_rows}
    evaluation_by_id = {row["teacher_id"]: row for row in evaluation["rows"]}
    if set(by_id) != set(evaluation_by_id):
        raise ValueError("evaluation rows do not match target directional rows")
    distances = {
        block: _distance_context(training, target_rows, block)
        for block in BLOCKS
    }
    rows = []
    for index, row in enumerate(target_rows):
        result = evaluation_by_id[row["teacher_id"]]
        block_diagnostics = {}
        outside_blocks = []
        low_density_blocks = []
        for block in BLOCKS:
            reference = distances[block]["training_leave_one_out"]
            nearest = float(distances[block]["target_nearest"][index])
            maximum = float(np.max(reference))
            p95 = float(np.quantile(reference, 0.95))
            outside = nearest > maximum
            if outside:
                outside_blocks.append(block)
            if nearest > p95:
                low_density_blocks.append(block)
            block_diagnostics[block] = {
                "standardized_nearest_training_distance": nearest,
                "training_leave_one_out_median": float(np.median(reference)),
                "training_leave_one_out_p95": p95,
                "training_leave_one_out_maximum": maximum,
                "outside_training_envelope": outside,
            }
        label = row["continuation_labels"]["fill_score_proxy"]
        support_known = all(
            name in label for name in (
                "lower_continuation_values", "higher_continuation_values"
            )
        )
        alternatives = {
            "lower": len(label["lower_continuation_values"])
            if support_known else None,
            "higher": len(label["higher_continuation_values"])
            if support_known else None,
        }
        if result["consensus_correct"]:
            classification = "correct"
        elif len(outside_blocks) == len(BLOCKS):
            classification = "afterstate_extrapolation"
        elif len(low_density_blocks) == len(BLOCKS):
            classification = "low_density_afterstate"
        elif support_known and min(alternatives.values()) <= 1:
            classification = "bounded_teacher_support"
        else:
            classification = "in_envelope_model_error"
        exact_scenario_rows = sum(
            candidate.get("scenario_axes") == row.get("scenario_axes")
            for candidate in training
        )
        rows.append({
            "teacher_id": row["teacher_id"],
            "case_id": row.get("case_id"),
            "root_step": row.get("root_step"),
            "actual": result["actual"],
            "consensus_correct": result["consensus_correct"],
            "classification": classification,
            "exact_scenario_training_rows": exact_scenario_rows,
            "continuation_alternatives": alternatives,
            "continuation_value_gap": abs(
                float(label["lower_best_continuation"])
                - float(label["higher_best_continuation"])
            ) if all(
                name in label for name in (
                    "lower_best_continuation",
                    "higher_best_continuation",
                )
            ) else None,
            "afterstate_distance": block_diagnostics,
        })
    errors = [row for row in rows if not row["consensus_correct"]]
    support_covered = [
        row for row in rows
        if all(
            row["afterstate_distance"][block]
            ["standardized_nearest_training_distance"]
            <= row["afterstate_distance"][block]
            ["training_leave_one_out_p95"]
            for block in BLOCKS
        )
    ]
    counts = {
        name: sum(row["classification"] == name for row in errors)
        for name in (
            "afterstate_extrapolation",
            "low_density_afterstate",
            "bounded_teacher_support",
            "in_envelope_model_error",
        )
    }
    return {
        "schema_version": 1,
        "training_run_ids": training_ids,
        "target_run_id": target["run_id"],
        "training_split": "discovery only",
        "target_split": "complete late_holdout",
        "evaluation_rows_are_training_data": False,
        "directional_rows": len(rows),
        "errors": len(errors),
        "error_classification_counts": counts,
        "posthoc_training_support_gate": {
            "contract": (
                "cover only when both fixed feature blocks are no farther "
                "than their training-only leave-one-out p95"
            ),
            "covered": len(support_covered),
            "total": len(rows),
            "coverage": len(support_covered) / len(rows) if rows else 0.0,
            "correct": sum(
                row["consensus_correct"] for row in support_covered
            ),
            "passes_original_minimum_coverage": (
                len(support_covered) / len(rows) >= 0.75 if rows else False
            ),
            "status": "diagnostic_only_not_preregistered",
        },
        "rows": rows,
        "next_experiment": (
            "Increase independent mid/late roots within the existing scenario "
            "matrix and preregister an afterstate-support gate. Do not train "
            "on either confirmation run or increase H3 depth yet."
            if counts["afterstate_extrapolation"] or counts["low_density_afterstate"]
            else "Keep the failed runs sealed and target the dominant class."
        ),
        "claim": (
            "Post-failure diagnosis, not confirmation evidence. Distances use "
            "only the original discovery training rows."
        ),
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Frozen fill-afterstate failure diagnosis", "",
        f"- Target physical run: {report['target_run_id']}",
        f"- Directional rows/errors: {report['directional_rows']}/{report['errors']}",
        "- Error classes: " + ", ".join(
            f"{name}={value}"
            for name, value in report["error_classification_counts"].items()
        ),
        "- Posthoc support gate: "
        f"{report['posthoc_training_support_gate']['correct']}/"
        f"{report['posthoc_training_support_gate']['covered']} correct at "
        f"{report['posthoc_training_support_gate']['coverage']:.1%} coverage; "
        f"original 75% coverage gate="
        f"{'PASS' if report['posthoc_training_support_gate']['passes_original_minimum_coverage'] else 'FAIL'}",
        "",
        "| Row | Case | Result | Class | Packed distance/p95/max | "
        "Packed+visible distance/p95/max | Exact-scenario train rows |",
        "|---|---|---|---|---:|---:|---:|",
    ]
    for row in report["rows"]:
        packed = row["afterstate_distance"]["packed"]
        visible = row["afterstate_distance"]["packed_visible"]
        lines.append(
            f"| {row['teacher_id']} | {row['case_id']} | "
            f"{'correct' if row['consensus_correct'] else 'error'} | "
            f"{row['classification']} | "
            f"{packed['standardized_nearest_training_distance']:.3f}/"
            f"{packed['training_leave_one_out_p95']:.3f}/"
            f"{packed['training_leave_one_out_maximum']:.3f} | "
            f"{visible['standardized_nearest_training_distance']:.3f}/"
            f"{visible['training_leave_one_out_p95']:.3f}/"
            f"{visible['training_leave_one_out_maximum']:.3f} | "
            f"{row['exact_scenario_training_rows']} |"
        )
    lines.extend([
        "", f"Next experiment: {report['next_experiment']}",
        "", f"> {report['claim']}", "",
    ])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--training-dir", type=pathlib.Path, action="append", required=True)
    parser.add_argument("--target-dir", type=pathlib.Path, required=True)
    parser.add_argument("--evaluation", type=pathlib.Path, required=True)
    parser.add_argument("--json-output", type=pathlib.Path, required=True)
    parser.add_argument("--markdown-output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    report = diagnose(
        [load_run(path) for path in args.training_dir], load_run(args.target_dir),
        json.loads(args.evaluation.read_text(encoding="utf-8")),
    )
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    args.markdown_output.write_text(render_markdown(report), encoding="utf-8")
    print(args.markdown_output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
