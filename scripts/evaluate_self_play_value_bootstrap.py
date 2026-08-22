"""Group-held-out ridge audit for leakage-free Self-Play value targets."""

from __future__ import annotations

import argparse
import json
import math
import pathlib
from typing import Any

import numpy as np


def _set_summary(values: list[list[float]], width: int) -> list[float]:
    if not values:
        return [0.0] * (4 * width)
    array = np.asarray(values, dtype=float)
    return np.concatenate((
        array.mean(axis=0), array.std(axis=0),
        array.min(axis=0), array.max(axis=0),
    )).tolist()


def feature_vector(row: dict[str, Any], *, board: bool) -> list[float]:
    state = row["state"]
    game = row["game_features"]
    base = [
        1.0 if int(game["player_to_move"]) == 0 else -1.0,
        float(game["block_length"]),
        float(game["handoff_count"]),
        float(state["container_count"]),
        float(state["packed_item_count"]),
        float(state["visible_item_count"]),
    ]
    if not board:
        return base
    groups = (
        (state["container_values"], len(state["container_features"])),
        (state["packed_item_values"], len(state["packed_item_features"])),
        (state["visible_item_values"], len(state["visible_item_features"])),
    )
    for values, width in groups:
        base.extend(_set_summary(values, width))
    return base


def _ridge_predict(
    train_x: np.ndarray, train_y: np.ndarray, test_x: np.ndarray,
    *, alpha: float,
) -> np.ndarray:
    mean = train_x.mean(axis=0)
    scale = train_x.std(axis=0)
    scale[scale < 1e-9] = 1.0
    x = (train_x - mean) / scale
    test = (test_x - mean) / scale
    target_mean = float(train_y.mean())
    centered = train_y - target_mean
    coefficient = np.linalg.solve(
        x.T @ x + alpha * np.eye(x.shape[1]), x.T @ centered
    )
    return target_mean + test @ coefficient


def _metrics(actual: np.ndarray, predicted: np.ndarray) -> dict[str, float]:
    error = predicted - actual
    if len(actual) > 1 and np.std(actual) > 0 and np.std(predicted) > 0:
        correlation = float(np.corrcoef(actual, predicted)[0, 1])
    else:
        correlation = 0.0
    nonzero = np.abs(actual) > 1e-9
    sign_accuracy = (
        float(np.mean(np.sign(actual[nonzero]) == np.sign(predicted[nonzero])))
        if np.any(nonzero) else 0.0
    )
    return {
        "rmse": float(math.sqrt(np.mean(error * error))),
        "mae": float(np.mean(np.abs(error))),
        "pearson": correlation,
        "sign_accuracy": sign_accuracy,
    }


def evaluate(rows: list[dict[str, Any]], *, alpha: float = 10.0) -> dict[str, Any]:
    rows = [row for row in rows if row.get("value_target_eligible")]
    groups = sorted({str(row["trajectory_group"]) for row in rows})
    if len(groups) < 2:
        raise ValueError("value audit needs at least two trajectory groups")
    actual = np.asarray([float(row["return_to_go"]) for row in rows])
    phase_x = np.asarray([feature_vector(row, board=False) for row in rows])
    board_x = np.asarray([feature_vector(row, board=True) for row in rows])
    row_groups = np.asarray([str(row["trajectory_group"]) for row in rows])
    predictions = {
        "constant": np.zeros(len(rows)),
        "phase_count_ridge": np.zeros(len(rows)),
        "board_set_summary_ridge": np.zeros(len(rows)),
    }
    for group in groups:
        test = row_groups == group
        train = ~test
        predictions["constant"][test] = float(actual[train].mean())
        predictions["phase_count_ridge"][test] = _ridge_predict(
            phase_x[train], actual[train], phase_x[test], alpha=alpha
        )
        predictions["board_set_summary_ridge"][test] = _ridge_predict(
            board_x[train], actual[train], board_x[test], alpha=alpha
        )
    metrics = {
        name: _metrics(actual, predicted)
        for name, predicted in predictions.items()
    }
    board_gain = (
        metrics["phase_count_ridge"]["rmse"]
        - metrics["board_set_summary_ridge"]["rmse"]
    )
    return {
        "schema_version": 1,
        "protocol": "leave_one_trajectory_group_out_fixed_ridge_alpha",
        "ridge_alpha": alpha,
        "rows": len(rows),
        "trajectory_groups": len(groups),
        "metrics": metrics,
        "board_rmse_gain_over_phase_count": board_gain,
        "board_signal_observed": board_gain > 0.0,
        "deployment_ready": False,
        "note": (
            "Diagnostic bootstrap only; no hyperparameter selection or "
            "fresh policy-generation holdout has been performed."
        ),
    }


def markdown(result: dict[str, Any]) -> str:
    lines = [
        "# Self-Play value bootstrap audit", "",
        f"- rows: {result['rows']}",
        f"- trajectory groups: {result['trajectory_groups']}",
        f"- ridge alpha: {result['ridge_alpha']}",
        "", "| model | RMSE | MAE | Pearson | sign accuracy |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for name, metrics in result["metrics"].items():
        lines.append(
            f"| {name} | {metrics['rmse']:.6f} | {metrics['mae']:.6f} | "
            f"{metrics['pearson']:.6f} | {metrics['sign_accuracy']:.6f} |"
        )
    lines.extend([
        "",
        (
            "- board RMSE gain over phase/count: "
            f"{result['board_rmse_gain_over_phase_count']:+.6f}"
        ),
        f"- board signal observed: {result['board_signal_observed']}",
        f"- deployment ready: {result['deployment_ready']}",
        "", result["note"], "",
    ])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=pathlib.Path, required=True)
    parser.add_argument("--json-output", type=pathlib.Path, required=True)
    parser.add_argument("--markdown-output", type=pathlib.Path, required=True)
    parser.add_argument("--ridge-alpha", type=float, default=10.0)
    args = parser.parse_args()
    with args.dataset.open("r", encoding="utf-8") as handle:
        rows = [json.loads(line) for line in handle if line.strip()]
    result = evaluate(rows, alpha=args.ridge_alpha)
    args.json_output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    args.markdown_output.write_text(markdown(result), encoding="utf-8")
    print(args.markdown_output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
