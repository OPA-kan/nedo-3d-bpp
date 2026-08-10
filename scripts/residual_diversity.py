"""Residual-afterstate proxy descriptors and deterministic coverage sampling."""
from __future__ import annotations

import collections
import math
from typing import Any

from scripts.measure_anchor_recall import candidate_key


CONTINUOUS_FIELDS = (
    "center_x",
    "center_y",
    "center_z",
    "size_x",
    "size_y",
    "size_z",
    "support_ratio",
    "com_margin",
    "overhang_ratio",
    "drop_normalized",
    "support_imbalance",
    "left_right_imbalance",
    "front_back_imbalance",
    "settle_tilt_deg",
)
CATEGORICAL_FIELDS = (
    "pool_index",
    "container_index",
    "orientation",
    "kind",
)
RISK_FIELDS = CONTINUOUS_FIELDS[6:-1]


def residual_proxy_features(record: dict[str, Any]) -> dict[str, Any]:
    """
    Describe the afterstate change induced by one candidate.

    Records in a sampling group share one parent state. The parent therefore
    cancels when candidates are compared, leaving the commanded occupied
    region and predicted-contact features as a cheap proxy for residual-state
    difference. This descriptor measures coverage, never value.
    """
    center = list(record.get("center") or record.get("action_center") or ())
    size = list(record.get("size") or ())
    risk = record.get("release_risk")
    risk_features = (
        risk.get("features", {}) if isinstance(risk, dict) else {}
    )

    def vector_value(values: list[Any], index: int) -> float | None:
        if index >= len(values):
            return None
        try:
            return float(values[index])
        except (TypeError, ValueError):
            return None

    continuous: dict[str, float | None] = {
        "center_x": vector_value(center, 0),
        "center_y": vector_value(center, 1),
        "center_z": vector_value(center, 2),
        "size_x": vector_value(size, 0),
        "size_y": vector_value(size, 1),
        "size_z": vector_value(size, 2),
    }
    for name in RISK_FIELDS:
        raw = risk_features.get(name)
        try:
            continuous[name] = None if raw is None else float(raw)
        except (TypeError, ValueError):
            continuous[name] = None
    raw_tilt = record.get("settle_tilt_deg")
    try:
        continuous["settle_tilt_deg"] = (
            None if raw_tilt is None else float(raw_tilt)
        )
    except (TypeError, ValueError):
        continuous["settle_tilt_deg"] = None
    return {
        "continuous": continuous,
        "categorical": {
            "pool_index": int(record.get("pool_index", -1)),
            "container_index": int(record.get("container_index", -1)),
            "orientation": int(record.get("orientation", -1)),
            "kind": str(record.get("kind", "candidate")),
        },
    }


def proxy_ranges(records: list[dict[str, Any]]) -> dict[str, float]:
    features = [residual_proxy_features(record) for record in records]
    ranges: dict[str, float] = {}
    for name in CONTINUOUS_FIELDS:
        values = [
            feature["continuous"][name]
            for feature in features
            if feature["continuous"][name] is not None
        ]
        ranges[name] = max(values) - min(values) if values else 0.0
    return ranges


def residual_proxy_distance(
    left: dict[str, Any],
    right: dict[str, Any],
    *,
    ranges: dict[str, float],
) -> float:
    """Gower-style distance over mixed residual-proxy features."""
    a = residual_proxy_features(left)
    b = residual_proxy_features(right)
    terms: list[float] = []
    for name in CONTINUOUS_FIELDS:
        left_value = a["continuous"][name]
        right_value = b["continuous"][name]
        scale = ranges.get(name, 0.0)
        if left_value is None or right_value is None or scale <= 0.0:
            continue
        terms.append(abs(left_value - right_value) / scale)
    for name in CATEGORICAL_FIELDS:
        terms.append(
            0.0 if a["categorical"][name] == b["categorical"][name] else 1.0
        )
    return sum(terms) / len(terms) if terms else 0.0


def residual_proxy_coverage(
    records: list[dict[str, Any]],
    *,
    reference_records: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Compact coverage diagnostics for one sampled candidate portfolio."""
    reference = reference_records or records
    ranges = proxy_ranges(reference)
    nearest: list[float] = []
    for index, record in enumerate(records):
        distances = [
            residual_proxy_distance(record, other, ranges=ranges)
            for other_index, other in enumerate(records)
            if other_index != index
        ]
        if distances:
            nearest.append(min(distances))

    reference_features = [
        residual_proxy_features(record)["continuous"]
        for record in reference
    ]
    minima: dict[str, float] = {}
    for name in ("center_x", "center_y", "center_z"):
        values = [
            feature[name]
            for feature in reference_features
            if feature[name] is not None
        ]
        minima[name] = min(values) if values else 0.0

    spatial_cells: set[tuple[int | None, int | None, int | None]] = set()
    for record in records:
        continuous = residual_proxy_features(record)["continuous"]
        cell: list[int | None] = []
        for name in ("center_x", "center_y", "center_z"):
            value = continuous[name]
            span = ranges.get(name, 0.0)
            if value is None:
                cell.append(None)
            elif span <= 0.0:
                cell.append(0)
            else:
                normalized = max(
                    0.0, min(1.0, (value - minima[name]) / span)
                )
                cell.append(min(3, int(normalized * 4.0)))
        spatial_cells.add(tuple(cell))

    return {
        "sampled": len(records),
        "mean_nearest_neighbor_distance": (
            sum(nearest) / len(nearest) if nearest else None
        ),
        "minimum_nearest_neighbor_distance": (
            min(nearest) if nearest else None
        ),
        "unique_items": len(
            {int(record.get("item_index", -1)) for record in records}
        ),
        "unique_item_orientations": len(
            {
                (
                    int(record.get("item_index", -1)),
                    int(record.get("orientation", -1)),
                )
                for record in records
            }
        ),
        "spatial_cell_count": len(spatial_cells),
    }


def _settled_proxy_record(
    record: dict[str, Any], physical: dict[str, Any] | None
) -> dict[str, Any] | None:
    if not isinstance(physical, dict):
        return None
    x_plus = physical.get("x_plus")
    if not isinstance(x_plus, dict):
        return None
    position = x_plus.get("position")
    dimensions = x_plus.get("aabb_dimensions")
    quaternion = x_plus.get("quaternion")
    if not isinstance(position, list) or len(position) != 3:
        return None
    if not isinstance(dimensions, list) or len(dimensions) != 3:
        return None
    if not isinstance(quaternion, list) or len(quaternion) != 4:
        return None
    qx, qy, qz, qw = (float(value) for value in quaternion)
    norm = math.sqrt(qx * qx + qy * qy + qz * qz + qw * qw)
    if norm <= 1e-12:
        return None
    qx /= norm
    qy /= norm
    vertical_cosine = max(
        -1.0,
        min(1.0, 1.0 - 2.0 * (qx * qx + qy * qy)),
    )
    tilt_deg = math.degrees(math.acos(vertical_cosine))
    return {
        "pool_index": int(record.get("pool_index", -1)),
        "item_index": int(record.get("item_index", -1)),
        "container_index": int(record.get("container_index", -1)),
        "orientation": int(record.get("orientation", -1)),
        "kind": str(record.get("kind", "candidate")),
        "center": [float(value) for value in position],
        "size": [float(value) for value in dimensions],
        "settle_tilt_deg": tilt_deg,
    }


def settled_portfolio_comparison(
    *,
    diversity_sample: list[dict[str, Any]],
    random_sample: list[dict[str, Any]],
    results: dict[tuple[Any, ...], dict[str, Any]],
) -> dict[str, Any]:
    """Compare the two portfolios using observed settle afterstates only."""
    arms = {
        "stratified_random": random_sample,
        "residual_diversity": diversity_sample,
    }
    settled_by_arm: dict[str, list[dict[str, Any]]] = {}
    for name, records in arms.items():
        settled_by_arm[name] = [
            settled
            for record in records
            if (
                settled := _settled_proxy_record(
                    record, results.get(candidate_key(record))
                )
            )
            is not None
        ]
    reference = [
        record
        for records in settled_by_arm.values()
        for record in records
    ]

    report: dict[str, Any] = {
        "contract": "official_replay_observed_x_plus",
    }
    for name, records in arms.items():
        physical_rows = [
            results.get(candidate_key(record)) or {} for record in records
        ]
        coverage = residual_proxy_coverage(
            settled_by_arm[name], reference_records=reference
        )
        coverage.update(
            {
                "replayed": len(records),
                "settled": len(settled_by_arm[name]),
                "valid": sum(
                    bool(physical.get("is_valid"))
                    for physical in physical_rows
                ),
                "placed_safe": sum(
                    bool(physical.get("is_placed_safe"))
                    for physical in physical_rows
                ),
            }
        )
        report[name] = coverage

    def difference(name: str) -> float | int | None:
        left = report["residual_diversity"].get(name)
        right = report["stratified_random"].get(name)
        if left is None or right is None:
            return None
        return left - right

    report["diversity_minus_random"] = {
        name: difference(name)
        for name in (
            "mean_nearest_neighbor_distance",
            "minimum_nearest_neighbor_distance",
            "unique_items",
            "unique_item_orientations",
            "spatial_cell_count",
            "settled",
            "valid",
            "placed_safe",
        )
    }
    return report


def maximin_residual_sample(
    records: list[dict[str, Any]],
    *,
    quota: int,
    forced_keys: set[tuple[Any, ...]] | dict[tuple[Any, ...], str],
) -> list[dict[str, Any]]:
    """Select a deterministic residual-proxy-diverse subset of one group."""
    if not isinstance(forced_keys, dict):
        forced_keys = {key: "selected_action" for key in forced_keys}
    forced = [
        record for record in records if candidate_key(record) in forced_keys
    ]
    selected = list(forced)
    remaining = [
        record
        for record in records
        if candidate_key(record) not in forced_keys
    ]
    target = max(int(quota), len(selected))
    ranges = proxy_ranges(records)

    if not selected and remaining and target > 0:
        seed = min(
            remaining,
            key=lambda record: (
                -float(record.get("score", 0.0)),
                candidate_key(record),
            ),
        )
        selected.append(seed)
        remaining.remove(seed)

    while remaining and len(selected) < target:
        def priority(record: dict[str, Any]) -> tuple[Any, ...]:
            minimum_distance = min(
                residual_proxy_distance(record, chosen, ranges=ranges)
                for chosen in selected
            )
            return (
                -minimum_distance,
                -float(record.get("score", 0.0)),
                candidate_key(record),
            )

        chosen = min(remaining, key=priority)
        selected.append(chosen)
        remaining.remove(chosen)

    for record in selected:
        key = candidate_key(record)
        record["sampling"] = {
            "design": "deterministic_residual_proxy_maximin",
            "stratum_key": record.get("stratum_key"),
            "stratum_size": len(records),
            "stratum_sampled": len(selected),
            "inclusion_probability": None,
            "sampling_weight": None,
            "forced": key in forced_keys,
            "forced_reason": forced_keys.get(key),
        }
        record["residual_proxy"] = residual_proxy_features(record)
    return selected


def residual_diversity_sample(
    records: list[dict[str, Any]],
    *,
    per_stratum: int,
    forced_keys: set[tuple[Any, ...]] | dict[tuple[Any, ...], str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Apply deterministic maximin coverage inside every existing stratum."""
    if not isinstance(forced_keys, dict):
        forced_keys = {key: "selected_action" for key in forced_keys}
    groups: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for record in records:
        groups[record["stratum_key"]].append(record)

    sampled: list[dict[str, Any]] = []
    table: list[dict[str, Any]] = []
    for stratum_key in sorted(groups):
        group = groups[stratum_key]
        selected = maximin_residual_sample(
            group,
            quota=per_stratum,
            forced_keys=forced_keys,
        )
        sampled.extend(selected)
        table.append(
            {
                "stratum_key": stratum_key,
                "stratum": group[0]["stratum"],
                "population": len(group),
                "forced": sum(
                    candidate_key(record) in forced_keys for record in group
                ),
                "sampled": len(selected),
                "inclusion_probability": None,
                "design": "deterministic_residual_proxy_maximin",
            }
        )
    return sampled, table
