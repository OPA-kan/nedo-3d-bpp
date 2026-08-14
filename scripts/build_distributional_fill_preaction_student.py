"""Fit and audit a source-state-conditioned pre-action fill value model."""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import pathlib
from typing import Any

import numpy as np

try:
    from scripts.evaluate_counterfactual_afterstate_value import (
        _eligible,
        _exact_two_sided_sign_p,
        _set_summary,
        _state_block_delta,
        load_run,
    )
except ModuleNotFoundError:
    from evaluate_counterfactual_afterstate_value import (
        _eligible,
        _exact_two_sided_sign_p,
        _set_summary,
        _state_block_delta,
        load_run,
    )


LABEL_FAMILY = "distributional_continuation_labels"
METRIC = "fill_score_proxy"
BLOCKS = ("packed", "packed_visible")
PAIRWISE_L2_GRID = (0.1, 1.0, 10.0, 100.0, 1000.0)


def _action_delta(row: dict[str, Any]) -> list[float]:
    names = row["lower_action_tensor"]["feature_names"]
    if names != row["higher_action_tensor"]["feature_names"]:
        raise ValueError("candidate action feature names do not match")
    return [
        float(row["higher_action_tensor"]["values"][index])
        - float(row["lower_action_tensor"]["values"][index])
        for index, name in enumerate(names)
        if name != "immediate_score"
    ]


def _preaction_signature(row: dict[str, Any]) -> str:
    payload = json.dumps(
        [_set_summary(row["source_state_tensor"]), _action_delta(row)],
        separators=(",", ":"), allow_nan=False,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def _pairwise_design(
    rows: list[dict[str, Any]], *,
    source_means: np.ndarray, source_scales: np.ndarray,
    action_scales: np.ndarray,
) -> np.ndarray:
    output = []
    for row in rows:
        source = (
            np.asarray(_set_summary(row["source_state_tensor"]), dtype=float)
            - source_means
        ) / source_scales
        action = np.asarray(_action_delta(row), dtype=float) / action_scales
        output.append(np.concatenate([action, np.outer(source, action).ravel()]))
    return np.asarray(output, dtype=float)


def _fit_pairwise(rows: list[dict[str, Any]], l2: float) -> dict[str, Any]:
    if not rows:
        raise ValueError("pairwise training requires directional rows")
    sources = np.asarray([
        _set_summary(row["source_state_tensor"]) for row in rows
    ], dtype=float)
    actions = np.asarray([_action_delta(row) for row in rows], dtype=float)
    source_means = np.mean(sources, axis=0)
    source_scales = np.std(sources, axis=0)
    source_scales[source_scales == 0.0] = 1.0
    action_scales = np.sqrt(np.mean(np.square(actions), axis=0))
    action_scales[action_scales == 0.0] = 1.0
    design = _pairwise_design(
        rows, source_means=source_means, source_scales=source_scales,
        action_scales=action_scales,
    )
    targets = np.asarray([
        1.0 if row[LABEL_FAMILY][METRIC]["relation"]
        == "higher_afterstate_better" else -1.0
        for row in rows
    ])
    dual = np.linalg.solve(
        design @ design.T + l2 * np.eye(len(rows)), targets
    )
    weights = design.T @ dual
    return {
        "model": "state_action_bilinear_pairwise_ridge_no_intercept",
        "target": "directional_distributional_fill_continuation_relation",
        "l2": l2,
        "training_rows": len(rows),
        "source_feature_count": sources.shape[1],
        "action_delta_feature_count": actions.shape[1],
        "expanded_feature_count": design.shape[1],
        "source_means": source_means.tolist(),
        "source_scales": source_scales.tolist(),
        "action_scales": action_scales.tolist(),
        "weights": weights.tolist(),
    }


def _score_pairwise(model: dict[str, Any], rows: list[dict[str, Any]]) -> list[float]:
    if not rows:
        return []
    design = _pairwise_design(
        rows,
        source_means=np.asarray(model["source_means"], dtype=float),
        source_scales=np.asarray(model["source_scales"], dtype=float),
        action_scales=np.asarray(model["action_scales"], dtype=float),
    )
    return (design @ np.asarray(model["weights"], dtype=float)).tolist()


def _predict_pairwise(model: dict[str, Any], rows: list[dict[str, Any]]) -> list[str]:
    scores = _score_pairwise(model, rows)
    return [
        "higher_afterstate_better" if score >= 0.0 else "lower_afterstate_better"
        for score in scores
    ]


def _select_pairwise_l2(training_runs: list[dict[str, Any]]) -> dict[str, Any]:
    results = []
    for l2 in PAIRWISE_L2_GRID:
        correct = 0
        rows = 0
        per_run = []
        for held_out in training_runs:
            train = [
                row for run in training_runs if run is not held_out
                for row in _eligible(
                    run["discovery"], METRIC, label_family=LABEL_FAMILY
                )
            ]
            test = _eligible(
                held_out["discovery"], METRIC, label_family=LABEL_FAMILY
            )
            predictions = _predict_pairwise(_fit_pairwise(train, l2), test)
            fold_correct = sum(
                prediction == row[LABEL_FAMILY][METRIC]["relation"]
                for prediction, row in zip(predictions, test)
            )
            correct += fold_correct
            rows += len(test)
            per_run.append({
                "run_id": held_out["run_id"], "rows": len(test),
                "correct": fold_correct,
            })
        results.append({
            "l2": l2, "rows": rows, "correct": correct,
            "accuracy": correct / rows, "per_run": per_run,
        })
    selected = max(results, key=lambda item: (item["correct"], item["l2"]))
    return {"selection": "leave_one_run_out_accuracy", "grid": results,
            "selected_l2": selected["l2"]}


def build_student(
    training_runs: list[dict[str, Any]], shadow_model: dict[str, Any],
) -> dict[str, Any]:
    run_ids = [str(run["run_id"]) for run in training_runs]
    if len(set(run_ids)) != len(run_ids):
        raise ValueError("training run IDs must be unique")
    if set(run_ids) != set(map(str, shadow_model["training_run_ids"])):
        raise ValueError(
            "student and shadow model must use the same training runs"
        )
    rows = [row for run in training_runs for row in run["discovery"]]
    eligible_rows = _eligible(rows, METRIC, label_family=LABEL_FAMILY)
    pairwise_selection = _select_pairwise_l2(training_runs)
    return {
        "schema_version": 1,
        "status": "development_preaction_student",
        "label_family": LABEL_FAMILY,
        "axis": METRIC,
        "training_run_ids": run_ids,
        "input_contract": (
            "source observed-set summary plus candidate action-geometry delta "
            "without immediate score; no post-settle state, step, or future "
            "labels"
        ),
        "shadow_training_run_ids": shadow_model["training_run_ids"],
        "pairwise_selection": pairwise_selection,
        "pairwise_value_predictor": _fit_pairwise(
            eligible_rows, pairwise_selection["selected_l2"]
        ),
        "claim_limit": (
            "Frozen branch-direction candidate pending prospective physical-"
            "seed confirmation and later episode-score evaluation"
        ),
    }


def _relation(model: dict[str, Any], delta: list[float]) -> str:
    scales = np.asarray(model["scales"], dtype=float)
    weights = np.asarray(model["weights"], dtype=float)
    values = np.asarray(delta, dtype=float)
    if values.shape != scales.shape:
        raise ValueError("shadow feature count mismatch")
    return (
        "higher_afterstate_better"
        if float(np.dot(values / scales, weights)) >= 0.0
        else "lower_afterstate_better"
    )


def student_predictions(
    student: dict[str, Any], shadow_model: dict[str, Any],
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    output = []
    pairwise_relations = _predict_pairwise(
        student["pairwise_value_predictor"], rows
    )
    for row, pairwise_relation in zip(rows, pairwise_relations):
        action_delta = _action_delta(row)
        action_relation = _relation(
            shadow_model["models"]["action_geometry"], action_delta
        )
        output.append({
            "teacher_id": row["teacher_id"],
            "action_geometry_prediction": action_relation,
            "student_relation": pairwise_relation,
            "changed_from_action_geometry": pairwise_relation != action_relation,
        })
    return output


def evaluate_student(
    student: dict[str, Any], shadow_model: dict[str, Any],
    targets: list[dict[str, Any]], *, evaluation_kind: str = "development",
) -> dict[str, Any]:
    totals = {
        "rows": 0, "student_correct": 0, "action_geometry_correct": 0,
        "oracle_shadow_correct": 0, "student_matches_oracle": 0,
        "changed_from_action_geometry": 0,
    }
    paired = {"wins": 0, "ties": 0, "losses": 0}
    per_run = []
    signature_groups: dict[str, list[dict[str, str]]] = collections.defaultdict(list)
    for target in targets:
        rows = _eligible(
            target["late"], METRIC, label_family=LABEL_FAMILY
        )
        predictions = student_predictions(student, shadow_model, rows)
        by_id = {row["teacher_id"]: row for row in rows}
        run_counts = {name: 0 for name in totals}
        run_counts["rows"] = len(rows)
        for prediction in predictions:
            row = by_id[prediction["teacher_id"]]
            actual = row[LABEL_FAMILY][METRIC]["relation"]
            signature_groups[_preaction_signature(row)].append({
                "run_id": str(target["run_id"]),
                "teacher_id": str(row["teacher_id"]),
                "relation": str(actual),
            })
            oracle_blocks = {
                block: _relation(
                    shadow_model["models"][block],
                    _state_block_delta(row, block),
                )
                for block in BLOCKS
            }
            oracle_relation = (
                oracle_blocks["packed"]
                if oracle_blocks["packed"] == oracle_blocks["packed_visible"]
                else prediction["action_geometry_prediction"]
            )
            student_correct = prediction["student_relation"] == actual
            action_correct = prediction["action_geometry_prediction"] == actual
            if student_correct and not action_correct:
                paired["wins"] += 1
            elif action_correct and not student_correct:
                paired["losses"] += 1
            else:
                paired["ties"] += 1
            run_counts["student_correct"] += student_correct
            run_counts["action_geometry_correct"] += action_correct
            run_counts["oracle_shadow_correct"] += oracle_relation == actual
            run_counts["student_matches_oracle"] += (
                prediction["student_relation"] == oracle_relation
            )
            run_counts["changed_from_action_geometry"] += prediction[
                "changed_from_action_geometry"
            ]
        for name in totals:
            totals[name] += run_counts[name]
        per_run.append({"target_run_id": target["run_id"], **run_counts})
    paired["exact_two_sided_sign_p"] = _exact_two_sided_sign_p(
        paired["wins"], paired["losses"]
    )
    cross_run_groups = [
        group for group in signature_groups.values()
        if len({row["run_id"] for row in group}) > 1
    ]
    conflicting_groups = [
        group for group in signature_groups.values()
        if len({row["relation"] for row in group}) > 1
    ]
    return {
        "schema_version": 1,
        "evaluation_kind": evaluation_kind,
        "training_run_ids": student["training_run_ids"],
        "target_run_ids": [target["run_id"] for target in targets],
        **totals,
        "paired_student_vs_action_geometry": paired,
        "preaction_support_audit": {
            "signature": "exact source-state summary plus action-geometry delta",
            "unique_signatures": len(signature_groups),
            "unique_fraction": len(signature_groups) / totals["rows"],
            "cross_run_duplicate_groups": len(cross_run_groups),
            "rows_in_cross_run_duplicate_groups": sum(
                len(group) for group in cross_run_groups
            ),
            "conflicting_signature_groups": len(conflicting_groups),
        },
        "per_run": per_run,
        "claim": (
            "Prospective audit of the unchanged frozen pre-action student; "
            "apply the separately preregistered gate to determine confirmation."
            if evaluation_kind == "prospective" else
            "Development audit of a pre-action student. Target runs inspected "
            "during student development cannot confirm a frozen policy."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--training-dir", action="append", type=pathlib.Path)
    parser.add_argument("--target-dir", action="append", type=pathlib.Path)
    parser.add_argument("--shadow-model", type=pathlib.Path, required=True)
    parser.add_argument("--student-model", type=pathlib.Path)
    parser.add_argument("--student-output", type=pathlib.Path)
    parser.add_argument("--evaluation-output", type=pathlib.Path)
    parser.add_argument(
        "--evaluation-kind", choices=("development", "prospective"),
        default="development",
    )
    parser.add_argument(
        "--status", default="development_preaction_student",
        choices=(
            "development_preaction_student",
            "frozen_pending_prospective_confirmation",
        ),
    )
    args = parser.parse_args()
    shadow_model = json.loads(args.shadow_model.read_text(encoding="utf-8"))
    if args.student_model:
        if args.training_dir or args.student_output:
            parser.error(
                "--student-model forbids --training-dir and --student-output"
            )
        student = json.loads(args.student_model.read_text(encoding="utf-8"))
    elif args.training_dir and args.student_output:
        training_runs = [
            load_run(path, label_family=LABEL_FAMILY)
            for path in args.training_dir
        ]
        student = build_student(training_runs, shadow_model)
        student["status"] = args.status
        args.student_output.parent.mkdir(parents=True, exist_ok=True)
        args.student_output.write_text(
            json.dumps(student, indent=2) + "\n", encoding="utf-8"
        )
    else:
        parser.error(
            "provide --student-model or both --training-dir and --student-output"
        )
    if args.target_dir:
        if not args.evaluation_output:
            parser.error("--target-dir requires --evaluation-output")
        report = evaluate_student(
            student, shadow_model,
            [load_run(path, label_family=LABEL_FAMILY) for path in args.target_dir],
            evaluation_kind=args.evaluation_kind,
        )
        args.evaluation_output.parent.mkdir(parents=True, exist_ok=True)
        args.evaluation_output.write_text(
            json.dumps(report, indent=2) + "\n", encoding="utf-8"
        )
    print(args.student_output or args.evaluation_output or args.student_model)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
