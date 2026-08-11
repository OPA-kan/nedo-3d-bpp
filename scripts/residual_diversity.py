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

# Two kinds of "different residual state", kept apart on purpose.
#
# Placing a candidate changes the board in two ways that a single Gower sum
# silently averages together. It occupies a region of a container, and it
# consumes an item, leaving a different pool behind. Two placements can match
# on one and differ on the other, and the sum cannot say which.
#
# The weighting was never chosen either: each categorical field contributes a
# full 1.0 while a normalised position difference contributes a fraction, so
# on the observed records -- where only centre, size and settle tilt survive
# -- four of eleven terms are discrete identity, and they carry most of the
# ordering. Measured on the retained corpus: identity alone reproduces 0.793
# of the full metric's 0.839 rank agreement with itself.
#
# So report the two components, and do not fabricate a total. This is the
# same rule the multi-axis selector already follows.
OCCUPANCY_CONTINUOUS = (
    "center_x",
    "center_y",
    "center_z",
    "size_x",
    "size_y",
    "size_z",
    "settle_tilt_deg",
)
OCCUPANCY_CATEGORICAL = ("container_index",)
CONSUMPTION_CATEGORICAL = ("pool_index", "item_index")


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


ProxyVector = tuple[tuple[float | None, ...], tuple[Any, ...]]


def proxy_feature_vector(record: dict[str, Any]) -> ProxyVector:
    """Flatten one descriptor into field-aligned continuous/categorical tuples.

    The dict form is what the JSONL rows carry; this is the same content in
    the order the distance sums it. Callers that compare one record many
    times build it once instead of rebuilding the dict per comparison.
    """
    features = residual_proxy_features(record)
    return (
        tuple(features["continuous"][name] for name in CONTINUOUS_FIELDS),
        tuple(features["categorical"][name] for name in CATEGORICAL_FIELDS),
    )


def scale_vector(vectors: list[ProxyVector]) -> tuple[float, ...]:
    """Per-field observed range of a reference set, aligned to the fields."""
    scales: list[float] = []
    for index in range(len(CONTINUOUS_FIELDS)):
        values = [
            vector[0][index]
            for vector in vectors
            if vector[0][index] is not None
        ]
        scales.append(max(values) - min(values) if values else 0.0)
    return tuple(scales)


def proxy_ranges(records: list[dict[str, Any]]) -> dict[str, float]:
    scales = scale_vector([proxy_feature_vector(record) for record in records])
    return dict(zip(CONTINUOUS_FIELDS, scales))


def feature_vector_distance(
    left: ProxyVector,
    right: ProxyVector,
    *,
    scales: tuple[float, ...],
) -> float:
    """Gower-style distance over mixed residual-proxy features.

    The arities come from the vectors, not from the module-level field
    tuples: a component vector carries fewer fields than the full
    descriptor, and reading the count from ``CATEGORICAL_FIELDS`` would
    index past its end.
    """
    terms: list[float] = []
    for index, scale in enumerate(scales[: len(left[0])]):
        left_value = left[0][index]
        right_value = right[0][index]
        if left_value is None or right_value is None or scale <= 0.0:
            continue
        terms.append(abs(left_value - right_value) / scale)
    for index in range(min(len(left[1]), len(right[1]))):
        terms.append(0.0 if left[1][index] == right[1][index] else 1.0)
    return sum(terms) / len(terms) if terms else 0.0


def residual_proxy_distance(
    left: dict[str, Any],
    right: dict[str, Any],
    *,
    ranges: dict[str, float],
) -> float:
    """Gower-style distance over mixed residual-proxy features."""
    return feature_vector_distance(
        proxy_feature_vector(left),
        proxy_feature_vector(right),
        scales=tuple(ranges.get(name, 0.0) for name in CONTINUOUS_FIELDS),
    )


def nearest_neighbor_distances(
    vectors: list[ProxyVector], *, scales: tuple[float, ...]
) -> list[float]:
    """In-portfolio nearest-neighbour distance of every member, in order.

    The acceptance guard's ΔNN is a mean over this list, so the reported
    coverage and anything optimizing against it must not have two
    implementations. ``residual_proxy_coverage`` and
    ``paired_mean_nn_objective`` both reduce this one list.
    """
    nearest: list[float] = []
    for index, vector in enumerate(vectors):
        distances = [
            feature_vector_distance(vector, other, scales=scales)
            for other_index, other in enumerate(vectors)
            if other_index != index
        ]
        if distances:
            nearest.append(min(distances))
    return nearest


def residual_proxy_coverage(
    records: list[dict[str, Any]],
    *,
    reference_records: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Compact coverage diagnostics for one sampled candidate portfolio."""
    reference = reference_records or records
    scales = scale_vector(
        [proxy_feature_vector(record) for record in reference]
    )
    ranges = dict(zip(CONTINUOUS_FIELDS, scales))
    nearest = nearest_neighbor_distances(
        [proxy_feature_vector(record) for record in records], scales=scales
    )

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


def settled_proxy_record(
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


def component_vector(
    record: dict[str, Any], names: tuple[str, ...]
) -> tuple[tuple[float | None, ...], tuple[Any, ...]]:
    """A descriptor restricted to one named component."""
    features = residual_proxy_features(record)
    continuous = tuple(
        features["continuous"].get(name)
        for name in names
        if name in CONTINUOUS_FIELDS
    )
    categorical = tuple(
        int(record.get(name, -1))
        for name in names
        if name not in CONTINUOUS_FIELDS
    )
    return continuous, categorical


def occupancy_distance(
    left: dict[str, Any],
    right: dict[str, Any],
    *,
    scales: tuple[float, ...],
) -> float:
    """Do these two placements occupy a different region of a container?

    Geometry plus container membership, and nothing else. Positions must
    already be in a single frame; `settled_proxy_record` emits world
    coordinates while commands are container-local, and on a two-container
    board that difference is the container spacing.
    """
    return feature_vector_distance(
        component_vector(left, OCCUPANCY_CONTINUOUS + OCCUPANCY_CATEGORICAL),
        component_vector(right, OCCUPANCY_CONTINUOUS + OCCUPANCY_CATEGORICAL),
        scales=scales,
    )


def consumption_distance(
    left: dict[str, Any], right: dict[str, Any]
) -> float:
    """Do these two placements consume a different item?

    Not decoration: the residual state includes what is left to pack, so two
    placements with identical occupancy but different items leave different
    futures. It is a separate question from occupancy, which is why it is a
    separate number.
    """
    a = component_vector(left, CONSUMPTION_CATEGORICAL)[1]
    b = component_vector(right, CONSUMPTION_CATEGORICAL)[1]
    return sum(
        0.0 if x == y else 1.0 for x, y in zip(a, b)
    ) / max(1, len(a))


def occupancy_scales(
    records: list[dict[str, Any]],
) -> tuple[float, ...]:
    vectors = [
        component_vector(record, OCCUPANCY_CONTINUOUS) for record in records
    ]
    scales: list[float] = []
    for index in range(len(OCCUPANCY_CONTINUOUS)):
        values = [
            vector[0][index]
            for vector in vectors
            if vector[0][index] is not None
        ]
        scales.append(max(values) - min(values) if values else 0.0)
    return tuple(scales)


def paired_mean_nn_objective(
    positive_vectors: list[ProxyVector],
    control_vectors: list[ProxyVector],
) -> dict[str, float | None]:
    """The exact quantity ``settled_portfolio_comparison`` reports as ΔNN.

    Both arms are rescaled by the range of their union, so moving one row of
    the positive arm also moves the control arm's reported distance. Anything
    optimizing this objective has to re-derive the scales after every move
    rather than treat the control number as a constant.
    """
    scales = scale_vector(list(positive_vectors) + list(control_vectors))
    positive = nearest_neighbor_distances(positive_vectors, scales=scales)
    control = nearest_neighbor_distances(control_vectors, scales=scales)

    def mean(values: list[float]) -> float | None:
        return sum(values) / len(values) if values else None

    def smallest(values: list[float]) -> float | None:
        return min(values) if values else None

    def delta(left: float | None, right: float | None) -> float | None:
        return None if left is None or right is None else left - right

    return {
        "positive_mean_nearest_neighbor_distance": mean(positive),
        "control_mean_nearest_neighbor_distance": mean(control),
        "mean_nearest_neighbor_distance_delta": delta(
            mean(positive), mean(control)
        ),
        # Secondary diagnostic only. The acceptance guard does not read it,
        # and the search does not constrain it, so a mean gain paid for with
        # a minimum-distance loss stays visible instead of being asserted away.
        "positive_minimum_nearest_neighbor_distance": smallest(positive),
        "control_minimum_nearest_neighbor_distance": smallest(control),
        "minimum_nearest_neighbor_distance_delta": delta(
            smallest(positive), smallest(control)
        ),
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
                settled := settled_proxy_record(
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


def constrained_residual_sample(
    records: list[dict[str, Any]],
    *,
    quota: int,
    forced_keys: set[tuple[Any, ...]] | dict[tuple[Any, ...], str],
) -> list[dict[str, Any]]:
    """Cover item semantics before maximizing residual-proxy distance."""
    if not isinstance(forced_keys, dict):
        forced_keys = {key: "selected_action" for key in forced_keys}
    selected = [
        record for record in records if candidate_key(record) in forced_keys
    ]
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
        selected_items = {
            int(record.get("item_index", -1)) for record in selected
        }
        selected_orientations = {
            (
                int(record.get("item_index", -1)),
                int(record.get("orientation", -1)),
            )
            for record in selected
        }

        def priority(record: dict[str, Any]) -> tuple[Any, ...]:
            item = int(record.get("item_index", -1))
            item_orientation = (
                item,
                int(record.get("orientation", -1)),
            )
            minimum_distance = min(
                residual_proxy_distance(record, chosen, ranges=ranges)
                for chosen in selected
            )
            return (
                -(item not in selected_items),
                -(item_orientation not in selected_orientations),
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
            "design": (
                "deterministic_item_coverage_then_residual_maximin"
            ),
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


def constrained_residual_diversity_sample(
    records: list[dict[str, Any]],
    *,
    per_stratum: int,
    forced_keys: set[tuple[Any, ...]] | dict[tuple[Any, ...], str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Apply item-aware residual coverage inside every existing stratum."""
    if not isinstance(forced_keys, dict):
        forced_keys = {key: "selected_action" for key in forced_keys}
    groups: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for record in records:
        groups[record["stratum_key"]].append(record)

    sampled: list[dict[str, Any]] = []
    table: list[dict[str, Any]] = []
    for stratum_key in sorted(groups):
        group = groups[stratum_key]
        selected = constrained_residual_sample(
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
                "design": (
                    "deterministic_item_coverage_then_residual_maximin"
                ),
            }
        )
    return sampled, table


def _maximum_semantic_slot_assignment(
    records_by_stratum: dict[str, list[dict[str, Any]]],
    *,
    capacities: dict[str, int],
    semantic_key,
    excluded_semantics: set[Any],
    selected_keys: set[tuple[Any, ...]],
) -> list[tuple[Any, str]]:
    """Maximum-cardinality semantic-to-stratum-capacity matching."""
    strata_by_semantic: dict[Any, set[str]] = collections.defaultdict(set)
    for stratum_key, records in records_by_stratum.items():
        if capacities.get(stratum_key, 0) <= 0:
            continue
        for record in records:
            if candidate_key(record) in selected_keys:
                continue
            semantic = semantic_key(record)
            if semantic not in excluded_semantics:
                strata_by_semantic[semantic].add(stratum_key)

    slots = [
        (stratum_key, slot_index)
        for stratum_key in sorted(records_by_stratum)
        for slot_index in range(max(0, capacities.get(stratum_key, 0)))
    ]
    slot_owner: dict[tuple[str, int], Any] = {}

    def assign(semantic: Any, visited: set[tuple[str, int]]) -> bool:
        eligible = strata_by_semantic[semantic]
        for slot in slots:
            if slot[0] not in eligible or slot in visited:
                continue
            visited.add(slot)
            owner = slot_owner.get(slot)
            if owner is None or assign(owner, visited):
                slot_owner[slot] = semantic
                return True
        return False

    semantics = sorted(
        strata_by_semantic,
        key=lambda semantic: (
            len(strata_by_semantic[semantic]),
            repr(semantic),
        ),
    )
    for semantic in semantics:
        assign(semantic, set())
    return sorted(
        ((semantic, slot[0]) for slot, semantic in slot_owner.items()),
        key=lambda pair: (pair[1], repr(pair[0])),
    )


def global_constrained_residual_diversity_sample(
    records: list[dict[str, Any]],
    *,
    per_stratum: int,
    forced_keys: set[tuple[Any, ...]] | dict[tuple[Any, ...], str],
    distance_records: dict[tuple[Any, ...], dict[str, Any]] | None = None,
    design: str = (
        "deterministic_global_item_matching_then_residual_maximin"
    ),
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Maximize semantics, then distance, subject to every stratum quota.

    `distance_records` changes only the geometry used by the maximin tie-break.
    Identity, score, item/orientation matching and returned rows still come
    from `records`.  The safe-split dataset uses this seam after replay so its
    final portfolio covers observed settle states rather than command proxies.
    """
    if not isinstance(forced_keys, dict):
        forced_keys = {key: "selected_action" for key in forced_keys}
    groups: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for record in records:
        groups[record["stratum_key"]].append(record)

    selected = [
        record for record in records if candidate_key(record) in forced_keys
    ]
    selected_keys = {candidate_key(record) for record in selected}
    targets: dict[str, int] = {}
    counts: dict[str, int] = collections.Counter(
        str(record["stratum_key"]) for record in selected
    )
    for stratum_key, group in groups.items():
        targets[stratum_key] = min(
            len(group), max(int(per_stratum), counts.get(stratum_key, 0))
        )
    capacities = {
        stratum_key: targets[stratum_key] - counts.get(stratum_key, 0)
        for stratum_key in groups
    }
    def distance_record(record: dict[str, Any]) -> dict[str, Any]:
        if distance_records is None:
            return record
        return distance_records.get(candidate_key(record), record)

    ranges = proxy_ranges([distance_record(record) for record in records])

    def distance(
        left: dict[str, Any], right: dict[str, Any]
    ) -> float:
        return residual_proxy_distance(
            distance_record(left),
            distance_record(right),
            ranges=ranges,
        )

    def choose_record(
        semantic: Any,
        stratum_key: str,
        semantic_key,
    ) -> dict[str, Any]:
        candidates = [
            record
            for record in groups[stratum_key]
            if candidate_key(record) not in selected_keys
            and semantic_key(record) == semantic
        ]

        def priority(record: dict[str, Any]) -> tuple[Any, ...]:
            minimum_distance = (
                min(distance(record, chosen) for chosen in selected)
                if selected
                else 0.0
            )
            return (
                -minimum_distance,
                -float(record.get("score", 0.0)),
                candidate_key(record),
            )

        return min(candidates, key=priority)

    def item_key(record: dict[str, Any]) -> int:
        return int(record.get("item_index", -1))

    def orientation_key(record: dict[str, Any]) -> tuple[int, int]:
        return (
            int(record.get("item_index", -1)),
            int(record.get("orientation", -1)),
        )

    def add_assignments(assignments, semantic_key) -> None:
        for semantic, stratum_key in assignments:
            record = choose_record(semantic, stratum_key, semantic_key)
            selected.append(record)
            selected_keys.add(candidate_key(record))
            counts[stratum_key] = counts.get(stratum_key, 0) + 1
            capacities[stratum_key] -= 1

    covered_items = {item_key(record) for record in selected}
    add_assignments(
        _maximum_semantic_slot_assignment(
            groups,
            capacities=capacities,
            semantic_key=item_key,
            excluded_semantics=covered_items,
            selected_keys=selected_keys,
        ),
        item_key,
    )
    covered_orientations = {orientation_key(record) for record in selected}
    add_assignments(
        _maximum_semantic_slot_assignment(
            groups,
            capacities=capacities,
            semantic_key=orientation_key,
            excluded_semantics=covered_orientations,
            selected_keys=selected_keys,
        ),
        orientation_key,
    )

    while any(capacity > 0 for capacity in capacities.values()):
        eligible = [
            record
            for stratum_key, group in groups.items()
            if capacities[stratum_key] > 0
            for record in group
            if candidate_key(record) not in selected_keys
        ]
        if not eligible:
            break

        def fill_priority(record: dict[str, Any]) -> tuple[Any, ...]:
            minimum_distance = (
                min(distance(record, chosen) for chosen in selected)
                if selected
                else 0.0
            )
            return (
                -minimum_distance,
                -float(record.get("score", 0.0)),
                str(record["stratum_key"]),
                candidate_key(record),
            )

        record = min(eligible, key=fill_priority)
        stratum_key = str(record["stratum_key"])
        selected.append(record)
        selected_keys.add(candidate_key(record))
        counts[stratum_key] = counts.get(stratum_key, 0) + 1
        capacities[stratum_key] -= 1

    for record in selected:
        key = candidate_key(record)
        stratum_key = str(record["stratum_key"])
        record["sampling"] = {
            "design": design,
            "stratum_key": stratum_key,
            "stratum_size": len(groups[stratum_key]),
            "stratum_sampled": counts[stratum_key],
            "inclusion_probability": None,
            "sampling_weight": None,
            "forced": key in forced_keys,
            "forced_reason": forced_keys.get(key),
        }
        record["residual_proxy"] = residual_proxy_features(record)
        record["selection_distance_proxy"] = residual_proxy_features(
            distance_record(record)
        )

    table = [
        {
            "stratum_key": stratum_key,
            "stratum": group[0]["stratum"],
            "population": len(group),
            "forced": sum(
                candidate_key(record) in forced_keys for record in group
            ),
            "sampled": counts.get(stratum_key, 0),
            "inclusion_probability": None,
            "design": design,
        }
        for stratum_key, group in sorted(groups.items())
    ]
    return selected, table
