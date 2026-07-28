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
