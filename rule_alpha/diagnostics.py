"""Layer 1 board diagnostics: heightmap, plateaus, holes, typed support.

Nothing in this module feeds a competition objective.  It exists so that a
human can look at a Layer 1 board and say what is wrong with it, and so that a
future Layer 2 has a typed surface to plan on.
"""

from __future__ import annotations

import math

import numpy as np

from .geometry import ContainerModel, Rect


# --- typed support codes -----------------------------------------------------
SUPPORT_FREE = 0
SUPPORT_HARD = 1
SUPPORT_SOFT = 2
SUPPORT_PRIORITY = 3
SUPPORT_SOFT_PRIORITY = 4

SUPPORT_NAMES = {
    SUPPORT_FREE: "free-floor",
    SUPPORT_HARD: "hard",
    SUPPORT_SOFT: "soft-only",
    SUPPORT_PRIORITY: "priority-only",
    SUPPORT_SOFT_PRIORITY: "soft+priority-only",
}


def support_code(is_soft: bool, is_prioritized: bool) -> int:
    if is_soft and is_prioritized:
        return SUPPORT_SOFT_PRIORITY
    if is_soft:
        return SUPPORT_SOFT
    if is_prioritized:
        return SUPPORT_PRIORITY
    return SUPPORT_HARD


# ---------------------------------------------------------------------------
# Small grid utilities (kept dependency-free: numpy only)
# ---------------------------------------------------------------------------
def connected_components(mask: np.ndarray) -> tuple[np.ndarray, int]:
    """4-connected labelling of a boolean mask.  Returns (labels, count)."""
    height, width = mask.shape
    labels = np.zeros((height, width), dtype=np.int32)
    current = 0
    # iterative flood fill; grids here are a few thousand cells
    for start_r in range(height):
        for start_c in range(width):
            if not mask[start_r, start_c] or labels[start_r, start_c]:
                continue
            current += 1
            stack = [(start_r, start_c)]
            labels[start_r, start_c] = current
            while stack:
                r, c = stack.pop()
                for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nr, nc = r + dr, c + dc
                    if 0 <= nr < height and 0 <= nc < width:
                        if mask[nr, nc] and not labels[nr, nc]:
                            labels[nr, nc] = current
                            stack.append((nr, nc))
    return labels, current


def largest_rectangle_in_mask(mask: np.ndarray) -> tuple[int, tuple[int, int, int, int]]:
    """Largest axis-aligned all-true rectangle.  Returns (cells, (r0,c0,r1,c1))."""
    if not mask.any():
        return 0, (0, 0, 0, 0)
    height, width = mask.shape
    heights = np.zeros(width, dtype=np.int32)
    best_area = 0
    best_box = (0, 0, 0, 0)
    for r in range(height):
        heights = np.where(mask[r], heights + 1, 0)
        stack: list[tuple[int, int]] = []  # (start_col, height)
        for c in range(width + 1):
            h = int(heights[c]) if c < width else 0
            start = c
            while stack and stack[-1][1] >= h:
                s, sh = stack.pop()
                area = sh * (c - s)
                if area > best_area:
                    best_area = area
                    best_box = (r - sh + 1, s, r, c - 1)
                start = s
            stack.append((start, h))
    return best_area, best_box


# ---------------------------------------------------------------------------
# Occupancy grid
# ---------------------------------------------------------------------------
class FloorGrid:
    """Rasterised view of one container floor.

    The grid spans the full inner cross section (so the slope pocket is
    visible), and carries a ``usable`` mask for the part a floor layer can
    actually reach.
    """

    def __init__(self, model: ContainerModel, cell: float):
        self.model = model
        self.cell = float(cell)
        self.x0 = model.x_wall_min
        self.y0 = model.y_opening
        self.nx = max(1, int(math.ceil((model.x_wall_max - self.x0) / self.cell)))
        self.ny = max(1, int(math.ceil((model.y_back - self.y0) / self.cell)))

        xs = self.x0 + (np.arange(self.nx) + 0.5) * self.cell
        ys = self.y0 + (np.arange(self.ny) + 0.5) * self.cell
        self.xs = xs
        self.ys = ys
        self.xx, self.yy = np.meshgrid(xs, ys, indexing="ij")

        rect = model.floor_rect
        self.usable = (
            (self.xx >= rect.x_min - 1e-9)
            & (self.xx <= rect.x_max + 1e-9)
            & (self.yy >= rect.y_min - 1e-9)
            & (self.yy <= rect.y_max + 1e-9)
        )
        self.cell_area = self.cell * self.cell
        self.usable_area = float(self.usable.sum()) * self.cell_area

        self.height = np.full((self.nx, self.ny), model.z_floor, dtype=np.float64)
        self.support = np.zeros((self.nx, self.ny), dtype=np.int8)
        self.structural = np.zeros((self.nx, self.ny), dtype=bool)
        self.occupied = np.zeros((self.nx, self.ny), dtype=bool)
        self.owner = np.full((self.nx, self.ny), -1, dtype=np.int32)

    # -- construction ----------------------------------------------------
    def rect_mask(self, rect: Rect) -> np.ndarray:
        return (
            (self.xx >= rect.x_min - 1e-9)
            & (self.xx <= rect.x_max + 1e-9)
            & (self.yy >= rect.y_min - 1e-9)
            & (self.yy <= rect.y_max + 1e-9)
        )

    def stamp(self, rect: Rect, top_z: float, code: int, structural: bool,
              owner: int = -1) -> None:
        mask = self.rect_mask(rect)
        if not mask.any():
            return
        higher = mask & (top_z >= self.height - 1e-9)
        self.height[higher] = top_z
        self.support[higher] = code
        self.structural[higher] = structural
        self.owner[higher] = owner
        self.occupied |= mask

    def free_mask(self) -> np.ndarray:
        return self.usable & ~self.occupied

    def coverage(self) -> float:
        if self.usable_area <= 0:
            return 0.0
        return float((self.usable & self.occupied).sum()) * self.cell_area / self.usable_area


def build_floor_grid(model: ContainerModel, placements, cell: float) -> FloorGrid:
    """Rasterise the Layer 1 placements of one container.

    ``placements`` are :class:`~rule_alpha.layer1.Placement` records.  Items
    sitting on a shelf are *not* stamped onto the floor grid: they do not create
    floor support and must not be mistaken for it.
    """
    grid = FloorGrid(model, cell)
    for placement in placements:
        if placement.surface == "shelf":
            continue
        grid.stamp(
            placement.rect,
            placement.top_z,
            support_code(placement.profile.is_soft, placement.profile.is_prioritized),
            placement.is_structural,
            placement.profile.index,
        )
    return grid


# ---------------------------------------------------------------------------
# Plateau extraction
# ---------------------------------------------------------------------------
def plateau_report(grid: FloorGrid, config) -> dict:
    """Plateaus of the *non-structural* surface.

    Wall-front, elongated structural items and slope-specific structure are
    masked out: they are meant to be tall, so counting them as roughness would
    punish the rules that put them there.
    """
    considered = grid.usable & ~grid.structural
    if not considered.any():
        return {
            "largest_plateau_area": 0.0,
            "largest_plateau_ratio": 0.0,
            "largest_built_plateau_area": 0.0,
            "largest_built_plateau_ratio": 0.0,
            "plateau_count": 0,
            "height_spread": 0.0,
            "local_roughness": 0.0,
            "masked_cell_fraction": 1.0,
            "plateaus": [],
            "_labels": np.zeros(grid.height.shape, dtype=np.int32),
        }

    tol = config.plateau_height_tolerance
    quantised = np.round(grid.height / max(tol, 1e-6)).astype(np.int64)
    plateaus = []
    labels = np.zeros(grid.height.shape, dtype=np.int32)
    next_label = 0
    for level in np.unique(quantised[considered]):
        mask = considered & (quantised == level)
        sub_labels, count = connected_components(mask)
        for component in range(1, count + 1):
            cells = sub_labels == component
            area = float(cells.sum()) * grid.cell_area
            next_label += 1
            labels[cells] = next_label
            heights = grid.height[cells]
            plateaus.append(
                {
                    "id": next_label,
                    "area": round(area, 4),
                    "mean_height": round(float(heights.mean()), 4),
                    "cells": int(cells.sum()),
                    "built": bool((cells & grid.occupied).sum() > cells.sum() / 2),
                }
            )
    plateaus.sort(key=lambda p: -p["area"])

    heights = grid.height[considered]
    # local roughness: mean absolute height step between adjacent considered cells
    steps = []
    hx = np.abs(np.diff(grid.height, axis=0))
    mx = considered[:-1, :] & considered[1:, :]
    if mx.any():
        steps.append(hx[mx])
    hy = np.abs(np.diff(grid.height, axis=1))
    my = considered[:, :-1] & considered[:, 1:]
    if my.any():
        steps.append(hy[my])
    roughness = float(np.concatenate(steps).mean()) if steps else 0.0

    largest = plateaus[0]["area"] if plateaus else 0.0
    built = [p for p in plateaus if p["built"]]
    largest_built = built[0]["area"] if built else 0.0
    built_area = float((considered & grid.occupied).sum()) * grid.cell_area
    return {
        # ratios are against the whole usable floor, so "flat" cannot be faked
        # by masking most of the board out
        "largest_plateau_area": round(largest, 4),
        "largest_plateau_ratio": round(largest / max(grid.usable_area, 1e-9), 4),
        "largest_built_plateau_area": round(largest_built, 4),
        "largest_built_plateau_ratio": round(
            largest_built / max(built_area, 1e-9), 4
        ),
        "plateau_count": len(plateaus),
        "height_spread": round(float(heights.max() - heights.min()), 4),
        "local_roughness": round(roughness, 4),
        "masked_cell_fraction": round(
            float((grid.usable & grid.structural).sum()) / max(1, int(grid.usable.sum())), 4
        ),
        "plateaus": plateaus[:12],
        "_labels": labels,
    }


# ---------------------------------------------------------------------------
# Hole extraction
# ---------------------------------------------------------------------------
def _boundary_touching(mask_component: np.ndarray, usable: np.ndarray) -> bool:
    """True when the free component reaches the edge of the usable region."""
    nx, ny = usable.shape
    padded = np.zeros((nx + 2, ny + 2), dtype=bool)
    padded[1:-1, 1:-1] = usable
    comp = np.zeros((nx + 2, ny + 2), dtype=bool)
    comp[1:-1, 1:-1] = mask_component
    outside = ~padded
    # a component touching a non-usable neighbour (or the array border) is open
    neighbours = (
        np.roll(outside, 1, axis=0)
        | np.roll(outside, -1, axis=0)
        | np.roll(outside, 1, axis=1)
        | np.roll(outside, -1, axis=1)
    )
    return bool((comp & neighbours).any())


def hole_report(grid: FloorGrid, config) -> dict:
    """Connected components of free floor, split into interior vs open."""
    model = grid.model
    free = grid.free_mask()
    labels, count = connected_components(free)

    interior, open_regions = [], []
    for component in range(1, count + 1):
        cells = labels == component
        area = float(cells.sum()) * grid.cell_area
        idx_x, idx_y = np.nonzero(cells)
        xs = grid.xs[idx_x]
        ys = grid.ys[idx_y]
        x_min, x_max = float(xs.min()) - grid.cell / 2, float(xs.max()) + grid.cell / 2
        y_min, y_max = float(ys.min()) - grid.cell / 2, float(ys.max()) + grid.cell / 2

        sub = cells[idx_x.min(): idx_x.max() + 1, idx_y.min(): idx_y.max() + 1]
        rect_cells, _ = largest_rectangle_in_mask(sub)

        # surrounding support: cells adjacent to the component that are occupied
        neigh = np.zeros_like(cells)
        neigh[1:, :] |= cells[:-1, :]
        neigh[:-1, :] |= cells[1:, :]
        neigh[:, 1:] |= cells[:, :-1]
        neigh[:, :-1] |= cells[:, 1:]
        ring = neigh & grid.occupied & grid.usable
        if ring.any():
            ring_height = float(grid.height[ring].mean())
            ring_types: dict[str, int] = {}
            for code in np.unique(grid.support[ring]):
                ring_types[SUPPORT_NAMES[int(code)]] = int((grid.support[ring] == code).sum())
        else:
            ring_height = model.z_floor
            ring_types = {}

        is_open = _boundary_touching(cells, grid.usable)
        record = {
            "id": component,
            "area": round(area, 4),
            "centroid": [round(float(xs.mean()), 4), round(float(ys.mean()), 4)],
            "bbox_width_x": round(x_max - x_min, 4),
            "bbox_length_y": round(y_max - y_min, 4),
            "bbox": [round(x_min, 4), round(x_max, 4), round(y_min, 4), round(y_max, 4)],
            "largest_inscribed_rect_area": round(rect_cells * grid.cell_area, 4),
            "distance_to_container_edge": round(
                min(
                    abs(x_min - model.floor_rect.x_min),
                    abs(model.floor_rect.x_max - x_max),
                    abs(model.floor_rect.y_max - y_max),
                    abs(y_min - model.floor_rect.y_min),
                ),
                4,
            ),
            "distance_to_opening": round(abs(y_min - model.y_opening), 4),
            "surrounding_support_height": round(ring_height - model.z_floor, 4),
            "surrounding_support_types": ring_types,
            "interior": not is_open,
        }
        (open_regions if is_open else interior).append(record)

    interior.sort(key=lambda h: -h["area"])
    open_regions.sort(key=lambda h: -h["area"])
    total_free = float(free.sum()) * grid.cell_area
    return {
        "free_area": round(total_free, 4),
        "free_ratio": round(total_free / max(grid.usable_area, 1e-9), 4),
        "interior_hole_count": len(interior),
        "interior_hole_area": round(sum(h["area"] for h in interior), 4),
        "largest_interior_hole": interior[0] if interior else None,
        "interior_holes": interior[:12],
        "open_free_count": len(open_regions),
        "largest_open_free_area": open_regions[0]["area"] if open_regions else 0.0,
        "largest_open_free_rect": (
            open_regions[0]["largest_inscribed_rect_area"] if open_regions else 0.0
        ),
        "open_free_regions": open_regions[:6],
        "_labels": labels,
    }


# ---------------------------------------------------------------------------
# Wall front / corridor
# ---------------------------------------------------------------------------
def wall_front_report(model: ContainerModel, placements, config) -> dict:
    wall_items = [p for p in placements if p.role_is_wall_front]
    wall_height = max((p.top_z for p in wall_items), default=model.z_floor)
    return {
        "wall_front_item_count": len(wall_items),
        "wall_front_top_z": round(wall_height, 4),
        "wall_front_height": round(wall_height - model.z_floor, 4),
        "wall_height_ratio": round(
            (wall_height - model.z_floor) / max(1e-9, model.z_ceiling - model.z_floor), 4
        ),
        "wall_height_target_ratio": config.wall_front_target_ratio,
        "wall_front_coverage_y": round(
            sum(p.rect.y_max - p.rect.y_min for p in wall_items), 4
        ),
        "container_depth": round(model.y_back - model.y_opening, 4),
    }


def zone_report(grid: FloorGrid, model: ContainerModel) -> dict:
    """How much of each reserved zone was actually used, and by what.

    The reserved strips are a hard rule, so a zone that stays empty is a real
    cost of the layout.  Making that cost visible is the point of this block.
    """
    out = {}
    for name in ("wall_front_strip", "soft_zone", "priority_zone", "corridor",
                 "back_band", "centre_band"):
        rect = getattr(model, name)
        mask = grid.rect_mask(rect) & grid.usable
        area = float(mask.sum()) * grid.cell_area
        occupied = mask & grid.occupied
        by_type = {}
        if occupied.any():
            for code in np.unique(grid.support[occupied]):
                by_type[SUPPORT_NAMES[int(code)]] = round(
                    float((grid.support[occupied] == code).sum()) * grid.cell_area, 4
                )
        out[name] = {
            "area": round(area, 4),
            "occupied_area": round(float(occupied.sum()) * grid.cell_area, 4),
            "occupancy": round(
                float(occupied.sum()) / max(1, int(mask.sum())), 4
            ),
            "by_support_type": by_type,
        }
    return out


def corridor_report(grid: FloorGrid, model: ContainerModel) -> dict:
    corridor_mask = grid.rect_mask(model.corridor) & grid.usable
    blocked = corridor_mask & grid.occupied
    corridor_area = float(corridor_mask.sum()) * grid.cell_area
    blocked_area = float(blocked.sum()) * grid.cell_area
    # A usable corridor also needs a clear straight run from the opening to the
    # frontier: check every column of the corridor for an uninterrupted lane.
    lanes = 0
    total_lanes = 0
    for ix in range(grid.nx):
        column = corridor_mask[ix]
        if not column.any():
            continue
        total_lanes += 1
        if not grid.occupied[ix][column].any():
            lanes += 1
    return {
        "corridor_area": round(corridor_area, 4),
        "corridor_blocked_area": round(blocked_area, 4),
        "corridor_free_ratio": round(
            1.0 - blocked_area / max(corridor_area, 1e-9), 4
        ),
        "corridor_clear_lane_ratio": round(lanes / max(1, total_lanes), 4),
    }


# ---------------------------------------------------------------------------
# Full report
# ---------------------------------------------------------------------------
def board_report(model: ContainerModel, placements, config, cell: float | None = None) -> dict:
    grid = build_floor_grid(model, placements, cell or config.grid_cell)
    plateaus = plateau_report(grid, config)
    holes = hole_report(grid, config)
    plateaus.pop("_labels", None)
    holes.pop("_labels", None)
    floor_items = [p for p in placements if p.surface == "floor"]
    shelf_items = [p for p in placements if p.surface == "shelf"]
    report = {
        "container_index": model.index,
        "container": model.describe(),
        "placed_total": len(placements),
        "placed_floor": len(floor_items),
        "placed_shelf": len(shelf_items),
        "floor_coverage": round(grid.coverage(), 4),
        "placed_volume": round(sum(p.volume for p in placements), 5),
        "flatness": plateaus,
        "holes": holes,
        "wall_front": wall_front_report(model, placements, config),
        "corridor": corridor_report(grid, model),
        "zones": zone_report(grid, model),
        "support_type_area": {
            SUPPORT_NAMES[int(code)]: round(
                float((grid.support == code)[grid.usable & grid.occupied].sum())
                * grid.cell_area,
                4,
            )
            for code in np.unique(grid.support[grid.usable & grid.occupied])
        } if (grid.usable & grid.occupied).any() else {},
    }
    return report
