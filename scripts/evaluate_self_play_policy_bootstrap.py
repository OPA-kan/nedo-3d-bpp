"""Group-held-out policy-prior audit on leakage-free MCTS visit targets."""

from __future__ import annotations

import argparse
import json
import math
import pathlib
from typing import Any

import numpy as np


def candidate_features(row: dict[str, Any], candidate: dict[str, Any]) -> list[float]:
    state = row["state"]
    action = candidate["command_action"]
    item_index = int(action["item_idx"])
    container_index = int(action["container_idx"])
    visible = {
        int(index): values for index, values in zip(
            state["visible_item_indices"], state["visible_item_values"]
        )
    }
    containers = state["container_values"]
    item = list(visible.get(item_index, [0.0] * len(
        state["visible_item_features"]
    )))
    container = (
        list(containers[container_index])
        if 0 <= container_index < len(containers)
        else [0.0] * len(state["container_features"])
    )
    packed = [
        values for values in state["packed_item_values"]
        if int(values[0]) == container_index
    ]
    packed_array = np.asarray(packed, dtype=float) if packed else None
    local_z = (
        float(packed_array[:, 3].max()) if packed_array is not None else 0.0
    )
    mean_xyz = (
        packed_array[:, 1:4].mean(axis=0).tolist()
        if packed_array is not None else [0.0, 0.0, 0.0]
    )
    orientation = int(action["orientation"])
    position = [float(value) for value in action["place_pos"]]
    length, width, height = (container + [1.0, 1.0, 1.0])[:3]
    normalized_position = [
        position[0] / length if length else 0.0,
        position[1] / width if width else 0.0,
        position[2] / height if height else 0.0,
    ]
    return [
        *position,
        *normalized_position,
        *[1.0 if orientation == index else 0.0 for index in range(6)],
        1.0 if container_index == 0 else 0.0,
        1.0 if container_index == 1 else 0.0,
        *item,
        *container,
        float(len(packed)),
        local_z,
        *mean_xyz,
        float(state["packed_item_count"]),
        float(state["visible_item_count"]),
        1.0 if int(row["game_features"]["player_to_move"]) == 0 else -1.0,
        float(row["game_features"]["block_length"]),
    ]


def _ridge(
    train_x: np.ndarray, train_y: np.ndarray, test_x: np.ndarray,
    *, alpha: float,
) -> np.ndarray:
    mean = train_x.mean(axis=0)
    scale = train_x.std(axis=0)
    scale[scale < 1e-9] = 1.0
    x = (train_x - mean) / scale
    test = (test_x - mean) / scale
    target_mean = float(train_y.mean())
    coefficient = np.linalg.solve(
        x.T @ x + alpha * np.eye(x.shape[1]),
        x.T @ (train_y - target_mean),
    )
    return target_mean + test @ coefficient


def _softmax(values: np.ndarray) -> np.ndarray:
    shifted = values - float(values.max())
    exp = np.exp(np.clip(shifted, -40.0, 40.0))
    return exp / exp.sum()


def _q_discriminating(row: dict[str, Any]) -> bool:
    return len({
        round(float(candidate["search_q"]), 12)
        for candidate in row.get("policy_target", [])
        if candidate.get("search_q") is not None
        and int(candidate.get("visits", 0)) > 0
    }) > 1


def evaluate(
    rows: list[dict[str, Any]], *, alpha: float = 10.0,
    q_discriminating_only: bool = False,
) -> dict[str, Any]:
    rows = [row for row in rows if row.get("policy_target_eligible")]
    if q_discriminating_only:
        rows = [row for row in rows if _q_discriminating(row)]
    groups = sorted({str(row["trajectory_group"]) for row in rows})
    if len(groups) < 2:
        raise ValueError("policy audit needs at least two trajectory groups")
    uniform_ce = learned_ce = target_entropy = 0.0
    uniform_brier = learned_brier = 0.0
    learned_top1 = 0
    decisions = 0
    for holdout in groups:
        train_rows = [
            row for row in rows if str(row["trajectory_group"]) != holdout
        ]
        test_rows = [
            row for row in rows if str(row["trajectory_group"]) == holdout
        ]
        train_x = []
        train_y = []
        for row in train_rows:
            candidates = row["policy_target"]
            count = len(candidates)
            for candidate in candidates:
                train_x.append(candidate_features(row, candidate))
                probability = float(candidate["probability"])
                train_y.append(math.log(max(1e-6, probability)))
        test_x = np.asarray([
            candidate_features(row, candidate)
            for row in test_rows for candidate in row["policy_target"]
        ])
        predicted_logits = _ridge(
            np.asarray(train_x), np.asarray(train_y), test_x, alpha=alpha
        )
        offset = 0
        for row in test_rows:
            candidates = row["policy_target"]
            count = len(candidates)
            target = np.asarray([
                float(candidate["probability"]) for candidate in candidates
            ])
            target = target / target.sum()
            predicted = _softmax(predicted_logits[offset:offset + count])
            uniform = np.full(count, 1.0 / count)
            offset += count
            target_entropy += float(-np.sum(target * np.log(target + 1e-12)))
            uniform_ce += float(-np.sum(target * np.log(uniform)))
            learned_ce += float(-np.sum(target * np.log(predicted + 1e-12)))
            uniform_brier += float(np.mean((uniform - target) ** 2))
            learned_brier += float(np.mean((predicted - target) ** 2))
            learned_top1 += int(int(predicted.argmax()) == int(target.argmax()))
            decisions += 1
    metrics = {
        "uniform": {
            "cross_entropy": uniform_ce / decisions,
            "brier": uniform_brier / decisions,
        },
        "candidate_geometry_ridge": {
            "cross_entropy": learned_ce / decisions,
            "brier": learned_brier / decisions,
            "top1_accuracy": learned_top1 / decisions,
        },
        "target_entropy": target_entropy / decisions,
    }
    ce_gain = metrics["uniform"]["cross_entropy"] - metrics[
        "candidate_geometry_ridge"
    ]["cross_entropy"]
    return {
        "schema_version": 1,
        "protocol": "leave_one_trajectory_group_out_candidate_ridge",
        "ridge_alpha": alpha,
        "q_discriminating_only": q_discriminating_only,
        "decisions": decisions,
        "trajectory_groups": len(groups),
        "metrics": metrics,
        "cross_entropy_gain_over_uniform": ce_gain,
        "policy_signal_observed": ce_gain > 0.0,
        "deployment_ready": False,
        "note": (
            "Diagnostic prior bootstrap only; evaluate any learned prior "
            "noise-free and greedy on fresh groups before deployment."
        ),
    }


def markdown(result: dict[str, Any]) -> str:
    metrics = result["metrics"]
    return "\n".join([
        "# Self-Play policy bootstrap audit", "",
        f"- decisions: {result['decisions']}",
        f"- trajectory groups: {result['trajectory_groups']}",
        f"- Q-discriminating only: {result['q_discriminating_only']}",
        f"- target entropy: {metrics['target_entropy']:.6f}",
        f"- uniform cross-entropy: {metrics['uniform']['cross_entropy']:.6f}",
        (
            "- candidate-geometry cross-entropy: "
            f"{metrics['candidate_geometry_ridge']['cross_entropy']:.6f}"
        ),
        (
            "- candidate-geometry top-1 accuracy: "
            f"{metrics['candidate_geometry_ridge']['top1_accuracy']:.6f}"
        ),
        (
            "- cross-entropy gain over uniform: "
            f"{result['cross_entropy_gain_over_uniform']:+.6f}"
        ),
        f"- policy signal observed: {result['policy_signal_observed']}",
        f"- deployment ready: {result['deployment_ready']}",
        "", result["note"], "",
    ])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=pathlib.Path, required=True)
    parser.add_argument("--json-output", type=pathlib.Path, required=True)
    parser.add_argument("--markdown-output", type=pathlib.Path, required=True)
    parser.add_argument("--ridge-alpha", type=float, default=10.0)
    parser.add_argument("--q-discriminating-only", action="store_true")
    args = parser.parse_args()
    with args.dataset.open("r", encoding="utf-8") as handle:
        rows = [json.loads(line) for line in handle if line.strip()]
    result = evaluate(
        rows, alpha=args.ridge_alpha,
        q_discriminating_only=args.q_discriminating_only,
    )
    args.json_output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    args.markdown_output.write_text(markdown(result), encoding="utf-8")
    print(args.markdown_output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
