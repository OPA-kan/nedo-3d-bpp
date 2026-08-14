"""Develop a local-geometry pre-action value model under strict stream holdout."""

from __future__ import annotations

import argparse
import copy
import json
import pathlib
from typing import Any

import numpy as np

SUPPORT_QUANTILE_GRID = (0.5, 0.75, 0.9, 0.95, 1.0)

try:
    from scripts.build_distributional_fill_preaction_student import (
        LABEL_FAMILY,
        METRIC,
        PAIRWISE_L2_GRID,
        _action_delta,
        _predict_pairwise,
    )
    from scripts.develop_distributional_fill_preaction_v2 import (
        OVERRIDE_RATIO_GRID,
        _action_scores,
        _hybrid_predictions,
        _streams,
        _target,
        deduplicate_rows,
    )
    from scripts.evaluate_counterfactual_afterstate_value import (
        _eligible,
        _exact_two_sided_sign_p,
        load_run,
    )
    from scripts.evaluate_counterfactual_teacher_discovery import (
        _candidate_local_features,
    )
except ModuleNotFoundError:
    from build_distributional_fill_preaction_student import (
        LABEL_FAMILY,
        METRIC,
        PAIRWISE_L2_GRID,
        _action_delta,
        _predict_pairwise,
    )
    from develop_distributional_fill_preaction_v2 import (
        OVERRIDE_RATIO_GRID,
        _action_scores,
        _hybrid_predictions,
        _streams,
        _target,
        deduplicate_rows,
    )
    from evaluate_counterfactual_afterstate_value import (
        _eligible,
        _exact_two_sided_sign_p,
        load_run,
    )
    from evaluate_counterfactual_teacher_discovery import (
        _candidate_local_features,
    )


def _oriented_action(action: dict[str, Any]) -> dict[str, Any]:
    output = copy.deepcopy(action)
    names = output["feature_names"]
    indices = {name: names.index(name) for name in (
        "orientation", "length", "width", "height"
    )}
    length, width, height = (
        float(output["values"][indices[name]])
        for name in ("length", "width", "height")
    )
    dimensions = (
        (length, width, height), (length, height, width),
        (height, width, length), (width, length, height),
        (width, height, length), (height, length, width),
    )
    orientation = int(round(float(output["values"][indices["orientation"]])))
    for name, value in zip(("length", "width", "height"), dimensions[orientation]):
        output["values"][indices[name]] = value
    return output


def _packed_aabb_state(state: dict[str, Any]) -> dict[str, Any]:
    output = copy.deepcopy(state)
    names = output["packed_item_features"]
    required = (
        "quaternion_x", "quaternion_y", "quaternion_z", "quaternion_w",
        "length", "width", "height",
    )
    if not set(required).issubset(names):
        return output
    index = {name: names.index(name) for name in required}
    for values in output["packed_item_values"]:
        x, y, z, w = (
            float(values[index[f"quaternion_{axis}"]]) for axis in "xyzw"
        )
        rotation = (
            (1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)),
            (2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)),
            (2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)),
        )
        dimensions = np.asarray([
            float(values[index[name]]) for name in ("length", "width", "height")
        ])
        aabb = np.abs(np.asarray(rotation)) @ dimensions
        for name, value in zip(("length", "width", "height"), aabb):
            values[index[name]] = float(value)
    return output


def local_pair_vector(row: dict[str, Any]) -> list[float]:
    state = _packed_aabb_state(row["source_state_tensor"])
    lower = _candidate_local_features(_oriented_action(row["lower_action_tensor"]), state)
    higher = _candidate_local_features(
        _oriented_action(row["higher_action_tensor"]), state
    )
    return _action_delta(row) + lower + higher + [
        right - left for left, right in zip(lower, higher)
    ]


def fit_local_ridge(rows: list[dict[str, Any]], l2: float) -> dict[str, Any]:
    values = np.asarray([local_pair_vector(row) for row in rows], dtype=float)
    means = np.mean(values, axis=0)
    scales = np.std(values, axis=0)
    scales[scales == 0.0] = 1.0
    design = np.column_stack([np.ones(len(rows)), (values - means) / scales])
    targets = np.asarray([
        1.0 if _target(row) == "higher_afterstate_better" else -1.0
        for row in rows
    ])
    penalty = np.eye(design.shape[1])
    penalty[0, 0] = 0.0
    weights = np.linalg.solve(
        design.T @ design + l2 * penalty, design.T @ targets
    )
    return {
        "model": "local_geometry_pairwise_ridge_with_intercept",
        "l2": l2,
        "training_rows": len(rows),
        "feature_count": values.shape[1],
        "means": means.tolist(),
        "scales": scales.tolist(),
        "weights": weights.tolist(),
        "training_standardized": ((values - means) / scales).tolist(),
    }


def score_local(model: dict[str, Any], rows: list[dict[str, Any]]) -> list[float]:
    if not rows:
        return []
    values = np.asarray([local_pair_vector(row) for row in rows], dtype=float)
    means = np.asarray(model["means"], dtype=float)
    scales = np.asarray(model["scales"], dtype=float)
    design = np.column_stack([np.ones(len(rows)), (values - means) / scales])
    return (design @ np.asarray(model["weights"], dtype=float)).tolist()


def support_distances(
    model: dict[str, Any], rows: list[dict[str, Any]],
) -> list[float]:
    if not rows:
        return []
    values = np.asarray([local_pair_vector(row) for row in rows], dtype=float)
    standardized = (
        values - np.asarray(model["means"], dtype=float)
    ) / np.asarray(model["scales"], dtype=float)
    training = np.asarray(model["training_standardized"], dtype=float)
    return [
        float(np.min(np.sum(np.square(training - row), axis=1)))
        for row in standardized
    ]


def support_threshold(model: dict[str, Any], quantile: float) -> float:
    training = np.asarray(model["training_standardized"], dtype=float)
    distances = np.sum(
        np.square(training[:, None, :] - training[None, :, :]), axis=2
    )
    np.fill_diagonal(distances, np.inf)
    nearest = np.min(distances, axis=1)
    return float(np.quantile(nearest, quantile))


def _support_gated_predictions(
    student_scores: list[float], action_scores: list[float],
    distances: list[float], *, ratio: float, maximum_distance: float,
) -> list[str]:
    predictions = _hybrid_predictions(student_scores, action_scores, ratio)
    action_predictions = [
        "higher_afterstate_better" if score >= 0.0 else "lower_afterstate_better"
        for score in action_scores
    ]
    return [
        prediction if distance <= maximum_distance else action
        for prediction, action, distance in zip(
            predictions, action_predictions, distances
        )
    ]


def select_policy(
    rows: list[dict[str, Any]], shadow: dict[str, Any],
) -> dict[str, Any]:
    streams = sorted({stream for row in rows for stream in _streams(row)})
    grid = []
    for l2 in PAIRWISE_L2_GRID:
        folds = []
        for stream in streams:
            train = [row for row in rows if stream not in _streams(row)]
            test = [row for row in rows if stream in _streams(row)]
            fold_model = fit_local_ridge(train, l2)
            folds.append({
                "stream_variant": stream,
                "rows": test,
                "student_scores": score_local(fold_model, test),
                "action_scores": _action_scores(shadow, test),
                "support_distances": support_distances(fold_model, test),
                "support_thresholds": {
                    quantile: support_threshold(fold_model, quantile)
                    for quantile in SUPPORT_QUANTILE_GRID
                },
            })
        for threshold in OVERRIDE_RATIO_GRID:
          for support_quantile in SUPPORT_QUANTILE_GRID:
            per_stream = []
            for fold in folds:
                predictions = _support_gated_predictions(
                    fold["student_scores"], fold["action_scores"],
                    fold["support_distances"], ratio=threshold,
                    maximum_distance=fold["support_thresholds"][support_quantile],
                )
                action = [
                    "higher_afterstate_better" if score >= 0.0
                    else "lower_afterstate_better"
                    for score in fold["action_scores"]
                ]
                per_stream.append({
                    "stream_variant": fold["stream_variant"],
                    "rows": len(fold["rows"]),
                    "candidate_correct": sum(
                        prediction == _target(row)
                        for prediction, row in zip(predictions, fold["rows"])
                    ),
                    "action_correct": sum(
                        prediction == _target(row)
                        for prediction, row in zip(action, fold["rows"])
                    ),
                })
            grid.append({
                "l2": l2,
                "override_ratio_threshold": threshold,
                "support_quantile": support_quantile,
                "candidate_correct": sum(
                    item["candidate_correct"] for item in per_stream
                ),
                "action_correct": sum(item["action_correct"] for item in per_stream),
                "all_streams_nonregressing": all(
                    item["candidate_correct"] >= item["action_correct"]
                    for item in per_stream
                ),
                "per_stream": per_stream,
            })
    eligible = [
        item for item in grid
        if item["all_streams_nonregressing"]
        and item["candidate_correct"] > item["action_correct"]
    ]
    if not eligible:
        eligible = [item for item in grid if item["all_streams_nonregressing"]]
    selected = max(
        eligible,
        key=lambda item: (
            item["candidate_correct"], item["override_ratio_threshold"],
            item["support_quantile"], item["l2"]
        ),
    )
    return {
        "selection": "strict exact-signature leave-one-stream-out nonregression",
        "selected_l2": selected["l2"],
        "selected_override_ratio_threshold": selected[
            "override_ratio_threshold"
        ],
        "selected_support_quantile": selected["support_quantile"],
        "selected_improves_action": (
            selected["candidate_correct"] > selected["action_correct"]
        ),
        "selected_result": selected,
    }


def build_v3(
    runs: list[dict[str, Any]], shadow: dict[str, Any],
) -> dict[str, Any]:
    raw = [
        row for run in runs
        for row in _eligible(run["discovery"], METRIC, label_family=LABEL_FAMILY)
    ]
    support = deduplicate_rows(raw)
    selection = select_policy(support["rows"], shadow)
    return {
        "schema_version": 1,
        "status": "development_local_geometry_student",
        "label_family": LABEL_FAMILY,
        "axis": METRIC,
        "training_run_ids": [run["run_id"] for run in runs],
        "training_support": {
            name: value for name, value in support.items() if name != "rows"
        },
        "model_selection": selection,
        "input_contract": (
            "source tensor plus candidate command/item geometry; immediate "
            "score, step, post-settle state, and future labels excluded"
        ),
        "local_value_predictor": fit_local_ridge(
            support["rows"], selection["selected_l2"]
        ),
    }


def confirmation_gate(
    evaluation: dict[str, Any], *,
    contract: str = "predeclared in distributional-fill-preaction-v3.md",
) -> dict[str, Any]:
    support = evaluation["support"]
    paired = evaluation["paired_candidate_vs_action"]
    checks = {
        "at_least_four_complete_streams": len(evaluation["per_stream"]) >= 4,
        "at_least_30_unique_late_signatures": support["unique_rows"] >= 30,
        "at_least_50_percent_unique_support": support["unique_fraction"] >= 0.5,
        "every_stream_nonregressing": all(
            row["candidate_correct"] >= row["action_geometry_correct"]
            for row in evaluation["per_stream"]
        ),
        "pooled_wins_exceed_losses": paired["wins"] > paired["losses"],
        "exact_sign_p_at_most_0_05": paired["exact_two_sided_sign_p"] <= 0.05,
    }
    return {
        "checks": checks,
        "passed": all(checks.values()),
        "contract": contract,
    }


def evaluate_unique(
    model: dict[str, Any], v1: dict[str, Any], shadow: dict[str, Any],
    runs: list[dict[str, Any]], *, evaluation_kind: str = "development",
) -> dict[str, Any]:
    raw = [
        row for run in runs
        for row in _eligible(run["late"], METRIC, label_family=LABEL_FAMILY)
    ]
    support = deduplicate_rows(raw)
    rows = support["rows"]
    action_scores = _action_scores(shadow, rows)
    predictor = model["local_value_predictor"]
    candidate = _support_gated_predictions(
        score_local(predictor, rows), action_scores,
        support_distances(predictor, rows),
        ratio=model["model_selection"]["selected_override_ratio_threshold"],
        maximum_distance=support_threshold(
            predictor, model["model_selection"]["selected_support_quantile"]
        ),
    )
    action = [
        "higher_afterstate_better" if score >= 0.0 else "lower_afterstate_better"
        for score in action_scores
    ]
    incumbent = _predict_pairwise(v1["pairwise_value_predictor"], rows)
    systems = {"candidate": candidate, "v1": incumbent, "action_geometry": action}
    correct = {
        name: sum(prediction == _target(row) for prediction, row in zip(values, rows))
        for name, values in systems.items()
    }
    wins = sum(
        candidate_prediction == _target(row)
        and action_prediction != _target(row)
        for candidate_prediction, action_prediction, row in zip(candidate, action, rows)
    )
    losses = sum(
        action_prediction == _target(row)
        and candidate_prediction != _target(row)
        for candidate_prediction, action_prediction, row in zip(candidate, action, rows)
    )
    per_stream = []
    for stream in sorted({item for row in rows for item in _streams(row)}):
        indices = [index for index, row in enumerate(rows) if stream in _streams(row)]
        per_stream.append({
            "stream_variant": stream,
            "rows": len(indices),
            **{
                f"{name}_correct": sum(
                    systems[name][index] == _target(rows[index]) for index in indices
                )
                for name in systems
            },
        })
    threshold_audit = []
    student_scores = score_local(model["local_value_predictor"], rows)
    distances = support_distances(model["local_value_predictor"], rows)
    selected_support_threshold = support_threshold(
        model["local_value_predictor"],
        model["model_selection"]["selected_support_quantile"],
    )
    for threshold in OVERRIDE_RATIO_GRID:
        predictions = _support_gated_predictions(
            student_scores, action_scores, distances, ratio=threshold,
            maximum_distance=selected_support_threshold,
        )
        stream_rows = []
        for stream in sorted({item for row in rows for item in _streams(row)}):
            indices = [
                index for index, row in enumerate(rows)
                if stream in _streams(row)
            ]
            stream_rows.append({
                "stream_variant": stream,
                "candidate_correct": sum(
                    predictions[index] == _target(rows[index]) for index in indices
                ),
                "action_correct": sum(
                    action[index] == _target(rows[index]) for index in indices
                ),
            })
        threshold_audit.append({
            "override_ratio_threshold": threshold,
            "correct": sum(
                prediction == _target(row)
                for prediction, row in zip(predictions, rows)
            ),
            "all_streams_nonregressing": all(
                item["candidate_correct"] >= item["action_correct"]
                for item in stream_rows
            ),
            "per_stream": stream_rows,
        })
    evaluation = {
        "schema_version": 1,
        "evaluation_kind": (
            "prospective_confirmation_unique_signatures"
            if evaluation_kind == "prospective_confirmation"
            else "inspected_development_unique_signatures"
        ),
        "target_run_ids": [run["run_id"] for run in runs],
        "support": {name: value for name, value in support.items() if name != "rows"},
        "correct": correct,
        "paired_candidate_vs_action": {
            "wins": wins, "ties": len(rows) - wins - losses, "losses": losses,
            "exact_two_sided_sign_p": _exact_two_sided_sign_p(wins, losses),
        },
        "per_stream": per_stream,
        "diagnostic_only_posthoc_threshold_audit": threshold_audit,
    }
    if evaluation_kind == "prospective_confirmation":
        evaluation["predeclared_confirmation_gate"] = confirmation_gate(evaluation)
        evaluation["claim"] = (
            "Prospective confirmation passed; this establishes an offline "
            "branch-direction candidate, not an episode-score improvement."
            if evaluation["predeclared_confirmation_gate"]["passed"] else
            "Prospective confirmation failed; the frozen candidate is rejected."
        )
    else:
        evaluation["claim"] = (
            "Development evidence only; target runs are inspected and cannot "
            "confirm the frozen candidate."
        )
    return evaluation


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--training-dir", action="append", type=pathlib.Path)
    parser.add_argument("--target-dir", action="append", type=pathlib.Path)
    parser.add_argument("--model", type=pathlib.Path)
    parser.add_argument("--v1-model", type=pathlib.Path, required=True)
    parser.add_argument("--shadow-model", type=pathlib.Path, required=True)
    parser.add_argument("--model-output", type=pathlib.Path)
    parser.add_argument("--evaluation-output", type=pathlib.Path, required=True)
    parser.add_argument(
        "--evaluation-kind", default="development",
        choices=("development", "prospective_confirmation"),
    )
    parser.add_argument(
        "--status", default="development_local_geometry_student",
        choices=(
            "development_local_geometry_student",
            "frozen_pending_new_stream_confirmation",
        ),
    )
    args = parser.parse_args()
    shadow = json.loads(args.shadow_model.read_text(encoding="utf-8"))
    v1 = json.loads(args.v1_model.read_text(encoding="utf-8"))
    if args.model:
        if args.training_dir or args.model_output:
            parser.error("--model forbids --training-dir and --model-output")
        model = json.loads(args.model.read_text(encoding="utf-8"))
        if not args.target_dir:
            parser.error("--model requires --target-dir")
        runs = [
            load_run(path, label_family=LABEL_FAMILY) for path in args.target_dir
        ]
    elif args.training_dir and args.model_output:
        training_runs = [
            load_run(path, label_family=LABEL_FAMILY) for path in args.training_dir
        ]
        model = build_v3(training_runs, shadow)
        model["status"] = args.status
        args.model_output.parent.mkdir(parents=True, exist_ok=True)
        args.model_output.write_text(
            json.dumps(model, indent=2) + "\n", encoding="utf-8"
        )
        runs = (
            [load_run(path, label_family=LABEL_FAMILY) for path in args.target_dir]
            if args.target_dir else training_runs
        )
    else:
        parser.error("provide --model or --training-dir with --model-output")
    evaluation = evaluate_unique(
        model, v1, shadow, runs, evaluation_kind=args.evaluation_kind
    )
    args.evaluation_output.parent.mkdir(parents=True, exist_ok=True)
    args.evaluation_output.write_text(
        json.dumps(evaluation, indent=2) + "\n", encoding="utf-8"
    )
    print(args.evaluation_output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
