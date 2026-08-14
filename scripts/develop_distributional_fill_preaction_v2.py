"""Develop a signature-deduplicated, stream-held-out pre-action student."""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
from typing import Any

import numpy as np

try:
    from scripts.build_distributional_fill_preaction_student import (
        LABEL_FAMILY,
        METRIC,
        PAIRWISE_L2_GRID,
        _action_delta,
        _fit_pairwise,
        _preaction_signature,
        _predict_pairwise,
        _score_pairwise,
        _relation,
    )
    from scripts.evaluate_counterfactual_afterstate_value import (
        _eligible,
        _exact_two_sided_sign_p,
        load_run,
    )
except ModuleNotFoundError:
    from build_distributional_fill_preaction_student import (
        LABEL_FAMILY,
        METRIC,
        PAIRWISE_L2_GRID,
        _action_delta,
        _fit_pairwise,
        _preaction_signature,
        _predict_pairwise,
        _score_pairwise,
        _relation,
    )
    from evaluate_counterfactual_afterstate_value import (
        _eligible,
        _exact_two_sided_sign_p,
        load_run,
    )


def _target(row: dict[str, Any]) -> str:
    return str(row[LABEL_FAMILY][METRIC]["relation"])


def deduplicate_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for row in rows:
        groups[_preaction_signature(row)].append(row)
    conflicts = [
        group for group in groups.values()
        if len({_target(row) for row in group}) > 1
    ]
    if conflicts:
        raise ValueError(
            f"{len(conflicts)} exact pre-action signatures have conflicting labels"
        )
    unique = []
    for group in groups.values():
        representative = dict(group[0])
        representative["_preaction_stream_variants"] = sorted({
            str(row["scenario_axes"]["stream_variant"]) for row in group
        })
        unique.append(representative)
    return {
        "raw_rows": len(rows),
        "unique_rows": len(unique),
        "unique_fraction": len(unique) / len(rows) if rows else 0.0,
        "rows": unique,
    }


def _stream(row: dict[str, Any]) -> str:
    return str(row["scenario_axes"]["stream_variant"])


def _streams(row: dict[str, Any]) -> tuple[str, ...]:
    return tuple(row.get("_preaction_stream_variants", (_stream(row),)))


OVERRIDE_RATIO_GRID = (0.0, 0.5, 1.0, 2.0, 4.0, 8.0, 16.0, 1e30)


def _action_scores(
    shadow: dict[str, Any], rows: list[dict[str, Any]],
) -> list[float]:
    model = shadow["models"]["action_geometry"]
    scales = np.asarray(model["scales"], dtype=float)
    weights = np.asarray(model["weights"], dtype=float)
    return [
        float(np.dot(np.asarray(_action_delta(row)) / scales, weights))
        for row in rows
    ]


def _hybrid_predictions(
    student_scores: list[float], action_scores: list[float], threshold: float,
) -> list[str]:
    output = []
    for student_score, action_score in zip(student_scores, action_scores):
        use_student = (
            (student_score >= 0.0) != (action_score >= 0.0)
            and abs(student_score) / max(abs(action_score), 1e-12) >= threshold
        )
        score = student_score if use_student else action_score
        output.append(
            "higher_afterstate_better" if score >= 0.0
            else "lower_afterstate_better"
        )
    return output


def select_policy_by_stream(
    rows: list[dict[str, Any]], shadow: dict[str, Any],
) -> dict[str, Any]:
    streams = sorted({stream for row in rows for stream in _streams(row)})
    if len(streams) < 2:
        raise ValueError("stream-held-out selection requires at least two streams")
    grid = []
    for l2 in PAIRWISE_L2_GRID:
        fold_outputs = []
        for stream in streams:
            train = [row for row in rows if stream not in _streams(row)]
            test = [row for row in rows if stream in _streams(row)]
            fold_outputs.append({
                "stream_variant": stream,
                "rows": test,
                "student_scores": _score_pairwise(_fit_pairwise(train, l2), test),
                "action_scores": _action_scores(shadow, test),
            })
        for threshold in OVERRIDE_RATIO_GRID:
            per_stream = []
            for fold in fold_outputs:
                predictions = _hybrid_predictions(
                    fold["student_scores"], fold["action_scores"], threshold
                )
                action_predictions = [
                    "higher_afterstate_better" if score >= 0.0
                    else "lower_afterstate_better"
                    for score in fold["action_scores"]
                ]
                candidate_correct = sum(
                    prediction == _target(row)
                    for prediction, row in zip(predictions, fold["rows"])
                )
                action_correct = sum(
                    prediction == _target(row)
                    for prediction, row in zip(action_predictions, fold["rows"])
                )
                per_stream.append({
                    "stream_variant": fold["stream_variant"],
                    "rows": len(fold["rows"]),
                    "candidate_correct": candidate_correct,
                    "action_correct": action_correct,
                })
            candidate_correct = sum(row["candidate_correct"] for row in per_stream)
            action_correct = sum(row["action_correct"] for row in per_stream)
            grid.append({
                "l2": l2, "override_ratio_threshold": threshold,
                "rows": sum(row["rows"] for row in per_stream),
                "candidate_correct": candidate_correct,
                "action_correct": action_correct,
                "all_streams_nonregressing": all(
                    row["candidate_correct"] >= row["action_correct"]
                    for row in per_stream
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
            item["candidate_correct"], item["override_ratio_threshold"], item["l2"]
        ),
    )
    return {
        "selection": (
            "leave_one_stream_variant_out_unique-signature accuracy with "
            "per-stream nonregression"
        ),
        "grid": grid,
        "selected_l2": selected["l2"],
        "selected_override_ratio_threshold": selected[
            "override_ratio_threshold"
        ],
        "selected_improves_action": (
            selected["candidate_correct"] > selected["action_correct"]
        ),
    }


def build_v2(
    runs: list[dict[str, Any]], shadow: dict[str, Any],
) -> dict[str, Any]:
    raw = [
        row for run in runs
        for row in _eligible(
            run["discovery"], METRIC, label_family=LABEL_FAMILY
        )
    ]
    deduplicated = deduplicate_rows(raw)
    selection = select_policy_by_stream(deduplicated["rows"], shadow)
    return {
        "schema_version": 2,
        "status": "development_signature_deduplicated_student",
        "label_family": LABEL_FAMILY,
        "axis": METRIC,
        "training_run_ids": [run["run_id"] for run in runs],
        "training_support": {
            name: value for name, value in deduplicated.items() if name != "rows"
        },
        "model_selection": selection,
        "input_contract": (
            "exact source observed-set summary plus candidate action-geometry "
            "delta without immediate score"
        ),
        "pairwise_value_predictor": _fit_pairwise(
            deduplicated["rows"], selection["selected_l2"]
        ),
        "decision": (
            "use student only when it disagrees with action geometry and its "
            "absolute margin divided by the action margin meets the frozen "
            "override ratio; otherwise use action geometry"
        ),
    }


def evaluate_unique(
    candidate: dict[str, Any], incumbent: dict[str, Any],
    shadow: dict[str, Any], runs: list[dict[str, Any]],
) -> dict[str, Any]:
    raw = [
        row for run in runs
        for row in _eligible(run["late"], METRIC, label_family=LABEL_FAMILY)
    ]
    support = deduplicate_rows(raw)
    rows = support["rows"]
    candidate_predictions = _hybrid_predictions(
        _score_pairwise(candidate["pairwise_value_predictor"], rows),
        _action_scores(shadow, rows),
        candidate["model_selection"]["selected_override_ratio_threshold"],
    )
    incumbent_predictions = _predict_pairwise(
        incumbent["pairwise_value_predictor"], rows
    )
    action_predictions = [
        _relation(shadow["models"]["action_geometry"], _action_delta(row))
        for row in rows
    ]
    systems = {
        "candidate": candidate_predictions,
        "v1": incumbent_predictions,
        "action_geometry": action_predictions,
    }
    correct = {
        name: sum(prediction == _target(row) for prediction, row in zip(values, rows))
        for name, values in systems.items()
    }
    paired = {}
    for baseline in ("v1", "action_geometry"):
        wins = ties = losses = 0
        for candidate_prediction, baseline_prediction, row in zip(
            candidate_predictions, systems[baseline], rows
        ):
            candidate_correct = candidate_prediction == _target(row)
            baseline_correct = baseline_prediction == _target(row)
            if candidate_correct and not baseline_correct:
                wins += 1
            elif baseline_correct and not candidate_correct:
                losses += 1
            else:
                ties += 1
        paired[baseline] = {
            "wins": wins, "ties": ties, "losses": losses,
            "exact_two_sided_sign_p": _exact_two_sided_sign_p(wins, losses),
        }
    per_stream = []
    for stream in sorted({item for row in rows for item in _streams(row)}):
        indices = [
            index for index, row in enumerate(rows) if stream in _streams(row)
        ]
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
    return {
        "schema_version": 1,
        "evaluation_kind": "inspected_development_unique_signatures",
        "target_run_ids": [run["run_id"] for run in runs],
        "support": {name: value for name, value in support.items() if name != "rows"},
        "correct": correct,
        "paired_candidate_vs": paired,
        "per_stream": per_stream,
        "claim": (
            "Development comparison only. Every target run is inspected and "
            "cannot confirm a frozen v2 candidate."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--teacher-dir", action="append", type=pathlib.Path, required=True)
    parser.add_argument("--v1-model", type=pathlib.Path, required=True)
    parser.add_argument("--shadow-model", type=pathlib.Path, required=True)
    parser.add_argument("--model-output", type=pathlib.Path, required=True)
    parser.add_argument("--evaluation-output", type=pathlib.Path, required=True)
    parser.add_argument(
        "--status", default="development_signature_deduplicated_student",
        choices=(
            "development_signature_deduplicated_student",
            "frozen_pending_new_stream_confirmation",
        ),
    )
    args = parser.parse_args()
    runs = [load_run(path, label_family=LABEL_FAMILY) for path in args.teacher_dir]
    incumbent = json.loads(args.v1_model.read_text(encoding="utf-8"))
    shadow = json.loads(args.shadow_model.read_text(encoding="utf-8"))
    candidate = build_v2(runs, shadow)
    candidate["status"] = args.status
    evaluation = evaluate_unique(candidate, incumbent, shadow, runs)
    args.model_output.parent.mkdir(parents=True, exist_ok=True)
    args.model_output.write_text(
        json.dumps(candidate, indent=2) + "\n", encoding="utf-8"
    )
    args.evaluation_output.parent.mkdir(parents=True, exist_ok=True)
    args.evaluation_output.write_text(
        json.dumps(evaluation, indent=2) + "\n", encoding="utf-8"
    )
    print(args.evaluation_output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
