"""Test source-state representations inside discovery roots only.

Rows from one physical graph never cross a fold boundary.  The late-root file
is neither accepted as an argument nor read.  A deterministic state
permutation is reported beside the real candidate-local representation as a
negative control.
"""

from __future__ import annotations

import argparse
import json
import math
import pathlib
import statistics
from typing import Any, Callable

import numpy as np

try:
    from scripts.evaluate_counterfactual_teacher_baseline import (
        DIRECTIONAL,
        _action_pair,
        _read_jsonl,
        _set_summary,
        _standardize,
    )
except ModuleNotFoundError:  # direct `python scripts/...py` execution
    from evaluate_counterfactual_teacher_baseline import (
        DIRECTIONAL,
        _action_pair,
        _read_jsonl,
        _set_summary,
        _standardize,
    )


def _named(tensor: dict[str, Any], names_key: str, values: list[Any]) -> dict[str, float]:
    return {
        name: float(value)
        for name, value in zip(tensor[names_key], values)
    }


def _candidate_local_features(
    action: dict[str, Any], state: dict[str, Any],
) -> list[float]:
    command = _named(action, "feature_names", action["values"])
    container_index = int(command["container_index"])
    container_rows = state["container_values"]
    container = _named(
        state, "container_features",
        container_rows[container_index] if container_index < len(container_rows) else [],
    )
    x, y, z = (command[name] for name in ("command_x", "command_y", "command_z"))
    length, width, height = (
        command.get(name, 0.0) for name in ("length", "width", "height")
    )
    packed = [
        _named(state, "packed_item_features", values)
        for values in state["packed_item_values"]
    ]
    same = [
        item for item in packed
        if int(item["container_index"]) == container_index
    ]
    distances: list[float] = []
    horizontal_clearances: list[float] = []
    vertical_support_gaps: list[float] = []
    neighbour_soft = 0.0
    neighbour_priority = 0.0
    relative_counts = [0.0] * 6
    for item in same:
        dx = item["local_x"] - x
        dy = item["local_y"] - y
        dz = item["local_z"] - z
        distance = math.sqrt(dx * dx + dy * dy + dz * dz)
        distances.append(distance)
        gap_x = abs(dx) - (length + item["length"]) / 2.0
        gap_y = abs(dy) - (width + item["width"]) / 2.0
        horizontal_clearances.append(max(gap_x, gap_y))
        if gap_x <= 0.0 and gap_y <= 0.0:
            candidate_bottom = z - height / 2.0
            item_top = item["local_z"] + item["height"] / 2.0
            vertical_support_gaps.append(abs(candidate_bottom - item_top))
        if distance <= max(length, width, height, 0.25):
            neighbour_soft += item.get("is_soft", 0.0)
            neighbour_priority += item.get("is_prioritized", 0.0)
        relative_counts[0 if dx < 0 else 1] += 1.0
        relative_counts[2 if dy < 0 else 3] += 1.0
        relative_counts[4 if dz < 0 else 5] += 1.0

    scale = math.sqrt(
        container.get("length", 0.0) ** 2
        + container.get("width", 0.0) ** 2
        + container.get("height", 0.0) ** 2
    ) or 1.0
    nearest = sorted(distances)[:3]
    nearest.extend([scale] * (3 - len(nearest)))
    overlap_count = sum(value <= 0.0 for value in horizontal_clearances)
    pool = state["visible_item_values"]
    pool_maps = [
        _named(state, "visible_item_features", values) for values in pool
    ]
    denominator = float(len(same) or 1)
    return [
        float(len(same)),
        float(len(pool)),
        x / (container.get("length", 0.0) or 1.0),
        y / (container.get("width", 0.0) or 1.0),
        z / (container.get("height", 0.0) or 1.0),
        container.get("length", 0.0) / 2.0 - abs(x) - length / 2.0,
        container.get("width", 0.0) / 2.0 - abs(y) - width / 2.0,
        z - height / 2.0,
        container.get("height", 0.0) - z - height / 2.0,
        *nearest,
        min(horizontal_clearances, default=scale),
        float(overlap_count),
        min(vertical_support_gaps, default=scale),
        float(sum(gap <= 0.02 for gap in vertical_support_gaps)),
        neighbour_soft,
        neighbour_priority,
        *(count / denominator for count in relative_counts),
        statistics.fmean(item.get("mass", 0.0) for item in pool_maps)
        if pool_maps else 0.0,
        statistics.fmean(item.get("length", 0.0) for item in pool_maps)
        if pool_maps else 0.0,
        statistics.fmean(item.get("width", 0.0) for item in pool_maps)
        if pool_maps else 0.0,
        statistics.fmean(item.get("height", 0.0) for item in pool_maps)
        if pool_maps else 0.0,
        statistics.fmean(item.get("is_soft", 0.0) for item in pool_maps)
        if pool_maps else 0.0,
        statistics.fmean(item.get("is_prioritized", 0.0) for item in pool_maps)
        if pool_maps else 0.0,
        container.get("has_shelf", 0.0),
        container.get("is_priority_dedicated", 0.0),
    ]


def local_pair_vector(
    row: dict[str, Any], state: dict[str, Any] | None = None,
) -> list[float]:
    state = state or row["source_state_tensor"]
    lower = _candidate_local_features(row["lower_action_tensor"], state)
    higher = _candidate_local_features(row["higher_action_tensor"], state)
    return _action_pair(row) + lower + higher + [
        right - left for left, right in zip(lower, higher)
    ]


def _predict_fold(
    train: list[dict[str, Any]], test: list[dict[str, Any]], metric: str,
    features: Callable[[dict[str, Any]], list[float]],
    test_features: Callable[[dict[str, Any]], list[float]] | None = None,
) -> dict[str, str]:
    eligible = [
        row for row in train
        if row["labels"][metric]["relation"] in DIRECTIONAL
    ]
    if not eligible:
        return {}
    train_values = [features(row) for row in eligible]
    test_features = test_features or features
    test_values = [test_features(row) for row in test]
    train_values, test_values = _standardize(train_values, test_values)
    result = {}
    for row, vector in zip(test, test_values):
        distances = [
            math.fsum((left - right) ** 2 for left, right in zip(candidate, vector))
            for candidate in train_values
        ]
        nearest = min(
            range(len(eligible)),
            key=lambda index: (distances[index], eligible[index]["teacher_id"]),
        )
        result[row["teacher_id"]] = eligible[nearest]["labels"][metric]["relation"]
    return result


def _predict_ridge_fold(
    train: list[dict[str, Any]], test: list[dict[str, Any]], metric: str,
    features: Callable[[dict[str, Any]], list[float]],
    test_features: Callable[[dict[str, Any]], list[float]] | None = None,
) -> dict[str, str]:
    """Fixed-L2 least-squares classifier; no holdout-driven tuning."""
    eligible = [
        row for row in train
        if row["labels"][metric]["relation"] in DIRECTIONAL
    ]
    if not eligible:
        return {}
    test_features = test_features or features
    train_values, test_values = _standardize(
        [features(row) for row in eligible],
        [test_features(row) for row in test],
    )
    design = np.asarray(
        [[1.0, *values] for values in train_values], dtype=float
    )
    target = np.asarray([
        1.0
        if row["labels"][metric]["relation"]
        == "higher_immediate_score_better"
        else -1.0
        for row in eligible
    ])
    penalty = np.eye(design.shape[1], dtype=float)
    penalty[0, 0] = 0.0
    weights = np.linalg.solve(
        design.T @ design + penalty,
        design.T @ target,
    )
    result = {}
    for row, values in zip(test, test_values):
        prediction = float(np.dot(np.asarray([1.0, *values]), weights))
        result[row["teacher_id"]] = (
            "higher_immediate_score_better"
            if prediction >= 0.0
            else "lower_immediate_score_better"
        )
    return result


def _permuted_states(
    rows: list[dict[str, Any]], shift: int = 1,
) -> dict[str, dict[str, Any]]:
    ordered = sorted(rows, key=lambda row: row["teacher_id"])
    states = [row["source_state_tensor"] for row in ordered]
    return {
        row["teacher_id"]: states[(index + shift) % len(states)]
        for index, row in enumerate(ordered)
    }


def evaluate_discovery(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        raise ValueError("discovery corpus is empty")
    groups = sorted({row["graph_id"] for row in rows})
    if len(groups) < 2:
        raise ValueError("root-grouped evaluation requires at least two graphs")
    feature_sets: dict[str, Callable[[dict[str, Any]], list[float]]] = {
        "action_only_1nn": _action_pair,
        "global_state_1nn": lambda row: _set_summary(row["source_state_tensor"])
        + _action_pair(row),
        "candidate_local_state_1nn": local_pair_vector,
    }
    ridge_feature_sets: dict[str, Callable[[dict[str, Any]], list[float]]] = {
        "action_only_ridge": feature_sets["action_only_1nn"],
        "candidate_local_state_ridge": feature_sets[
            "candidate_local_state_1nn"
        ],
    }
    permutation_names = [
        f"permuted_local_state_ridge_shift_{shift}"
        for shift in range(1, 8)
    ]
    axes = {}
    for metric in sorted(rows[0]["labels"]):
        directional = [
            row for row in rows
            if row["labels"][metric]["relation"] in DIRECTIONAL
        ]
        predictions = {name: {} for name in feature_sets}
        predictions.update({name: {} for name in ridge_feature_sets})
        predictions["permuted_local_state_1nn"] = {}
        predictions.update({name: {} for name in permutation_names})
        majority_predictions = {}
        for group in groups:
            train = [row for row in rows if row["graph_id"] != group]
            test = [row for row in directional if row["graph_id"] == group]
            if not test:
                continue
            labels = [
                row["labels"][metric]["relation"] for row in train
                if row["labels"][metric]["relation"] in DIRECTIONAL
            ]
            if labels:
                counts = {label: labels.count(label) for label in DIRECTIONAL}
                majority = max(
                    DIRECTIONAL,
                    key=lambda label: (counts[label], label.startswith("higher")),
                )
                majority_predictions.update({row["teacher_id"]: majority for row in test})
            for name, features in feature_sets.items():
                predictions[name].update(_predict_fold(train, test, metric, features))
            for name, features in ridge_feature_sets.items():
                predictions[name].update(
                    _predict_ridge_fold(train, test, metric, features)
                )
            for shift, name in enumerate(permutation_names, start=1):
                state_map = _permuted_states(train, shift)
                permuted_features = (
                    lambda row, state_map=state_map: local_pair_vector(
                        row, state_map[row["teacher_id"]]
                    )
                )
                if shift == 1:
                    predictions["permuted_local_state_1nn"].update(
                        _predict_fold(
                            train, test, metric, permuted_features,
                            test_features=local_pair_vector,
                        )
                    )
                predictions[name].update(
                    _predict_ridge_fold(
                        train, test, metric, permuted_features,
                        test_features=local_pair_vector,
                    )
                )
        models = {
            "immediate_score": {row["teacher_id"]: "higher_immediate_score_better" for row in directional},
            "root_grouped_majority": majority_predictions,
            **predictions,
        }
        model_results = {
            name: {
                "correct": sum(
                    values.get(row["teacher_id"])
                    == row["labels"][metric]["relation"]
                    for row in directional
                ),
                "total": len(directional),
            }
            for name, values in models.items()
        }
        permutation_correct = [
            model_results[f"permuted_local_state_ridge_shift_{shift}"][
                "correct"
            ]
            for shift in range(1, 8)
        ]
        comparisons = {}
        for baseline in (
            "immediate_score", "action_only_ridge",
            "permuted_local_state_ridge_shift_1",
        ):
            wins = ties = losses = 0
            for group in groups:
                group_rows = [
                    row for row in directional if row["graph_id"] == group
                ]
                if not group_rows:
                    continue
                local_correct = sum(
                    models["candidate_local_state_ridge"].get(row["teacher_id"])
                    == row["labels"][metric]["relation"]
                    for row in group_rows
                )
                baseline_correct = sum(
                    models[baseline].get(row["teacher_id"])
                    == row["labels"][metric]["relation"]
                    for row in group_rows
                )
                if local_correct > baseline_correct:
                    wins += 1
                elif local_correct < baseline_correct:
                    losses += 1
                else:
                    ties += 1
            comparisons[baseline] = {
                "local_wins": wins, "ties": ties, "local_losses": losses,
            }
        axes[metric] = {
            "directional_rows": len(directional),
            "models": model_results,
            "permuted_local_ridge_correct": {
                "values": permutation_correct,
                "minimum": min(permutation_correct, default=0),
                "median": statistics.median(permutation_correct)
                if permutation_correct else 0,
                "maximum": max(permutation_correct, default=0),
            },
            "candidate_local_ridge_graph_comparisons": comparisons,
        }
    return {
        "schema_version": 1,
        "protocol": "leave_one_physical_graph_out_on_discovery_only",
        "late_holdout_accessed": False,
        "discovery_rows": len(rows),
        "graph_groups": len(groups),
        "negative_control": (
            "source states rotated only inside each training fold at shifts "
            "1 through 7; held-out graph states never enter training"
        ),
        "axes": axes,
    }


def render_markdown(report: dict[str, Any]) -> str:
    names = (
        "immediate_score", "action_only_1nn", "global_state_1nn",
        "candidate_local_state_1nn", "permuted_local_state_1nn",
        "action_only_ridge", "candidate_local_state_ridge",
    )
    lines = [
        "# Discovery-only counterfactual state representation audit",
        "",
        f"Rows / physical-graph folds: **{report['discovery_rows']} / {report['graph_groups']}**",
        "",
        "The late-root file was not read. Every fold holds out one complete physical graph.",
        "",
        "| Axis | Rows | Immediate | Action 1-NN | Global 1-NN | Local 1-NN | Permuted 1-NN | Action ridge | Local ridge | Permuted ridge min/median/max |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for metric, axis in report["axes"].items():
        cells = [
            f"{axis['models'][name]['correct']}/{axis['models'][name]['total']}"
            for name in names
        ]
        control = axis["permuted_local_ridge_correct"]
        cells.append(
            f"{control['minimum']}/{control['median']}/{control['maximum']}"
            f" of {axis['directional_rows']}"
        )
        lines.append(f"| {metric} | {axis['directional_rows']} | " + " | ".join(cells) + " |")
    lines.append("")
    return "\n".join(lines)


def frozen_axis_policy(report: dict[str, Any]) -> dict[str, Any]:
    """Freeze the representation choice before any new late-root run."""
    return {
        "schema_version": 1,
        "selection_source": "discovery_only_leave_one_physical_graph_out",
        "late_holdout_accessed_for_selection": False,
        "axes": {
            "fill_score_proxy": "action_only_ridge",
            "com_z": "candidate_local_state_ridge",
            "surface_total_variation": "candidate_local_state_ridge",
            "placed_count": "abstain_no_directional_discovery_rows",
            "priority_misrouted": "abstain_no_directional_discovery_rows",
            "soft_covered_by_other": "abstain_insufficient_directional_discovery_rows",
        },
        "discovery_evidence": {
            metric: {
                "directional_rows": report["axes"][metric]["directional_rows"],
                "action_only_ridge": report["axes"][metric]["models"][
                    "action_only_ridge"
                ],
                "candidate_local_state_ridge": report["axes"][metric]["models"][
                    "candidate_local_state_ridge"
                ],
                "permuted_local_ridge_correct": report["axes"][metric][
                    "permuted_local_ridge_correct"
                ],
            }
            for metric in (
                "fill_score_proxy", "com_z", "surface_total_variation"
            )
            if metric in report["axes"]
        },
        "acceptance_gate_for_one_new_late_run": (
            "Report exact per-axis counts once. Do not retune. Candidate-local "
            "must beat action-only on at least one of com_z/surface and be no "
            "worse in their pooled correct count to justify a larger model."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--discovery", type=pathlib.Path, required=True)
    parser.add_argument("--json-output", type=pathlib.Path, required=True)
    parser.add_argument("--markdown-output", type=pathlib.Path, required=True)
    parser.add_argument("--policy-output", type=pathlib.Path)
    args = parser.parse_args()
    report = evaluate_discovery(_read_jsonl(args.discovery))
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    args.markdown_output.write_text(render_markdown(report), encoding="utf-8")
    if args.policy_output is not None:
        args.policy_output.parent.mkdir(parents=True, exist_ok=True)
        args.policy_output.write_text(
            json.dumps(frozen_axis_policy(report), indent=2) + "\n",
            encoding="utf-8",
        )
    print(args.markdown_output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
