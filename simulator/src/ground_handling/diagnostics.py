from __future__ import annotations

import math
from typing import Any

import numpy as np


def settle_motion_metrics(
    target_position,
    target_quaternion,
    final_position,
    final_quaternion,
    final_aabb=None,
) -> dict[str, float | list[float] | None]:
    target_position_array = np.asarray(target_position, dtype=np.float64)
    final_position_array = np.asarray(final_position, dtype=np.float64)
    displacement = final_position_array - target_position_array

    target_quaternion_array = np.asarray(
        target_quaternion,
        dtype=np.float64,
    )
    final_quaternion_array = np.asarray(
        final_quaternion,
        dtype=np.float64,
    )
    target_norm = float(np.linalg.norm(target_quaternion_array))
    final_norm = float(np.linalg.norm(final_quaternion_array))
    angle_degrees = 0.0
    if target_norm > 0.0 and final_norm > 0.0:
        dot_product = abs(
            float(
                np.dot(
                    target_quaternion_array / target_norm,
                    final_quaternion_array / final_norm,
                )
            )
        )
        dot_product = min(1.0, max(0.0, dot_product))
        angle_degrees = math.degrees(2.0 * math.acos(dot_product))

    aabb_dimensions = None
    if final_aabb is not None:
        minimum, maximum = final_aabb
        aabb_dimensions = [
            float(value)
            for value in (
                np.asarray(maximum, dtype=np.float64)
                - np.asarray(minimum, dtype=np.float64)
            )
        ]

    return {
        "settle_displacement_xyz": [
            float(value) for value in displacement.tolist()
        ],
        "settle_displacement_norm": float(np.linalg.norm(displacement)),
        "settle_angle_deg": float(angle_degrees),
        "settle_final_position": [
            float(value) for value in final_position_array.tolist()
        ],
        "settle_final_quaternion": [
            float(value) for value in final_quaternion_array.tolist()
        ],
        "settle_aabb_dimensions": aabb_dimensions,
    }


def _surface_grid(container: dict[str, Any], grid_size: float) -> np.ndarray:
    length = float(container["length"])
    width = float(container["width"])
    thickness = float(container["thickness"])
    nx = max(1, int(math.ceil((length - 2.0 * thickness) / grid_size)))
    ny = max(1, int(math.ceil((width - 2.0 * thickness) / grid_size)))
    heights = np.full((nx, ny), thickness, dtype=np.float64)

    x_min = -length / 2.0 + thickness
    y_min = -width / 2.0 + thickness
    shelf_top = (
        float(container["height"]) / 2.0
        + thickness
        + float(container.get("buffer", 0.0))
    )

    cut_x = float(container.get("cut_x", 0.0))
    small_shelf_x_max = -length / 2.0 + thickness + cut_x
    small_end = min(nx, max(0, int(math.ceil(
        (small_shelf_x_max - x_min) / grid_size
    ))))
    if small_end > 0:
        heights[:small_end, :] = np.maximum(
            heights[:small_end, :],
            shelf_top,
        )

    if bool(container.get("require_shelf", container.get("shelf", False))):
        shelf_y_min = thickness
        shelf_start = min(ny, max(0, int(math.floor(
            (shelf_y_min - y_min) / grid_size
        ))))
        heights[:, shelf_start:] = np.maximum(
            heights[:, shelf_start:],
            shelf_top,
        )

    offset_x = float(container.get("offset_x", container.get("center_x", 0.0)))
    for item in container.get("packed_items", []):
        aabb_min = item.get("aabb_min")
        aabb_max = item.get("aabb_max")
        if aabb_min is None or aabb_max is None:
            continue
        item_x_min = float(aabb_min[0]) - offset_x
        item_x_max = float(aabb_max[0]) - offset_x
        item_y_min = float(aabb_min[1])
        item_y_max = float(aabb_max[1])
        ix0 = min(nx, max(0, int(math.floor(
            (item_x_min - x_min) / grid_size
        ))))
        ix1 = min(nx, max(0, int(math.ceil(
            (item_x_max - x_min) / grid_size
        ))))
        iy0 = min(ny, max(0, int(math.floor(
            (item_y_min - y_min) / grid_size
        ))))
        iy1 = min(ny, max(0, int(math.ceil(
            (item_y_max - y_min) / grid_size
        ))))
        if ix0 < ix1 and iy0 < iy1:
            heights[ix0:ix1, iy0:iy1] = np.maximum(
                heights[ix0:ix1, iy0:iy1],
                float(aabb_max[2]),
            )
    return heights


def _surface_metrics(
    containers: list[dict[str, Any]],
    grid_size: float,
) -> dict[str, float]:
    values: list[np.ndarray] = []
    edge_differences: list[np.ndarray] = []
    flat_edges = 0
    total_edges = 0
    for container in containers:
        grid = _surface_grid(container, grid_size)
        values.append(grid.ravel())
        for differences in (
            np.abs(np.diff(grid, axis=0)).ravel(),
            np.abs(np.diff(grid, axis=1)).ravel(),
        ):
            if differences.size == 0:
                continue
            edge_differences.append(differences)
            flat_edges += int(np.count_nonzero(differences <= 0.01))
            total_edges += int(differences.size)

    all_values = np.concatenate(values) if values else np.asarray([0.0])
    all_edges = (
        np.concatenate(edge_differences)
        if edge_differences
        else np.asarray([0.0])
    )
    return {
        "surface_height_std": float(np.std(all_values)),
        "surface_total_variation": float(np.mean(all_edges)),
        "flat_support_edge_ratio": (
            float(flat_edges / total_edges) if total_edges else 1.0
        ),
    }


def _depth_metrics(
    containers: list[dict[str, Any]],
    depth_bins: int,
) -> dict[str, float | list[float]]:
    depth_bins = max(2, int(depth_bins))
    occupied = np.zeros(depth_bins, dtype=np.float64)
    capacity = np.zeros(depth_bins, dtype=np.float64)
    weighted_depth = 0.0
    weighted_volume = 0.0

    for container in containers:
        length = float(container["length"])
        width = float(container["width"])
        height = float(container["height"])
        thickness = float(container["thickness"])
        y_min = -width / 2.0 + thickness
        y_max = width / 2.0 - thickness
        usable_depth = max(0.0, y_max - y_min)
        usable_x = max(0.0, length - 2.0 * thickness)
        usable_z = max(0.0, height - 2.0 * thickness)
        offset_x = float(
            container.get("offset_x", container.get("center_x", 0.0))
        )
        if usable_depth <= 0.0:
            continue
        bin_width = usable_depth / depth_bins
        capacity += usable_x * usable_z * bin_width

        for item in container.get("packed_items", []):
            aabb_min = item.get("aabb_min")
            aabb_max = item.get("aabb_max")
            if aabb_min is None or aabb_max is None:
                continue
            item_x_min = float(aabb_min[0]) - offset_x
            item_x_max = float(aabb_max[0]) - offset_x
            x_span = max(
                0.0,
                min(length / 2.0 - thickness, item_x_max)
                - max(-length / 2.0 + thickness, item_x_min),
            )
            z_span = max(
                0.0,
                min(height - thickness, float(aabb_max[2]))
                - max(thickness, float(aabb_min[2])),
            )
            for index in range(depth_bins):
                bin_min = y_min + index * bin_width
                bin_max = bin_min + bin_width
                y_span = max(
                    0.0,
                    min(bin_max, float(aabb_max[1]))
                    - max(bin_min, float(aabb_min[1])),
                )
                occupied[index] += x_span * y_span * z_span

            item_volume = float(item.get("volume", 0.0))
            half_usable_depth = usable_depth / 2.0
            normalized_y = (
                float(item.get("pos", [0.0, 0.0, 0.0])[1])
                / half_usable_depth
                if half_usable_depth > 0.0
                else 0.0
            )
            weighted_depth += item_volume * max(
                -1.0,
                min(1.0, normalized_y),
            )
            weighted_volume += item_volume

    profile = np.divide(
        occupied,
        capacity,
        out=np.zeros_like(occupied),
        where=capacity > 0.0,
    )
    profile = np.clip(profile, 0.0, 1.0)
    midpoint = depth_bins // 2
    return {
        "depth_occupancy_profile": [
            float(value) for value in profile.tolist()
        ],
        "front_depth_occupancy_mean": float(np.mean(profile[:midpoint])),
        "back_depth_occupancy_mean": float(np.mean(profile[midpoint:])),
        "occupied_depth_center_normalized": (
            weighted_depth / weighted_volume
            if weighted_volume > 0.0
            else 0.0
        ),
    }


def calculate_settled_metrics(
    containers: list[dict[str, Any]],
    grid_size: float = 0.02,
    depth_bins: int = 16,
) -> dict[str, float | int | list[float]]:
    items = [
        item
        for container in containers
        for item in container.get("packed_items", [])
    ]
    total_container_volume = sum(
        float(container.get("volume", 0.0)) for container in containers
    )
    placed_volume = sum(float(item.get("volume", 0.0)) for item in items)
    total_mass = sum(float(item.get("mass", 0.0)) for item in items)
    weighted_z = sum(
        float(item.get("mass", 0.0)) * float(item.get("pos", [0, 0, 0])[2])
        for item in items
    )
    remaining_volume = max(0.0, total_container_volume - placed_volume)
    surface = _surface_metrics(containers, grid_size)
    depth = _depth_metrics(containers, depth_bins)
    return {
        "placed_count": len(items),
        "placed_volume": placed_volume,
        "fill_percent_proxy": (
            100.0 * placed_volume / total_container_volume
            if total_container_volume > 0.0
            else 0.0
        ),
        "center_of_mass_z": weighted_z / total_mass if total_mass else 0.0,
        "remaining_volume": remaining_volume,
        "remaining_volume_ratio": (
            remaining_volume / total_container_volume
            if total_container_volume > 0.0
            else 0.0
        ),
        **surface,
        **depth,
    }


# --- Attribute placement: the two official components we can compute ---
#
# The official score has six components. This bundled evaluator computes two
# of them (fill_score, num_placed_items). cog, stability, placement and
# soft_item exist only on the evaluation platform, so until now the only way
# to learn anything about them was to submit and read the feedback -- which
# is how we found out that placement_score was 4.45 and soft_item_score 7.65,
# the two worst components, on submission22.
#
# Two of those four have fully published rules that need no physics.
# simulator/README.md:379, transcribed:
#
#   * a priority item loses points when an item of a DIFFERENT attribute
#     contacts it from above; priority-on-priority is explicitly free;
#   * a soft item loses points the same way; soft-on-soft is free;
#   * a priority item placed in a non-priority container loses points, but
#     only when a priority container was available;
#   * priority and soft are evaluated INDEPENDENTLY, so an item that is both
#     is judged twice, once under each rule.
#
# ## What this returns, and what it does not
#
# Counts of rule violations, plus a clean-ratio per attribute. The mapping
# from violations to the 0-100 official number is NOT published, so this
# CANNOT reproduce the 4.45. It is a monotone proxy: it says which of two
# arms damaged priority or soft placement more, which is all that is needed
# to stop flying blind. Do not present a clean_ratio as a score.
#
# ## The one modelling choice
#
# "Contact from above" is read off settled PyBullet AABBs rather than
# contact points: B covers A when their footprints overlap and B's underside
# sits within CONTACT_TOLERANCE of A's top. Contact points would be more
# faithful but depend on when the simulation was last stepped, and a metric
# that changes with call timing is worse than one that is slightly wrong in
# a fixed direction. This proxy can miss a cover separated by a thin gap and
# can invent one where two items merely touch at a corner, so treat single-
# count differences as noise.
CONTACT_TOLERANCE = 0.02
FOOTPRINT_EPSILON = 1e-6


def _footprint_overlap(lower: dict[str, Any], upper: dict[str, Any]) -> float:
    a_min, a_max = lower["aabb_min"], lower["aabb_max"]
    b_min, b_max = upper["aabb_min"], upper["aabb_max"]
    dx = min(a_max[0], b_max[0]) - max(a_min[0], b_min[0])
    dy = min(a_max[1], b_max[1]) - max(a_min[1], b_min[1])
    return max(0.0, dx) * max(0.0, dy)


def _covers_from_above(lower: dict[str, Any], upper: dict[str, Any]) -> bool:
    if _footprint_overlap(lower, upper) <= FOOTPRINT_EPSILON:
        return False
    gap = float(upper["aabb_min"][2]) - float(lower["aabb_max"][2])
    return -CONTACT_TOLERANCE <= gap <= CONTACT_TOLERANCE


def _attribute_violations(items, attribute: str) -> int:
    """Items with `attribute` that something lacking it rests on."""
    violated = 0
    for lower in items:
        if not lower.get(attribute):
            continue
        for upper in items:
            if upper is lower or upper.get(attribute):
                continue
            if _covers_from_above(lower, upper):
                violated += 1
                break
    return violated


def calculate_attribute_placement(
    containers: list[dict[str, Any]],
) -> dict[str, Any]:
    """Rule violations for placement_score and soft_item_score."""
    items = [
        dict(item, _container_is_prioritized=bool(
            container.get("is_prioritized", False)
        ))
        for container in containers
        for item in container.get("packed_items", [])
    ]
    priority_items = [i for i in items if i.get("is_prioritized")]
    soft_items = [i for i in items if i.get("is_soft")]
    has_priority_container = any(
        container.get("is_prioritized") for container in containers
    )
    # Routing is only a violation when the right container existed.
    misrouted = (
        sum(
            1
            for item in priority_items
            if not item["_container_is_prioritized"]
        )
        if has_priority_container
        else 0
    )
    covered_priority = _attribute_violations(items, "is_prioritized")
    covered_soft = _attribute_violations(items, "is_soft")

    def clean_ratio(total: int, violations: int) -> float | None:
        # None, not 1.0: a stream with no priority items has no opinion, and
        # averaging a fabricated 1.0 into an arm total would hide the arms
        # that do carry them.
        return None if total == 0 else max(0.0, (total - violations) / total)

    return {
        "priority_items": len(priority_items),
        "soft_items": len(soft_items),
        "has_priority_container": has_priority_container,
        "priority_covered_by_other": covered_priority,
        "priority_misrouted": misrouted,
        "soft_covered_by_other": covered_soft,
        "priority_clean_ratio": clean_ratio(
            len(priority_items), min(len(priority_items), covered_priority + misrouted)
        ),
        "soft_clean_ratio": clean_ratio(len(soft_items), covered_soft),
    }
