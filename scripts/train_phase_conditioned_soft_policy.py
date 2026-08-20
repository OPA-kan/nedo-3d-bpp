"""Freeze a phase-conditioned post-shake soft policy for a future H3 run.

This is a prospective artifact builder, not an evaluator.  It may consume all
rows of one development run because the resulting policy is only licensed for
a different physical run with non-overlapping teacher-pair signatures.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import statistics
from typing import Any, Callable

import numpy as np

try:
    from scripts.develop_post_shake_soft_reranker import (
        LABEL_FAMILY,
        METRIC,
        _eligible,
        soft_topology_delta,
    )
    from scripts.evaluate_counterfactual_afterstate_value import (
        _features,
        _read_jsonl,
        _state_delta,
        fit_ridge_model,
    )
except ModuleNotFoundError:
    from develop_post_shake_soft_reranker import (
        LABEL_FAMILY,
        METRIC,
        _eligible,
        soft_topology_delta,
    )
    from evaluate_counterfactual_afterstate_value import (
        _features,
        _read_jsonl,
        _state_delta,
        fit_ridge_model,
    )


MODEL_NAMES = (
    "action_geometry",
    "pooled_afterstate",
    "phase_conditioned_soft_topology",
    "phase_conditioned_pooled_afterstate",
)


def _column(state: dict[str, Any], prefix: str, name: str) -> list[float]:
    names = state[f"{prefix}_features"]
    if name not in names:
        return [0.0] * len(state[f"{prefix}_values"])
    index = names.index(name)
    return [float(row[index]) for row in state[f"{prefix}_values"]]


def phase_observables(state: dict[str, Any]) -> list[float]:
    """Continuous, live-observable progress variables; no root step leakage."""
    packed = state["packed_item_values"]
    visible = state["visible_item_values"]
    packed_count = len(packed)
    visible_count = len(visible)
    total_seen = packed_count + visible_count
    progress = packed_count / total_seen if total_seen else 0.0

    packed_lengths = _column(state, "packed_item", "length")
    packed_widths = _column(state, "packed_item", "width")
    packed_heights = _column(state, "packed_item", "height")
    packed_volume = sum(
        length * width * height
        for length, width, height in zip(
            packed_lengths, packed_widths, packed_heights
        )
    )
    container_volume = sum(
        row[state["container_features"].index("length")]
        * row[state["container_features"].index("width")]
        * row[state["container_features"].index("height")]
        for row in state["container_values"]
    )
    fill = packed_volume / float(container_volume or 1.0)

    local_z = _column(state, "packed_item", "local_z")
    top = [z + height / 2.0 for z, height in zip(local_z, packed_heights)]
    maximum_container_height = max(
        (
            float(row[state["container_features"].index("height")])
            for row in state["container_values"]
        ),
        default=1.0,
    )
    height_fraction = max(top, default=0.0) / (maximum_container_height or 1.0)

    packed_soft = _column(state, "packed_item", "is_soft")
    visible_soft = _column(state, "visible_item", "is_soft")
    packed_priority = _column(state, "packed_item", "is_prioritized")
    visible_priority = _column(state, "visible_item", "is_prioritized")
    return [
        1.0,
        progress,
        progress * progress,
        fill,
        height_fraction,
        sum(packed_soft) / float(packed_count or 1),
        sum(visible_soft) / float(visible_count or 1),
        sum(packed_priority) / float(packed_count or 1),
        sum(visible_priority) / float(visible_count or 1),
    ]


def phase_conditioned_soft_features(row: dict[str, Any]) -> list[float]:
    phase = phase_observables(row["source_state_tensor"])
    delta = soft_topology_delta(row)
    return [scalar * value for scalar in phase for value in delta]


def phase_conditioned_pooled_features(row: dict[str, Any]) -> list[float]:
    phase = phase_observables(row["source_state_tensor"])
    delta = _state_delta(row)
    return [scalar * value for scalar in phase for value in delta]


def feature_sets() -> dict[str, Callable[[dict[str, Any]], list[float]]]:
    return {
        "action_geometry": lambda row: _features(
            row, include_action=True, include_afterstate=False
        ),
        "pooled_afterstate": _state_delta,
        "phase_conditioned_soft_topology": phase_conditioned_soft_features,
        "phase_conditioned_pooled_afterstate": phase_conditioned_pooled_features,
    }


def fit_dual_ridge_model(
    rows: list[dict[str, Any]], features: Callable[[dict[str, Any]], list[float]],
) -> dict[str, Any]:
    """Fit the same fixed-L2 ridge in sample space when features outnumber rows."""
    values = [features(row) for row in rows]
    scales = np.asarray([
        statistics.pstdev(column) or 1.0 for column in zip(*values)
    ])
    design = np.asarray(values, dtype=float) / scales
    target = np.asarray([
        1.0
        if row[LABEL_FAMILY][METRIC]["relation"] == "higher_afterstate_better"
        else -1.0
        for row in rows
    ])
    dual = np.linalg.solve(
        design @ design.T + np.eye(design.shape[0]), target
    )
    weights = design.T @ dual
    return {
        "model": "fixed_l2_no_intercept_ridge_dual_fit",
        "l2": 1.0,
        "metric": METRIC,
        "label_family": LABEL_FAMILY,
        "training_rows": len(rows),
        "feature_count": len(scales),
        "scales": scales.astype(float).tolist(),
        "weights": weights.astype(float).tolist(),
    }


def teacher_signature(row: dict[str, Any]) -> str:
    """Identify a replayed decision without using labels or future outcomes."""
    payload = {
        "case_id": row.get("case_id"),
        "root_step": row.get("root_step"),
        "source_state_tensor": row.get("source_state_tensor"),
        "lower_action_tensor": row.get("lower_action_tensor"),
        "higher_action_tensor": row.get("higher_action_tensor"),
    }
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def train_policy(
    manifest: dict[str, Any], rows: list[dict[str, Any]],
) -> dict[str, Any]:
    eligible = _eligible(rows)
    if len(eligible) < 20:
        raise ValueError("phase policy requires at least 20 directional rows")
    features = feature_sets()
    return {
        "schema_version": 1,
        "status": "prospective_evaluation_only",
        "target": METRIC,
        "label_family": LABEL_FAMILY,
        "source_run_id": str(manifest["source_run_id"]),
        "source_commits": list(manifest.get("source_commits", [])),
        "training_directional_rows": len(eligible),
        "training_root_step_range": [
            min(int(row["root_step"]) for row in eligible),
            max(int(row["root_step"]) for row in eligible),
        ],
        "phase_contract": (
            "continuous source-state progress/fill/height/attribute composition; "
            "root_step is excluded from model features"
        ),
        "feature_contract": (
            "phase_observables_x_physical_afterstate_delta_v1; pooled and "
            "soft-topology variants frozen together"
        ),
        "selected_model": "phase_conditioned_pooled_afterstate",
        "training_teacher_signatures": sorted(
            teacher_signature(row) for row in eligible
        ),
        "models": {
            name: (
                fit_dual_ridge_model(eligible, values)
                if name == "phase_conditioned_pooled_afterstate"
                else fit_ridge_model(
                    eligible, METRIC, values, label_family=LABEL_FAMILY
                )
            )
            for name, values in features.items()
        },
        "promotion_contract": (
            "On one different physical run with zero teacher-signature overlap, "
            "phase-conditioned must strictly beat immediate score, action "
            "geometry, and pooled afterstate over at least 20 directional rows"
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--teacher-dir", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    manifest = json.loads(
        (args.teacher_dir / "manifest.json").read_text(encoding="utf-8")
    )
    rows = (
        _read_jsonl(args.teacher_dir / "distributional_discovery.jsonl")
        + _read_jsonl(args.teacher_dir / "distributional_late_holdout.jsonl")
    )
    policy = train_policy(manifest, rows)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(policy, indent=2) + "\n", encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
