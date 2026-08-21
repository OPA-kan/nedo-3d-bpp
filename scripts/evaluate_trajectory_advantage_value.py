"""Evaluate direct trajectory-advantage heads with whole-trajectory holdout."""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import statistics
from typing import Any

import numpy as np

try:
    from scripts.evaluate_counterfactual_teacher_baseline import _set_summary
except ModuleNotFoundError:  # direct `python scripts/...py` execution
    from evaluate_counterfactual_teacher_baseline import _set_summary


VIEWS = ("action", "afterstate", "action_afterstate")
PRIMARY_HEAD = "fill_score_proxy"
DEVELOPMENT_GATE = {
    "minimum_directional_fill_rows": 100,
    "minimum_afterstate_accuracy": 0.65,
    "minimum_afterstate_gain_over_action": 0.05,
    "minimum_unseen_afterstate_rows": 50,
    "minimum_unseen_afterstate_accuracy": 0.60,
}


def _ridge_weights(
    design: np.ndarray, target: np.ndarray, l2: float,
) -> np.ndarray:
    """Solve in the smaller of feature space and sample space."""
    if design.shape[1] <= design.shape[0]:
        return np.linalg.solve(
            design.T @ design + l2 * np.eye(design.shape[1]),
            design.T @ target,
        )
    return design.T @ np.linalg.solve(
        design @ design.T + l2 * np.eye(design.shape[0]), target
    )


def _tensor_delta(
    incumbent: dict[str, Any], candidate: dict[str, Any], *, teacher_id: str,
) -> list[float]:
    if incumbent.get("feature_names") != candidate.get("feature_names"):
        raise ValueError(f"tensor feature mismatch in {teacher_id}")
    left = [float(value) for value in incumbent["values"]]
    right = [float(value) for value in candidate["values"]]
    if len(left) != len(right):
        raise ValueError(f"tensor width mismatch in {teacher_id}")
    return [candidate_value - incumbent_value for incumbent_value, candidate_value in zip(left, right)]


def feature_vector(row: dict[str, Any], view: str) -> list[float]:
    if view not in VIEWS:
        raise ValueError(f"unsupported feature view: {view}")
    values = []
    if view in ("action", "action_afterstate"):
        values.extend(_tensor_delta(
            row["incumbent_action_tensor"], row["candidate_action_tensor"],
            teacher_id=row["teacher_id"],
        ))
    if view in ("afterstate", "action_afterstate"):
        incumbent = _set_summary(row["incumbent_afterstate_tensor"])
        candidate = _set_summary(row["candidate_afterstate_tensor"])
        if len(incumbent) != len(candidate):
            raise ValueError(f"afterstate width mismatch in {row['teacher_id']}")
        values.extend([
            candidate_value - incumbent_value
            for incumbent_value, candidate_value in zip(incumbent, candidate)
        ])
    return values


def _eligible(rows: list[dict[str, Any]], metric: str) -> list[dict[str, Any]]:
    return [row for row in rows if metric in row.get("advantage_heads", {})]


def fit_ridge(
    rows: list[dict[str, Any]], metric: str, view: str, *, l2: float = 1.0,
) -> dict[str, Any]:
    rows = _eligible(rows, metric)
    if not rows:
        raise ValueError(f"no training rows for {metric}")
    raw = [feature_vector(row, view) for row in rows]
    scales = np.asarray([
        statistics.pstdev(column) or 1.0 for column in zip(*raw)
    ])
    design = np.asarray(raw, dtype=float) / scales
    target = np.asarray([
        float(row["advantage_heads"][metric]["directed_advantage"])
        for row in rows
    ])
    weights = _ridge_weights(design, target, l2)
    return {
        "metric": metric,
        "view": view,
        "l2": l2,
        "training_rows": len(rows),
        "scales": scales,
        "weights": weights,
    }


def predict(model: dict[str, Any], row: dict[str, Any]) -> float:
    values = np.asarray(feature_vector(row, model["view"]), dtype=float)
    if len(values) != len(model["scales"]):
        raise ValueError("model feature width mismatch")
    return float(np.dot(values / model["scales"], model["weights"]))


def _signature(row: dict[str, Any], view: str) -> tuple[float, ...]:
    return tuple(round(value, 12) for value in feature_vector(row, view))


def evaluate_metric(
    rows: list[dict[str, Any]], metric: str, view: str,
) -> dict[str, Any]:
    eligible = _eligible(rows, metric)
    groups = sorted({row["split_group_id"] for row in eligible})
    records = []
    group_rows = collections.Counter()
    group_correct = collections.Counter()
    for group in groups:
        train = [row for row in eligible if row["split_group_id"] != group]
        test = [row for row in eligible if row["split_group_id"] == group]
        if not train or not test:
            continue
        model = fit_ridge(train, metric, view)
        training_signatures = {_signature(row, view) for row in train}
        for row in test:
            head = row["advantage_heads"][metric]
            target = float(head["directed_advantage"])
            prediction = predict(model, row)
            directional = head["relation"] != "equal"
            correct = directional and ((prediction > 0.0) == (target > 0.0))
            if directional:
                group_rows[group] += 1
                group_correct[group] += int(correct)
            records.append({
                "teacher_id": row["teacher_id"],
                "group": group,
                "target": target,
                "prediction": prediction,
                "directional": directional,
                "correct": correct,
                "unseen_signature": _signature(row, view) not in training_signatures,
            })
    directional = [record for record in records if record["directional"]]
    unseen = [record for record in directional if record["unseen_signature"]]
    return {
        "view": view,
        "held_out_unit": "split_group_id",
        "group_count": len(groups),
        "row_count": len(records),
        "directional_rows": len(directional),
        "directional_correct": sum(record["correct"] for record in directional),
        "directional_accuracy": (
            sum(record["correct"] for record in directional) / len(directional)
            if directional else None
        ),
        "always_candidate_accuracy": (
            sum(record["target"] > 0.0 for record in directional) / len(directional)
            if directional else None
        ),
        "always_incumbent_accuracy": (
            sum(record["target"] < 0.0 for record in directional) / len(directional)
            if directional else None
        ),
        "unseen_signature_rows": len(unseen),
        "unseen_signature_correct": sum(record["correct"] for record in unseen),
        "unseen_signature_accuracy": (
            sum(record["correct"] for record in unseen) / len(unseen)
            if unseen else None
        ),
        "mean_absolute_error": (
            statistics.fmean(abs(record["prediction"] - record["target"]) for record in records)
            if records else None
        ),
        "per_group_directional": {
            group: {
                "rows": group_rows[group],
                "correct": group_correct[group],
                "accuracy": (
                    group_correct[group] / group_rows[group]
                    if group_rows[group] else None
                ),
            }
            for group in groups
        },
    }


def _evaluate_all_metrics(
    rows: list[dict[str, Any]], metrics: list[str], view: str,
) -> dict[str, dict[str, Any]]:
    """Reuse one group/view matrix solve for every independent target head."""
    groups = sorted({row["split_group_id"] for row in rows})
    records = {metric: [] for metric in metrics}
    for group in groups:
        train = [row for row in rows if row["split_group_id"] != group]
        test = [row for row in rows if row["split_group_id"] == group]
        if not train or not test:
            continue
        raw_train = [feature_vector(row, view) for row in train]
        scales = np.asarray([
            statistics.pstdev(column) or 1.0 for column in zip(*raw_train)
        ])
        design = np.asarray(raw_train, dtype=float) / scales
        targets = np.asarray([
            [
                float(row["advantage_heads"][metric]["directed_advantage"])
                for metric in metrics
            ]
            for row in train
        ])
        weights = _ridge_weights(design, targets, 1.0)
        test_design = np.asarray([
            feature_vector(row, view) for row in test
        ], dtype=float) / scales
        predictions = test_design @ weights
        training_signatures = {_signature(row, view) for row in train}
        for row_index, row in enumerate(test):
            unseen = _signature(row, view) not in training_signatures
            for metric_index, metric in enumerate(metrics):
                head = row["advantage_heads"][metric]
                target = float(head["directed_advantage"])
                prediction = float(predictions[row_index, metric_index])
                directional = head["relation"] != "equal"
                records[metric].append({
                    "teacher_id": row["teacher_id"],
                    "group": group,
                    "target": target,
                    "prediction": prediction,
                    "directional": directional,
                    "correct": directional and (
                        (prediction > 0.0) == (target > 0.0)
                    ),
                    "unseen_signature": unseen,
                })

    results = {}
    for metric, metric_records in records.items():
        directional = [row for row in metric_records if row["directional"]]
        unseen = [row for row in directional if row["unseen_signature"]]
        per_group = {}
        for group in groups:
            selected = [row for row in directional if row["group"] == group]
            per_group[group] = {
                "rows": len(selected),
                "correct": sum(row["correct"] for row in selected),
                "accuracy": (
                    sum(row["correct"] for row in selected) / len(selected)
                    if selected else None
                ),
            }
        results[metric] = {
            "view": view,
            "held_out_unit": "split_group_id",
            "group_count": len(groups),
            "row_count": len(metric_records),
            "directional_rows": len(directional),
            "directional_correct": sum(row["correct"] for row in directional),
            "directional_accuracy": (
                sum(row["correct"] for row in directional) / len(directional)
                if directional else None
            ),
            "always_candidate_accuracy": (
                sum(row["target"] > 0.0 for row in directional) / len(directional)
                if directional else None
            ),
            "always_incumbent_accuracy": (
                sum(row["target"] < 0.0 for row in directional) / len(directional)
                if directional else None
            ),
            "unseen_signature_rows": len(unseen),
            "unseen_signature_correct": sum(row["correct"] for row in unseen),
            "unseen_signature_accuracy": (
                sum(row["correct"] for row in unseen) / len(unseen)
                if unseen else None
            ),
            "mean_absolute_error": statistics.fmean(
                abs(row["prediction"] - row["target"])
                for row in metric_records
            ),
            "per_group_directional": per_group,
        }
    return results


def evaluate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    metrics = sorted(set.intersection(*(
        set(row.get("advantage_heads", {})) for row in rows
    ))) if rows else []
    by_view = {
        view: _evaluate_all_metrics(rows, metrics, view) for view in VIEWS
    }
    results = {
        metric: {view: by_view[view][metric] for view in VIEWS}
        for metric in metrics
    }
    fill = results.get(PRIMARY_HEAD, {})
    action = fill.get("action", {})
    afterstate = fill.get("afterstate", {})
    directional = int(afterstate.get("directional_rows") or 0)
    afterstate_accuracy = afterstate.get("directional_accuracy")
    action_accuracy = action.get("directional_accuracy")
    unseen_rows = int(afterstate.get("unseen_signature_rows") or 0)
    unseen_accuracy = afterstate.get("unseen_signature_accuracy")
    checks = {
        "directional_fill_rows": directional >= DEVELOPMENT_GATE[
            "minimum_directional_fill_rows"
        ],
        "afterstate_accuracy": (
            afterstate_accuracy is not None
            and afterstate_accuracy >= DEVELOPMENT_GATE["minimum_afterstate_accuracy"]
        ),
        "gain_over_action": (
            afterstate_accuracy is not None and action_accuracy is not None
            and afterstate_accuracy - action_accuracy >= DEVELOPMENT_GATE[
                "minimum_afterstate_gain_over_action"
            ]
        ),
        "unseen_afterstate_rows": unseen_rows >= DEVELOPMENT_GATE[
            "minimum_unseen_afterstate_rows"
        ],
        "unseen_afterstate_accuracy": (
            unseen_accuracy is not None
            and unseen_accuracy >= DEVELOPMENT_GATE[
                "minimum_unseen_afterstate_accuracy"
            ]
        ),
    }
    return {
        "schema_version": 1,
        "evaluation": "whole-trajectory-group leave-one-out ridge",
        "target": "directed physical trajectory advantage; no weighted total",
        "row_count": len(rows),
        "group_count": len({row["split_group_id"] for row in rows}),
        "metrics": results,
        "development_gate": DEVELOPMENT_GATE,
        "development_gate_checks": checks,
        "development_gate_passed": all(checks.values()),
        "claim_limit": (
            "retrospective learnability only; no policy or score improvement"
        ),
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Trajectory advantage value development", "",
        f"- rows: {report['row_count']}",
        f"- trajectory groups: {report['group_count']}",
        f"- development gate: {'PASS' if report['development_gate_passed'] else 'FAIL'}",
        "", "| head | view | directional | accuracy | unseen accuracy | MAE |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for metric, views in report["metrics"].items():
        for view, result in views.items():
            accuracy = result["directional_accuracy"]
            unseen = result["unseen_signature_accuracy"]
            lines.append(
                f"| {metric} | {view} | {result['directional_rows']} | "
                f"{accuracy if accuracy is not None else 'n/a'} | "
                f"{unseen if unseen is not None else 'n/a'} | "
                f"{result['mean_absolute_error']} |"
            )
    lines.extend(["", report["claim_limit"], ""])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=pathlib.Path, required=True)
    parser.add_argument("--json-output", type=pathlib.Path, required=True)
    parser.add_argument("--markdown-output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    rows = [
        json.loads(line) for line in args.dataset.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    report = evaluate(rows)
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    args.markdown_output.write_text(render_markdown(report), encoding="utf-8")
    print(args.markdown_output)


if __name__ == "__main__":
    main()
