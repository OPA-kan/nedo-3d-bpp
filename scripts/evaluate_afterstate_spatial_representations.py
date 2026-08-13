"""Audit spatial afterstate representations on held-out stream variants."""

from __future__ import annotations

import argparse
import json
import pathlib
import statistics
from typing import Any, Callable

import numpy as np

try:
    from scripts.evaluate_counterfactual_afterstate_value import (
        _eligible, _features, _predict_ridge, _state_block_delta, load_run,
    )
except ModuleNotFoundError:
    from evaluate_counterfactual_afterstate_value import (
        _eligible, _features, _predict_ridge, _state_block_delta, load_run,
    )


def _height_grid(state: dict[str, Any], size: int) -> list[float]:
    container_names = state["container_features"]
    packed_names = state["packed_item_features"]
    index = {name: position for position, name in enumerate(packed_names)}
    result = []
    for container_index in range(2):
        if container_index >= len(state["container_values"]):
            result.extend([0.0] * (size * size))
            continue
        container = state["container_values"][container_index]
        length = float(container[container_names.index("length")])
        width = float(container[container_names.index("width")])
        grid = np.zeros((size, size))
        for row in state["packed_item_values"]:
            if int(row[index["container_index"]]) != container_index:
                continue
            x, y, z = (
                float(row[index[name]])
                for name in ("local_x", "local_y", "local_z")
            )
            dimensions = np.asarray([
                float(row[index[name]])
                for name in ("length", "width", "height")
            ])
            if "quaternion_x" in index:
                qx, qy, qz, qw = (
                    float(row[index[name]])
                    for name in (
                        "quaternion_x", "quaternion_y", "quaternion_z",
                        "quaternion_w",
                    )
                )
            else:
                # Schema-v1 fixtures written before orientation was exported
                # describe axis-aligned packed items.
                qx, qy, qz, qw = 0.0, 0.0, 0.0, 1.0
            rotation = np.asarray([
                [1 - 2 * (qy * qy + qz * qz), 2 * (qx * qy - qz * qw),
                 2 * (qx * qz + qy * qw)],
                [2 * (qx * qy + qz * qw), 1 - 2 * (qx * qx + qz * qz),
                 2 * (qy * qz - qx * qw)],
                [2 * (qx * qz - qy * qw), 2 * (qy * qz + qx * qw),
                 1 - 2 * (qx * qx + qy * qy)],
            ])
            extent = np.abs(rotation) @ dimensions / 2.0
            x0, x1 = x - extent[0], x + extent[0]
            y0, y1 = y - extent[1], y + extent[1]
            top = z + extent[2]
            for row_index in range(size):
                cell_x0 = -length / 2 + row_index * length / size
                cell_x1 = -length / 2 + (row_index + 1) * length / size
                for column_index in range(size):
                    cell_y0 = -width / 2 + column_index * width / size
                    cell_y1 = -width / 2 + (column_index + 1) * width / size
                    if (
                        x1 > cell_x0 and x0 < cell_x1
                        and y1 > cell_y0 and y0 < cell_y1
                    ):
                        grid[row_index, column_index] = max(
                            grid[row_index, column_index], top
                        )
        result.extend(grid.ravel().tolist())
    return result


def _grid_delta(row: dict[str, Any], size: int) -> list[float]:
    lower = _height_grid(row["lower_afterstate_tensor"], size)
    higher = _height_grid(row["higher_afterstate_tensor"], size)
    return [right - left for left, right in zip(lower, higher)]


def _per_container_delta(row: dict[str, Any]) -> list[float]:
    def summary(state: dict[str, Any]) -> list[float]:
        names = state["packed_item_features"]
        container_column = names.index("container_index")
        result = []
        for container_index in range(2):
            values = [
                [float(value) for index, value in enumerate(item)
                 if index != container_column]
                for item in state["packed_item_values"]
                if int(item[container_column]) == container_index
            ]
            result.append(float(len(values)))
            if values:
                columns = list(zip(*values))
                result.extend(statistics.fmean(column) for column in columns)
                result.extend(statistics.pstdev(column) for column in columns)
                result.extend(min(column) for column in columns)
                result.extend(max(column) for column in columns)
            else:
                result.extend([0.0] * (4 * (len(names) - 1)))
        return result
    lower = summary(row["lower_afterstate_tensor"])
    higher = summary(row["higher_afterstate_tensor"])
    return [right - left for left, right in zip(lower, higher)]


def _knn(
    train: list[dict[str, Any]], test: list[dict[str, Any]], k: int,
) -> dict[str, str]:
    eligible = _eligible(train, "fill_score_proxy")
    values = np.asarray([_grid_delta(row, 4) for row in eligible])
    scales = np.std(values, axis=0)
    scales[scales == 0.0] = 1.0
    design = values / scales
    targets = np.asarray([
        1 if row["continuation_labels"]["fill_score_proxy"]["relation"]
        == "higher_afterstate_better" else -1
        for row in eligible
    ])
    predictions = {}
    for row in test:
        value = np.asarray(_grid_delta(row, 4)) / scales
        nearest = np.argsort(np.linalg.norm(design - value, axis=1))[:k]
        predictions[row["teacher_id"]] = (
            "higher_afterstate_better" if targets[nearest].sum() >= 0
            else "lower_afterstate_better"
        )
    return predictions


def evaluate(
    base_runs: list[dict[str, Any]], development_runs: list[dict[str, Any]],
) -> dict[str, Any]:
    feature_sets: dict[str, Callable[[dict[str, Any]], list[float]]] = {
        "pooled_packed": lambda row: _state_block_delta(row, "packed"),
        "pooled_packed_visible": lambda row: _state_block_delta(
            row, "packed_visible"
        ),
        "per_container_packed": _per_container_delta,
        "height_grid_4": lambda row: _grid_delta(row, 4),
        "height_grid_8": lambda row: _grid_delta(row, 8),
        "height_grid_4_plus_visible": lambda row: (
            _grid_delta(row, 4) + _state_block_delta(row, "packed_visible")[89:]
        ),
        "height_grid_4_plus_action": lambda row: (
            _grid_delta(row, 4)
            + _features(row, include_action=True, include_afterstate=False)
        ),
        "height_grid_4_plus_pooled": lambda row: (
            _grid_delta(row, 4) + _state_block_delta(row, "packed_visible")
        ),
    }
    totals = {name: 0 for name in feature_sets}
    totals.update({f"height_grid_4_knn_{k}": 0 for k in (1, 3, 5)})
    folds = []
    total_rows = 0
    for target in development_runs:
        train = [
            row
            for run in base_runs + [run for run in development_runs if run is not target]
            for row in run["discovery"]
        ]
        test = _eligible(target["late"], "fill_score_proxy")
        predictions = {
            name: _predict_ridge(
                train, test, "fill_score_proxy", features
            )
            for name, features in feature_sets.items()
        }
        predictions.update({
            f"height_grid_4_knn_{k}": _knn(train, test, k)
            for k in (1, 3, 5)
        })
        correct = {}
        for name, values in predictions.items():
            correct[name] = sum(
                values[row["teacher_id"]]
                == row["continuation_labels"]["fill_score_proxy"]["relation"]
                for row in test
            )
            totals[name] += correct[name]
        total_rows += len(test)
        folds.append({
            "target_run_id": target["run_id"],
            "directional_rows": len(test),
            "correct": correct,
        })
    best = max(totals.values()) if totals else 0
    return {
        "schema_version": 1,
        "split_contract": "each development stream variant held out in full",
        "total_directional_rows": total_rows,
        "models": {
            name: {"correct": value, "total": total_rows}
            for name, value in totals.items()
        },
        "best_correct": best,
        "best_models": [name for name, value in totals.items() if value == best],
        "zero_error_representation_found": best == total_rows,
        "folds": folds,
        "claim": (
            "Development representation audit. All attempted representations "
            "are reported; sealed confirmation runs are not inputs."
        ),
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Spatial afterstate representation audit", "",
        f"- Directional rows: {report['total_directional_rows']}",
        f"- Best: {report['best_correct']}/{report['total_directional_rows']} "
        f"({', '.join(report['best_models'])})",
        f"- Zero-error representation found: "
        f"{'yes' if report['zero_error_representation_found'] else 'no'}",
        "", "| Representation | Correct |", "|---|---:|",
    ]
    for name, row in report["models"].items():
        lines.append(f"| {name} | {row['correct']}/{row['total']} |")
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
