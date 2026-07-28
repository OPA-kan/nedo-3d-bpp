from __future__ import annotations

import math
from typing import Any

import numpy as np


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


def calculate_settled_metrics(
    containers: list[dict[str, Any]],
    grid_size: float = 0.02,
) -> dict[str, float | int]:
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
    }
