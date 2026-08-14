#!/usr/bin/env python3
"""Develop and evaluate a stream-group-cross-fitted local kNN student."""

from __future__ import annotations

import argparse
import json
import pathlib
from typing import Any

import numpy as np

try:
    from .develop_distributional_fill_preaction_v2 import (
        _action_scores,
        _hybrid_predictions,
        _streams,
        _target,
        deduplicate_rows,
    )
    from .develop_distributional_fill_preaction_v3 import (
        LABEL_FAMILY,
        METRIC,
        confirmation_gate,
        local_pair_vector,
    )
    from .evaluate_counterfactual_afterstate_value import (
        _eligible,
        _exact_two_sided_sign_p,
        load_run,
    )
except ImportError:
    from develop_distributional_fill_preaction_v2 import (
        _action_scores,
        _hybrid_predictions,
        _streams,
        _target,
        deduplicate_rows,
    )
    from develop_distributional_fill_preaction_v3 import (
        LABEL_FAMILY,
        METRIC,
        confirmation_gate,
        local_pair_vector,
    )
    from evaluate_counterfactual_afterstate_value import (
        _eligible,
        _exact_two_sided_sign_p,
        load_run,
    )


K_GRID = (1, 3, 5, 9, 17, 33)
WEIGHTED_GRID = (False, True)
SUPPORT_QUANTILE_GRID = (0.5, 0.75, 0.9, 1.0)
OVERRIDE_RATIO_GRID = (0.0, 0.5, 1.0, 2.0, 4.0, 8.0)
MINIMUM_WEIGHT_DISTANCE = 0.25


def _squared_distances(left: np.ndarray, right: np.ndarray) -> np.ndarray:
    return np.maximum(
        np.sum(left * left, axis=1)[:, None]
        + np.sum(right * right, axis=1)[None, :]
        - 2.0 * left @ right.T,
        0.0,
    )


def group_complement_indices(
    rows: list[dict[str, Any]],
) -> list[tuple[list[int], list[int]]]:
    """Cross-fit each signature once while excluding all of its streams."""
    groups = sorted({tuple(sorted(_streams(row))) for row in rows})
    folds = []
    for heldout_streams in groups:
        heldout = set(heldout_streams)
        test = [
            index for index, row in enumerate(rows)
            if tuple(sorted(_streams(row))) == heldout_streams
        ]
        train = [
            index for index, row in enumerate(rows)
            if heldout.isdisjoint(_streams(row))
        ]
        if not train:
            raise ValueError(f"no training rows remain for streams {heldout_streams}")
        folds.append((train, test))
    return folds


def _standardize_fit(values: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    means = values.mean(axis=0)
    scales = values.std(axis=0)
    scales[scales < 1e-9] = 1.0
    return means, scales


def _neighbor_score(
    labels: np.ndarray, squared_distances: np.ndarray, order: np.ndarray,
    *, k: int, weighted: bool,
) -> np.ndarray:
    take = order[:, :min(k, order.shape[1])]
    near_labels = labels[take]
    if not weighted:
        return near_labels.mean(axis=1)
    near_distances = np.sqrt(
        np.take_along_axis(squared_distances, take, axis=1)
    )
    weights = 1.0 / np.maximum(near_distances, MINIMUM_WEIGHT_DISTANCE)
    return np.sum(weights * near_labels, axis=1) / np.sum(weights, axis=1)


def _prepare_crossfit(rows: list[dict[str, Any]], shadow: dict[str, Any]) -> list[dict[str, Any]]:
    values = np.asarray([local_pair_vector(row) for row in rows], dtype=float)
    labels = np.asarray([
        1.0 if _target(row) == "higher_afterstate_better" else -1.0
        for row in rows
    ])
    folds = []
    for train_indices, test_indices in group_complement_indices(rows):
        train_values = values[train_indices]
        means, scales = _standardize_fit(train_values)
        train = (train_values - means) / scales
        test = (values[test_indices] - means) / scales
        squared = _squared_distances(test, train)
        train_squared = _squared_distances(train, train)
        np.fill_diagonal(train_squared, np.inf)
        test_rows = [rows[index] for index in test_indices]
        folds.append({
            "test_indices": test_indices,
            "labels": labels[train_indices],
            "squared_distances": squared,
            "order": np.argsort(squared, axis=1),
            "support_distances": np.sqrt(np.min(squared, axis=1)),
            "training_support_distances": np.sqrt(np.min(train_squared, axis=1)),
            "action_scores": np.asarray(_action_scores(shadow, test_rows)),
        })
    return folds


def _score_predictions(
    rows: list[dict[str, Any]], candidate: list[str], action: list[str],
) -> dict[str, Any]:
    truth = [_target(row) for row in rows]
    wins = sum(c == target and a != target for c, a, target in zip(candidate, action, truth))
    losses = sum(a == target and c != target for c, a, target in zip(candidate, action, truth))
    per_stream = []
    for stream in sorted({item for row in rows for item in _streams(row)}):
        indices = [index for index, row in enumerate(rows) if stream in _streams(row)]
        per_stream.append({
            "stream_variant": stream,
            "rows": len(indices),
            "candidate_correct": sum(candidate[index] == truth[index] for index in indices),
            "action_geometry_correct": sum(action[index] == truth[index] for index in indices),
        })
    return {
        "candidate_correct": sum(c == target for c, target in zip(candidate, truth)),
        "action_geometry_correct": sum(a == target for a, target in zip(action, truth)),
        "wins": wins,
        "ties": len(rows) - wins - losses,
        "losses": losses,
        "exact_two_sided_sign_p": _exact_two_sided_sign_p(wins, losses),
        "all_streams_nonregressing": all(
            row["candidate_correct"] >= row["action_geometry_correct"]
            for row in per_stream
        ),
        "per_stream": per_stream,
    }


def select_policy(rows: list[dict[str, Any]], shadow: dict[str, Any]) -> dict[str, Any]:
    folds = _prepare_crossfit(rows, shadow)
    candidates = []
    for k in K_GRID:
        for weighted in WEIGHTED_GRID:
            for support_quantile in SUPPORT_QUANTILE_GRID:
                for override_ratio in OVERRIDE_RATIO_GRID:
                    predictions: list[str | None] = [None] * len(rows)
                    action_predictions: list[str | None] = [None] * len(rows)
                    for fold in folds:
                        scores = _neighbor_score(
                            fold["labels"], fold["squared_distances"], fold["order"],
                            k=k, weighted=weighted,
                        )
                        action_scores = fold["action_scores"]
                        hybrid = _hybrid_predictions(scores, action_scores, override_ratio)
                        support_threshold = float(np.quantile(
                            fold["training_support_distances"], support_quantile
                        ))
                        action = [
                            "higher_afterstate_better" if score >= 0.0
                            else "lower_afterstate_better"
                            for score in action_scores
                        ]
                        gated = [
                            prediction if distance <= support_threshold else fallback
                            for prediction, fallback, distance in zip(
                                hybrid, action, fold["support_distances"]
                            )
                        ]
                        for index, prediction, fallback in zip(
                            fold["test_indices"], gated, action
                        ):
                            predictions[index] = prediction
                            action_predictions[index] = fallback
                    if any(item is None for item in predictions + action_predictions):
                        raise AssertionError("cross-fit did not predict every unique row")
                    result = _score_predictions(
                        rows,
                        [str(item) for item in predictions],
                        [str(item) for item in action_predictions],
                    )
                    candidates.append({
                        "k": k,
                        "weighted": weighted,
                        "support_quantile": support_quantile,
                        "override_ratio_threshold": override_ratio,
                        **result,
                    })
    selected = max(candidates, key=lambda item: (
        item["all_streams_nonregressing"],
        item["candidate_correct"],
        -item["losses"],
        item["wins"],
        item["override_ratio_threshold"],
        -item["support_quantile"],
        -item["k"],
        item["weighted"],
    ))
    return {
        "validation_contract": (
            "Each exact signature is predicted once. Every stream attached to "
            "that signature is simultaneously excluded from its training fold."
        ),
        "selection_order": (
            "all-stream non-regression, pooled correct, fewer losses, more wins, "
            "then conservative deterministic tie-breaks"
        ),
        "grid": {
            "k": list(K_GRID),
            "weighted": list(WEIGHTED_GRID),
            "support_quantile": list(SUPPORT_QUANTILE_GRID),
            "override_ratio_threshold": list(OVERRIDE_RATIO_GRID),
        },
        "evaluated_candidates": len(candidates),
        "selected_result": selected,
    }


def fit_knn(rows: list[dict[str, Any]], selection: dict[str, Any]) -> dict[str, Any]:
    values = np.asarray([local_pair_vector(row) for row in rows], dtype=float)
    means, scales = _standardize_fit(values)
    standardized = (values - means) / scales
    squared = _squared_distances(standardized, standardized)
    np.fill_diagonal(squared, np.inf)
    support_distances = np.sqrt(np.min(squared, axis=1))
    selected = selection["selected_result"]
    return {
        "feature_count": values.shape[1],
        "means": means.tolist(),
        "scales": scales.tolist(),
        "standardized_training_vectors": standardized.tolist(),
        "training_labels": [
            1.0 if _target(row) == "higher_afterstate_better" else -1.0
            for row in rows
        ],
        "k": selected["k"],
        "weighted": selected["weighted"],
        "minimum_weight_distance": MINIMUM_WEIGHT_DISTANCE,
        "support_quantile": selected["support_quantile"],
        "support_distance_threshold": float(np.quantile(
            support_distances, selected["support_quantile"]
        )),
        "override_ratio_threshold": selected["override_ratio_threshold"],
    }


def predict_knn(
    predictor: dict[str, Any], shadow: dict[str, Any], rows: list[dict[str, Any]],
) -> tuple[list[str], list[str], list[float]]:
    if not rows:
        return [], [], []
    values = np.asarray([local_pair_vector(row) for row in rows], dtype=float)
    means = np.asarray(predictor["means"], dtype=float)
    scales = np.asarray(predictor["scales"], dtype=float)
    training = np.asarray(predictor["standardized_training_vectors"], dtype=float)
    labels = np.asarray(predictor["training_labels"], dtype=float)
    standardized = (values - means) / scales
    squared = _squared_distances(standardized, training)
    distances = np.sqrt(np.min(squared, axis=1))
    scores = _neighbor_score(
        labels, squared, np.argsort(squared, axis=1),
        k=int(predictor["k"]), weighted=bool(predictor["weighted"]),
    )
    action_scores = np.asarray(_action_scores(shadow, rows))
    hybrid = _hybrid_predictions(
        scores, action_scores, float(predictor["override_ratio_threshold"])
    )
    action = [
        "higher_afterstate_better" if score >= 0.0 else "lower_afterstate_better"
        for score in action_scores
    ]
    candidate = [
        prediction
        if distance <= float(predictor["support_distance_threshold"])
        else fallback
        for prediction, fallback, distance in zip(hybrid, action, distances)
    ]
    return candidate, action, distances.tolist()


def _all_rows(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        row for run in runs for split in ("discovery", "late")
        for row in _eligible(run[split], METRIC, label_family=LABEL_FAMILY)
    ]


def build_v4(runs: list[dict[str, Any]], shadow: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    support = deduplicate_rows(_all_rows(runs))
    rows = support.pop("rows")
    selection = select_policy(rows, shadow)
    model = {
        "schema_version": 1,
        "status": "frozen_pending_new_stream_confirmation",
        "label_family": LABEL_FAMILY,
        "axis": METRIC,
        "training_run_ids": [run["run_id"] for run in runs],
        "training_support": support,
        "model_selection": selection,
        "input_contract": (
            "source tensor plus candidate command/item geometry; immediate "
            "score, step, post-settle state, and future labels excluded"
        ),
        "knn_value_predictor": fit_knn(rows, selection),
    }
    development = {
        "schema_version": 1,
        "evaluation_kind": "group_complement_crossfit_unique_signatures",
        "training_run_ids": model["training_run_ids"],
        "support": support,
        "selected_result": selection["selected_result"],
        "claim": "Development evidence only; a new-stream confirmation is required.",
    }
    return model, development


def evaluate_v4(
    model: dict[str, Any], shadow: dict[str, Any], runs: list[dict[str, Any]],
    *, prospective: bool,
) -> dict[str, Any]:
    raw = [
        row for run in runs
        for row in _eligible(run["late"], METRIC, label_family=LABEL_FAMILY)
    ]
    support = deduplicate_rows(raw)
    rows = support.pop("rows")
    candidate, action, distances = predict_knn(
        model["knn_value_predictor"], shadow, rows
    )
    scored = _score_predictions(rows, candidate, action)
    result = {
        "schema_version": 1,
        "evaluation_kind": (
            "prospective_confirmation_unique_signatures"
            if prospective else "inspected_development_unique_signatures"
        ),
        "target_run_ids": [run["run_id"] for run in runs],
        "support": support,
        "distance_support": {
            "supported_rows": sum(
                distance <= model["knn_value_predictor"]["support_distance_threshold"]
                for distance in distances
            ),
            "support_distance_threshold": model["knn_value_predictor"]["support_distance_threshold"],
        },
        "correct": {
            "candidate": scored["candidate_correct"],
            "action_geometry": scored["action_geometry_correct"],
        },
        "paired_candidate_vs_action": {
            key: scored[key] for key in (
                "wins", "ties", "losses", "exact_two_sided_sign_p"
            )
        },
        "per_stream": scored["per_stream"],
    }
    if prospective:
        result["predeclared_confirmation_gate"] = confirmation_gate(
            result, contract="predeclared in distributional-fill-preaction-v4.md"
        )
        result["claim"] = (
            "Prospective confirmation passed; offline branch-direction candidate only."
            if result["predeclared_confirmation_gate"]["passed"] else
            "Prospective confirmation failed; the frozen candidate is rejected."
        )
    else:
        result["claim"] = "Development evidence only; target labels are inspected."
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--training-dir", action="append", type=pathlib.Path)
    parser.add_argument("--target-dir", action="append", type=pathlib.Path)
    parser.add_argument("--model", type=pathlib.Path)
    parser.add_argument("--shadow-model", type=pathlib.Path, required=True)
    parser.add_argument("--model-output", type=pathlib.Path)
    parser.add_argument("--development-output", type=pathlib.Path)
    parser.add_argument("--evaluation-output", type=pathlib.Path)
    parser.add_argument("--prospective", action="store_true")
    args = parser.parse_args()
    shadow = json.loads(args.shadow_model.read_text(encoding="utf-8"))
    if args.model:
        if args.training_dir or args.model_output or args.development_output:
            parser.error("--model forbids training outputs")
        if not args.target_dir or not args.evaluation_output:
            parser.error("--model requires --target-dir and --evaluation-output")
        model = json.loads(args.model.read_text(encoding="utf-8"))
    elif args.training_dir and args.model_output and args.development_output:
        runs = [load_run(path, label_family=LABEL_FAMILY) for path in args.training_dir]
        model, development = build_v4(runs, shadow)
        args.model_output.parent.mkdir(parents=True, exist_ok=True)
        args.development_output.parent.mkdir(parents=True, exist_ok=True)
        args.model_output.write_text(json.dumps(model, indent=2) + "\n", encoding="utf-8")
        args.development_output.write_text(
            json.dumps(development, indent=2) + "\n", encoding="utf-8"
        )
    else:
        parser.error("provide --model or complete training inputs and outputs")
    if args.target_dir:
        if not args.evaluation_output:
            parser.error("--target-dir requires --evaluation-output")
        target_runs = [load_run(path, label_family=LABEL_FAMILY) for path in args.target_dir]
        evaluation = evaluate_v4(model, shadow, target_runs, prospective=args.prospective)
        args.evaluation_output.parent.mkdir(parents=True, exist_ok=True)
        args.evaluation_output.write_text(
            json.dumps(evaluation, indent=2) + "\n", encoding="utf-8"
        )
    print(args.model_output or args.evaluation_output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
