#!/usr/bin/env python3
"""Develop the v6 pre-action student on stamped-height-grid geometry.

The 116-feature local-geometry family (v3-v5) is closed after a powered
prospective rejection. This candidate tests a different representation
hypothesis: predict each candidate's post-placement container height grid by
stamping its oriented commanded box onto the shared source-state grid with a
drop-to-rest approximation, and learn from the pairwise grid difference plus
the action-geometry delta. Immediate score, step, post-settle state, and
future labels remain excluded, so the input stays pre-action and label-blind.
"""

from __future__ import annotations

import argparse
import json
import pathlib
from typing import Any, Callable

import numpy as np

try:
    from .develop_distributional_fill_preaction_v2 import (
        _action_scores,
        deduplicate_rows,
    )
    from .build_distributional_fill_preaction_student import _action_delta
    from .develop_distributional_fill_preaction_v3 import (
        LABEL_FAMILY,
        METRIC,
        _oriented_action,
    )
    from .develop_distributional_fill_preaction_v4 import (
        K_GRID,
        OVERRIDE_RATIO_GRID,
        SUPPORT_QUANTILE_GRID,
        WEIGHTED_GRID,
        _all_rows,
        _neighbor_score,
        _score_predictions,
        _squared_distances,
        _standardize_fit,
        group_complement_indices,
    )
    from .develop_distributional_fill_preaction_v2 import _hybrid_predictions
    from .develop_distributional_fill_preaction_v5 import (
        minimum_powered_discordant,
    )
    from .evaluate_afterstate_spatial_representations import _height_grid
    from .evaluate_counterfactual_afterstate_value import load_run
except ImportError:
    from develop_distributional_fill_preaction_v2 import (
        _action_scores,
        _hybrid_predictions,
        deduplicate_rows,
    )
    from build_distributional_fill_preaction_student import _action_delta
    from develop_distributional_fill_preaction_v3 import (
        LABEL_FAMILY,
        METRIC,
        _oriented_action,
    )
    from develop_distributional_fill_preaction_v4 import (
        K_GRID,
        OVERRIDE_RATIO_GRID,
        SUPPORT_QUANTILE_GRID,
        WEIGHTED_GRID,
        _all_rows,
        _neighbor_score,
        _score_predictions,
        _squared_distances,
        _standardize_fit,
        group_complement_indices,
    )
    from develop_distributional_fill_preaction_v5 import (
        minimum_powered_discordant,
    )
    from evaluate_afterstate_spatial_representations import _height_grid
    from evaluate_counterfactual_afterstate_value import load_run


GRID_SIZE = 4


def _stamped_grid(
    source_grid: list[float], state: dict[str, Any], action: dict[str, Any],
    *, size: int = GRID_SIZE,
) -> tuple[list[float], float]:
    """Predict the post-placement height grid without physics.

    The oriented commanded box drops onto the highest cell under its
    footprint; every footprint cell rises to that rest top. Returns the
    stamped grid and the predicted rest top.
    """
    oriented = _oriented_action(action)
    names = oriented["feature_names"]
    value = {name: float(oriented["values"][names.index(name)]) for name in (
        "container_index", "command_x", "command_y", "length", "width", "height",
    )}
    container_index = int(round(value["container_index"]))
    grid = [list(row) for row in np.asarray(source_grid).reshape(2, size, size)]
    if container_index not in (0, 1):
        return [cell for plane in grid for row in plane for cell in row], 0.0
    container_names = state["container_features"]
    container = state["container_values"][container_index]
    container_length = float(container[container_names.index("length")])
    container_width = float(container[container_names.index("width")])
    x0 = value["command_x"] - value["length"] / 2.0
    x1 = value["command_x"] + value["length"] / 2.0
    y0 = value["command_y"] - value["width"] / 2.0
    y1 = value["command_y"] + value["width"] / 2.0
    footprint = []
    for row_index in range(size):
        cell_x0 = -container_length / 2 + row_index * container_length / size
        cell_x1 = -container_length / 2 + (row_index + 1) * container_length / size
        for column_index in range(size):
            cell_y0 = -container_width / 2 + column_index * container_width / size
            cell_y1 = -container_width / 2 + (column_index + 1) * container_width / size
            if x1 > cell_x0 and x0 < cell_x1 and y1 > cell_y0 and y0 < cell_y1:
                footprint.append((row_index, column_index))
    rest_base = max(
        (grid[container_index][row][column] for row, column in footprint),
        default=0.0,
    )
    rest_top = rest_base + value["height"]
    for row, column in footprint:
        grid[container_index][row][column] = max(
            grid[container_index][row][column], rest_top
        )
    return [cell for plane in grid for row in plane for cell in row], rest_top


def grid_pair_vector(row: dict[str, Any]) -> list[float]:
    state = row["source_state_tensor"]
    source = _height_grid(state, GRID_SIZE)
    lower, lower_top = _stamped_grid(source, state, row["lower_action_tensor"])
    higher, higher_top = _stamped_grid(source, state, row["higher_action_tensor"])
    delta = [right - left for left, right in zip(lower, higher)]
    summaries = [
        higher_top - lower_top,
        max(higher) - max(lower),
        sum(higher) - sum(lower),
        float(np.std(higher) - np.std(lower)),
    ]
    return _action_delta(row) + delta + summaries


def _prepare_crossfit(
    rows: list[dict[str, Any]], shadow: dict[str, Any],
    vector: Callable[[dict[str, Any]], list[float]],
) -> list[dict[str, Any]]:
    values = np.asarray([vector(row) for row in rows], dtype=float)
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


def _target(row: dict[str, Any]) -> str:
    return str(row[LABEL_FAMILY][METRIC]["relation"])


def select_policy(
    rows: list[dict[str, Any]], shadow: dict[str, Any],
    vector: Callable[[dict[str, Any]], list[float]] = grid_pair_vector,
) -> dict[str, Any]:
    folds = _prepare_crossfit(rows, shadow, vector)
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


def build_v6_development(
    runs: list[dict[str, Any]], shadow: dict[str, Any],
) -> dict[str, Any]:
    support = deduplicate_rows(_all_rows(runs))
    rows = support.pop("rows")
    selection = select_policy(rows, shadow)
    selected = selection["selected_result"]
    wins, losses = int(selected["wins"]), int(selected["losses"])
    win_fraction = wins / (wins + losses) if wins + losses else 0.0
    development = {
        "schema_version": 1,
        "evaluation_kind": "group_complement_crossfit_unique_signatures",
        "representation": (
            f"stamped_height_grid_{GRID_SIZE}_delta_plus_action_delta"
        ),
        "training_run_ids": [run["run_id"] for run in runs],
        "support": support,
        "selected_result": selected,
        "development_win_fraction": win_fraction,
        "claim": (
            "Development evidence only; freezing requires clear cross-fit "
            "superiority and a powered new-stream confirmation."
        ),
    }
    if win_fraction > 0.5:
        development["minimum_discordant_pairs_if_frozen"] = (
            minimum_powered_discordant(win_fraction)
        )
    return development


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--training-dir", action="append", type=pathlib.Path,
                        required=True)
    parser.add_argument("--shadow-model", type=pathlib.Path, required=True)
    parser.add_argument("--development-output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    shadow = json.loads(args.shadow_model.read_text(encoding="utf-8"))
    runs = [load_run(path, label_family=LABEL_FAMILY) for path in args.training_dir]
    development = build_v6_development(runs, shadow)
    args.development_output.parent.mkdir(parents=True, exist_ok=True)
    args.development_output.write_text(
        json.dumps(development, indent=2) + "\n", encoding="utf-8"
    )
    print(args.development_output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
