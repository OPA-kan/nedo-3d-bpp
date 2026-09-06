"""The board as channels: what a value network sees.

Everything is drawn on rule-alpha's 4 cm floor grid of one container.  Local
structure (holes, terrace edges, rows) is left to the convolutions; global
properties a convolution cannot see -- what is reachable from the opening at
a working height, where the shelf and the chamfer are -- are computed
geometrically and handed over as channels, the way liberties are handed to
a Go network.  Nothing here is a score.
"""

from __future__ import annotations

import numpy as np

from rule_alpha import diagnostics as diag
from rule_alpha._reuse import packed_aabbs_local, shelf_aabbs

REACH_HEIGHTS = (0.0, 0.4, 0.8)
CANVAS = (48, 40)
CHANNELS = (
    "height", "occupied",
    "top_hard", "top_soft", "top_priority", "top_soft_priority",
    "usable", "pocket", "shelf_footprint", "shelf_height", "shelf_occupied",
    "reach_0", "reach_04", "reach_08",
    "coord_x", "coord_y",
)


def _reach_mask(grid, z_floor: float, z_rel: float) -> np.ndarray:
    height = grid.height - z_floor
    running = np.maximum.accumulate(height, axis=1)
    before = np.concatenate([np.zeros((height.shape[0], 1)), running[:, :-1]], axis=1)
    usable = grid.usable & (height <= z_rel + 1e-9)
    return usable & (before <= z_rel + 1e-9)


def _shelf_layers(board, idx, grid, config):
    """Height above the shelf plane of whatever rests on a shelf, and the
    shelf footprint, on the floor grid's cells."""
    model = board.model(idx)
    container = board.container(idx)
    footprint = np.zeros(grid.height.shape, dtype=bool)
    height = np.zeros(grid.height.shape, dtype=np.float64)
    occupied = np.zeros(grid.height.shape, dtype=bool)
    shelves = list(shelf_aabbs(container))
    if not shelves:
        return footprint, height, occupied, 0.0
    shelf_top = 0.0
    for shelf in shelves:
        footprint |= grid.rect_mask(diag.Rect(
            float(shelf.minimum[0]), float(shelf.maximum[0]),
            float(shelf.minimum[1]), float(shelf.maximum[1])))
        shelf_top = max(shelf_top, float(shelf.maximum[2]))
    sink = float(getattr(config, "settle_sink_allowance", 0.0) or 0.0)
    for box, _soft, _prio in packed_aabbs_local(container):
        bottom = float(box.minimum[2])
        if bottom < shelf_top - config.contact_tolerance - sink:
            continue
        rect = diag.Rect(float(box.minimum[0]), float(box.maximum[0]),
                         float(box.minimum[1]), float(box.maximum[1]))
        mask = grid.rect_mask(rect)
        top_rel = float(box.maximum[2]) - shelf_top
        height[mask] = np.maximum(height[mask], top_rel)
        occupied |= mask
    return footprint, height, occupied, shelf_top


def board_tensor(board, idx: int, config) -> tuple[np.ndarray, dict]:
    """(C, nx, ny) float32 channels plus a dict of scalar summaries."""
    model = board.model(idx)
    grid = board.grid(idx)
    z_floor = model.z_floor
    height_norm = max(model.height, 1e-9)
    rel = np.clip((grid.height - z_floor) / height_norm, 0.0, 1.5)

    shelf_fp, shelf_h, shelf_occ, shelf_top = _shelf_layers(board, idx, grid, config)
    pocket = (~grid.usable) & (grid.xx < model.x_floor_min)
    nx, ny = grid.height.shape
    cx = np.broadcast_to(np.linspace(0.0, 1.0, nx)[:, None], (nx, ny))
    cy = np.broadcast_to(np.linspace(0.0, 1.0, ny)[None, :], (nx, ny))

    channels = [
        rel,
        grid.occupied,
        grid.occupied & (grid.support == diag.SUPPORT_HARD),
        grid.occupied & (grid.support == diag.SUPPORT_SOFT),
        grid.occupied & (grid.support == diag.SUPPORT_PRIORITY),
        grid.occupied & (grid.support == diag.SUPPORT_SOFT_PRIORITY),
        grid.usable,
        pocket,
        shelf_fp,
        np.clip(shelf_h / height_norm, 0.0, 1.5),
        shelf_occ,
        _reach_mask(grid, z_floor, REACH_HEIGHTS[0]),
        _reach_mask(grid, z_floor, REACH_HEIGHTS[1]),
        _reach_mask(grid, z_floor, REACH_HEIGHTS[2]),
        cx, cy,
    ]
    X = np.stack([np.asarray(c, dtype=np.float32) for c in channels])
    # every container is drawn on the same canvas so batches can be stacked:
    # 1.92 x 1.37 m of usable floor at 4 cm is 48 x 35 cells, the shelf ULD
    # 48 x 37; zero padding at the back and right marks "outside"
    pad_x = max(0, CANVAS[0] - X.shape[1]); pad_y = max(0, CANVAS[1] - X.shape[2])
    X = np.pad(X, ((0, 0), (0, pad_x), (0, pad_y)))[:, :CANVAS[0], :CANVAS[1]]

    cell_area = grid.cell_area
    hard_top = float((grid.usable & grid.occupied & (grid.support == diag.SUPPORT_HARD)).sum()) * cell_area
    reach0 = float(channels[11].sum()) * cell_area
    usable_at_04 = float((grid.usable & ((grid.height - z_floor) <= 0.4 + 1e-9)).sum()) * cell_area
    sealed_04 = usable_at_04 - float(channels[12].sum()) * cell_area
    plateau = board.plateau_stats(idx).get("largest", 0.0)
    shelf_free = float((shelf_fp & ~shelf_occ).sum()) * cell_area
    placed = board.container(idx).get("packed_items", [])
    volume = sum(float(np.prod(b.size)) for b, _s, _p in packed_aabbs_local(board.container(idx)))
    summary = {
        "hard_top_area": hard_top,
        "reach_free_0": reach0,
        "sealed_04": max(0.0, sealed_04),
        "largest_hard_plateau": float(plateau),
        "shelf_free_area": shelf_free,
        "fill_ratio": volume / max(model.usable_volume, 1e-9),
        "placed_count": float(len(placed)),
        "is_prioritized": float(model.is_prioritized),
        "has_shelf": float(model.has_shelf),
    }
    return X, summary


SUMMARY_KEYS = ("hard_top_area", "reach_free_0", "sealed_04", "largest_hard_plateau",
                "shelf_free_area", "fill_ratio", "placed_count", "is_prioritized", "has_shelf")


def summary_vector(summary: dict) -> np.ndarray:
    return np.asarray([summary[k] for k in SUMMARY_KEYS], dtype=np.float32)
