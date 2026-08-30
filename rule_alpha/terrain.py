"""What terrain does Layer 1 actually leave behind?

Read-only.  Nothing here feeds back into the planner: it exists to answer the
question a Layer 2 design has to start from — *what surface am I handed?* — and
to say how close the shipped Layer 1 already is to a target zoning.

The reporting partition is a 4 x 2 grid of the floor plus the shelf:

        y = back  +Y  (far from the opening)
    ┌─────────┬────────┬──────────────┬────────┐
    │ chamfer │  left  │    centre    │ right  │   back half
    ├─────────┼────────┼──────────────┼────────┤
    │ chamfer │  left  │    centre    │ right  │   front half
    └─────────┴────────┴──────────────┴────────┘
        y = front -Y  (the opening / transport entry)
      -X                                        +X

``chamfer`` is the wall-front strip over the bevel, ``left`` / ``right`` are the
edge bands, ``centre`` is everything between them.  The split in ``y`` is the
midpoint of the usable depth, which is the line the "back-first" rule is about.

This is a *reporting* partition and deliberately not the same object as
``ContainerModel.zones``, which is what the rules steer by.  Keeping them
separate is the point: it lets the report say how far the enforced zones and
the intended zoning have drifted apart.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from . import classify as cls
from .diagnostics import (
    SUPPORT_FREE,
    SUPPORT_HARD,
    SUPPORT_NAMES,
    SUPPORT_SOFT,
    SUPPORT_SOFT_PRIORITY,
    build_floor_grid,
    connected_components,
    largest_rectangle_in_mask,
    order_report,
    volume_report,
)
from .geometry import ContainerModel, Rect


X_BANDS = ("chamfer", "left", "centre", "right")
Y_BANDS = ("back", "front")
CELLS = tuple(f"{x}-{y}" for y in Y_BANDS for x in X_BANDS)


# ---------------------------------------------------------------------------
# Partition
# ---------------------------------------------------------------------------
def band_edges(model: ContainerModel, config) -> dict:
    """The x cut lines and the single y cut line of the reporting partition."""
    rect = model.floor_rect
    usable_len = rect.x_max - rect.x_min
    wall_strip = config.wall_front_strip_fraction * usable_len
    edge_w = config.edge_band_fraction * usable_len
    return {
        "x0": rect.x_min,
        "x_chamfer": rect.x_min + wall_strip,
        "x_left": rect.x_min + wall_strip + edge_w,
        "x_right": rect.x_max - edge_w,
        "x1": rect.x_max,
        "y0": rect.y_min,
        "y_mid": 0.5 * (rect.y_min + rect.y_max),
        "y1": rect.y_max,
    }


def cell_rects(model: ContainerModel, config) -> dict:
    """``{cell name: Rect}`` for the 4 x 2 reporting partition."""
    e = band_edges(model, config)
    xs = {
        "chamfer": (e["x0"], e["x_chamfer"]),
        "left": (e["x_chamfer"], e["x_left"]),
        "centre": (e["x_left"], e["x_right"]),
        "right": (e["x_right"], e["x1"]),
    }
    ys = {"back": (e["y_mid"], e["y1"]), "front": (e["y0"], e["y_mid"])}
    out = {}
    for yname, (y_min, y_max) in ys.items():
        for xname, (x_min, x_max) in xs.items():
            out[f"{xname}-{yname}"] = Rect(x_min, x_max, y_min, y_max)
    return out


def cell_of(x: float, y: float, model: ContainerModel, config) -> str:
    e = band_edges(model, config)
    if x < e["x_chamfer"]:
        xband = "chamfer"
    elif x < e["x_left"]:
        xband = "left"
    elif x < e["x_right"]:
        xband = "centre"
    else:
        xband = "right"
    return f"{xband}-{'back' if y >= e['y_mid'] else 'front'}"


def placement_cell(placement, model: ContainerModel, config) -> str:
    """Which cell an item's *footprint centroid* falls in."""
    rect = placement.rect
    return cell_of(
        0.5 * (rect.x_min + rect.x_max), 0.5 * (rect.y_min + rect.y_max), model, config
    )


# ---------------------------------------------------------------------------
# 1. Where does normal-hard floor cargo sit?
# ---------------------------------------------------------------------------
def _norm(value: float, lo: float, hi: float) -> float:
    span = hi - lo
    return 0.0 if span <= 0 else (value - lo) / span


def normal_hard_report(model: ContainerModel, placements, config) -> dict:
    """Bias of the normal-hard floor layer, in normalised floor coordinates.

    ``x_centroid`` / ``y_centroid`` are area-weighted and scaled to [0, 1] over
    the usable floor, so 0.5 is dead centre and ``y_centroid > 0.5`` means the
    hard cargo really did go to the back.
    """
    rect = model.floor_rect
    floor_hard = [
        p for p in placements
        if p.surface == "floor" and p.profile.cargo_class == cls.NORMAL_HARD
    ]
    total_area = sum(p.rect.area for p in floor_hard)
    cells = {name: 0.0 for name in CELLS}
    for p in floor_hard:
        cells[placement_cell(p, model, config)] += p.rect.area

    if total_area <= 0:
        return {
            "count": 0, "footprint_m2": 0.0, "x_centroid": None, "y_centroid": None,
            "back_share": None, "centre_share": None,
            "cell_share": {k: 0.0 for k in CELLS},
            "height_by_y_third": [None, None, None],
        }

    cx = sum(p.rect.area * 0.5 * (p.rect.x_min + p.rect.x_max) for p in floor_hard)
    cy = sum(p.rect.area * 0.5 * (p.rect.y_min + p.rect.y_max) for p in floor_hard)
    cx /= total_area
    cy /= total_area

    # Is the "back is higher" terrain there yet?  Mean top height of hard floor
    # cargo in each third of the depth, front third first.
    thirds: list[list[float]] = [[], [], []]
    depth = rect.y_max - rect.y_min
    for p in floor_hard:
        mid_y = 0.5 * (p.rect.y_min + p.rect.y_max)
        k = min(2, max(0, int((mid_y - rect.y_min) / max(depth, 1e-9) * 3)))
        thirds[k].append(p.top_z - model.z_floor)

    # The terrace question is about the *foundation slab*, so the structural
    # members are masked out the same way ``foundation_slab_fill_ratio`` masks
    # them: the wall front is meant to be tall and runs the whole depth, so
    # averaging it into the depth thirds reports a front wall that is really
    # just the chamfer wall seen end-on.
    slab: list[list[float]] = [[], [], []]
    for p in floor_hard:
        if p.is_structural:
            continue
        mid_y = 0.5 * (p.rect.y_min + p.rect.y_max)
        k = min(2, max(0, int((mid_y - rect.y_min) / max(depth, 1e-9) * 3)))
        slab[k].append(p.top_z - model.z_floor)

    back = sum(v for k, v in cells.items() if k.endswith("-back"))
    centre = sum(v for k, v in cells.items() if k.startswith("centre-"))
    return {
        "count": len(floor_hard),
        "footprint_m2": round(total_area, 4),
        "x_centroid": round(_norm(cx, rect.x_min, rect.x_max), 3),
        "y_centroid": round(_norm(cy, rect.y_min, rect.y_max), 3),
        "back_share": round(back / total_area, 3),
        "centre_share": round(centre / total_area, 3),
        "cell_share": {k: round(v / total_area, 3) for k, v in cells.items()},
        "height_by_y_third": [
            round(sum(t) / len(t), 3) if t else None for t in thirds
        ],
        "slab_height_by_y_third": [
            round(sum(t) / len(t), 3) if t else None for t in slab
        ],
    }


# ---------------------------------------------------------------------------
# 2. Tall structure: is the perimeter filled from the back?
# ---------------------------------------------------------------------------
TALL_ROLES = (cls.ROLE_TALL_PERIMETER, cls.ROLE_WALL_FRONT, cls.ROLE_ELONGATED)


def tall_report(model: ContainerModel, placements, config) -> dict:
    rows = []
    for p in sorted(placements, key=lambda p: p.step):
        if p.surface == "shelf" or p.role not in TALL_ROLES:
            continue
        rows.append(
            {
                "step": p.step,
                "role": p.role,
                "cell": placement_cell(p, model, config),
                "height_m": round(p.top_z - model.z_floor, 3),
                "footprint_m2": round(p.rect.area, 4),
                "class": p.profile.cargo_class,
            }
        )
    perimeter = [r for r in rows if r["role"] == cls.ROLE_TALL_PERIMETER]
    back = [r for r in perimeter if r["cell"].endswith("-back")]
    # "back first" here means: of the perimeter items, did the back ones go
    # down before the front ones?  Compare median step.
    back_steps = [r["step"] for r in back]
    front_steps = [r["step"] for r in perimeter if not r["cell"].endswith("-back")]
    return {
        "items": rows,
        "tall_perimeter_count": len(perimeter),
        "tall_perimeter_back_share": (
            round(len(back) / len(perimeter), 3) if perimeter else None
        ),
        "tall_perimeter_median_step_back": _median(back_steps),
        "tall_perimeter_median_step_front": _median(front_steps),
    }


def _median(values):
    if not values:
        return None
    ordered = sorted(values)
    n = len(ordered)
    return float(ordered[n // 2]) if n % 2 else round(
        0.5 * (ordered[n // 2 - 1] + ordered[n // 2]), 1
    )


# ---------------------------------------------------------------------------
# 3/6. The surface itself: height map with a support type per cell
# ---------------------------------------------------------------------------
@dataclass
class Terrain:
    grid: object
    cells: dict = field(default_factory=dict)

    @property
    def height(self):
        return self.grid.height

    @property
    def support(self):
        return self.grid.support


def build_terrain(model: ContainerModel, placements, config) -> Terrain:
    grid = build_floor_grid(model, placements, config.grid_cell, config)
    return Terrain(grid=grid, cells=cell_rects(model, config))


def support_area_report(terrain: Terrain, model: ContainerModel) -> dict:
    grid = terrain.grid
    out = {}
    for code, name in SUPPORT_NAMES.items():
        mask = grid.usable & (grid.support == code)
        if code == SUPPORT_FREE:
            mask = grid.free_mask()
        out[name] = round(float(mask.sum()) * grid.cell_area, 4)
    return out


def height_band_report(terrain: Terrain, model: ContainerModel,
                       edges=(0.0, 0.15, 0.30, 0.50, 0.80)) -> dict:
    """How much of the usable floor sits in each height band."""
    grid = terrain.grid
    rel = grid.height - model.z_floor
    out = {}
    bounds = list(edges) + [float("inf")]
    for lo, hi in zip(bounds[:-1], bounds[1:]):
        mask = grid.usable & (rel >= lo - 1e-9) & (rel < hi - 1e-9)
        label = f"{lo:.2f}-{hi:.2f}" if math.isfinite(hi) else f"{lo:.2f}+"
        out[label] = round(float(mask.sum()) * grid.cell_area, 4)
    return out


def buildable_report(terrain: Terrain, model: ContainerModel, config) -> dict:
    """How much of the surface Layer 2 could actually build on.

    "Buildable" is deliberately strict: hard top (or bare floor), and part of a
    plateau at least ``min_pad`` on a side, because a hard top too small to take
    a box is not a support surface — it is roughness.
    """
    grid = terrain.grid
    hard = grid.usable & ((grid.support == SUPPORT_HARD) | (~grid.occupied))
    soft_capped = grid.usable & (grid.support != SUPPORT_HARD) & grid.occupied

    tol = config.plateau_height_tolerance
    quantised = np.round(grid.height / max(tol, 1e-6)).astype(np.int64)
    min_cells = max(1, int(round(0.30 / grid.cell)))  # a 0.30 m square
    buildable_cells = 0
    pads = []
    for level in np.unique(quantised[hard]):
        mask = hard & (quantised == level)
        labels, count = connected_components(mask)
        for label in range(1, count + 1):
            comp = labels == label
            cells, box = largest_rectangle_in_mask(comp)
            r0, c0, r1, c1 = box
            side_r, side_c = (r1 - r0 + 1), (c1 - c0 + 1)
            if cells and side_r >= min_cells and side_c >= min_cells:
                buildable_cells += int(comp.sum())
                pads.append(
                    {
                        "height_m": round(
                            float(grid.height[comp].mean()) - model.z_floor, 3
                        ),
                        "area_m2": round(float(comp.sum()) * grid.cell_area, 4),
                        "rect_m2": round(cells * grid.cell_area, 4),
                        "rect_size_m": [
                            round(side_r * grid.cell, 2), round(side_c * grid.cell, 2)
                        ],
                    }
                )
    pads.sort(key=lambda p: -p["rect_m2"])
    return {
        "buildable_area_m2": round(buildable_cells * grid.cell_area, 4),
        "buildable_ratio": round(
            buildable_cells * grid.cell_area / max(grid.usable_area, 1e-9), 3
        ),
        "soft_capped_area_m2": round(
            float(soft_capped.sum()) * grid.cell_area, 4
        ),
        "pad_count": len(pads),
        "pads": pads[:6],
    }


def cell_terrain_report(terrain: Terrain, model: ContainerModel,
                        placements, config) -> dict:
    """Per reporting cell: coverage, height, support mix, what is standing."""
    grid = terrain.grid
    by_cell: dict[str, list] = {name: [] for name in CELLS}
    for p in placements:
        if p.surface == "shelf":
            continue
        by_cell[placement_cell(p, model, config)].append(p)

    out = {}
    for name, rect in terrain.cells.items():
        mask = grid.usable & grid.rect_mask(rect)
        area = float(mask.sum()) * grid.cell_area
        if area <= 0:
            out[name] = {"usable_m2": 0.0}
            continue
        occupied = mask & grid.occupied
        rel = grid.height - model.z_floor
        items = by_cell[name]
        out[name] = {
            "usable_m2": round(area, 4),
            "coverage": round(float(occupied.sum()) * grid.cell_area / area, 3),
            "mean_height_m": round(float(rel[mask].mean()), 3),
            "max_height_m": round(float(rel[mask].max()), 3),
            "hard_top_m2": round(
                float((mask & (grid.support == SUPPORT_HARD)).sum())
                * grid.cell_area, 4
            ),
            "soft_top_m2": round(
                float((mask & np.isin(
                    grid.support, [SUPPORT_SOFT, SUPPORT_SOFT_PRIORITY]
                )).sum())
                * grid.cell_area, 4
            ),
            "items": len(items),
            "classes": _histogram(p.profile.cargo_class for p in items),
            "roles": _histogram(p.role for p in items if p.role != cls.ROLE_NONE),
            "first_step": min((p.step for p in items), default=None),
            "median_step": _median([p.step for p in items]),
        }
    return out


def _histogram(values) -> dict:
    out: dict[str, int] = {}
    for value in values:
        out[value] = out.get(value, 0) + 1
    return out


# ---------------------------------------------------------------------------
# 4. Shelf usage and the overflow that missed it
# ---------------------------------------------------------------------------
def shelf_report(model: ContainerModel, placements, config) -> dict:
    """How much of the volume above the shelf got used, and who missed it.

    ``headroom_volume`` is the shelf top plane to the ceiling — the space the
    zoning wants soft / priority cargo to consume before anything goes to the
    floor.
    """
    on_shelf = [p for p in placements if p.surface == "shelf"]
    soft_or_priority_on_floor = [
        p for p in placements
        if p.surface == "floor"
        and (p.profile.is_soft or p.profile.is_prioritized)
    ]
    placed_volume = sum(float(np.prod(p.box.size)) for p in on_shelf)

    if not model.shelves:
        return {
            "has_shelf": False,
            "headroom_m": 0.0,
            "headroom_volume_m3": 0.0,
            "shelf_volume_used_m3": round(placed_volume, 4),
            "shelf_fill_ratio": None,
            "shelf_items": len(on_shelf),
            "overflow_items": len(soft_or_priority_on_floor),
            "overflow_volume_m3": round(
                sum(float(np.prod(p.box.size))
                    for p in soft_or_priority_on_floor), 4
            ),
            "max_used_height_m": 0.0,
            "back_share_of_shelf_area": None,
        }

    headroom = 0.0
    headroom_volume = 0.0
    shelf_area = 0.0
    for shelf in model.shelves:
        top = float(shelf.maximum[2])
        rect = model.shelf_rect(shelf)
        gap = max(0.0, model.z_ceiling - top)
        headroom = max(headroom, gap)
        headroom_volume += gap * rect.area
        shelf_area += rect.area

    used_heights = [
        float(p.box.maximum[2]) - float(p.box.minimum[2]) for p in on_shelf
    ]
    # how far back on the shelf the cargo actually went
    back_area = 0.0
    total_area = 0.0
    for p in on_shelf:
        total_area += p.rect.area
        mid_y = 0.5 * (p.rect.y_min + p.rect.y_max)
        if mid_y >= 0.5 * (model.floor_rect.y_min + model.floor_rect.y_max):
            back_area += p.rect.area

    return {
        "has_shelf": True,
        "headroom_m": round(headroom, 3),
        "headroom_volume_m3": round(headroom_volume, 4),
        "shelf_area_m2": round(shelf_area, 4),
        "shelf_volume_used_m3": round(placed_volume, 4),
        "shelf_fill_ratio": round(placed_volume / max(headroom_volume, 1e-9), 3),
        "shelf_items": len(on_shelf),
        "shelf_footprint_ratio": round(total_area / max(shelf_area, 1e-9), 3),
        "max_used_height_m": round(max(used_heights), 3) if used_heights else 0.0,
        "headroom_height_used_ratio": (
            round(max(used_heights) / max(headroom, 1e-9), 3) if used_heights else 0.0
        ),
        "back_share_of_shelf_area": (
            round(back_area / total_area, 3) if total_area > 0 else None
        ),
        "overflow_items": len(soft_or_priority_on_floor),
        "overflow_volume_m3": round(
            sum(float(np.prod(p.box.size)) for p in soft_or_priority_on_floor), 4
        ),
    }


# ---------------------------------------------------------------------------
# 5. What is left of the way in
# ---------------------------------------------------------------------------
def access_report(terrain: Terrain, model: ContainerModel, config) -> dict:
    """The front-centre approach, as free area *and* as free height.

    Free area alone flatters the board: a lane that is clear on the floor but
    roofed at 0.2 m is not an approach.  ``min_clear_height`` is the worst
    column height over the corridor footprint.
    """
    grid = terrain.grid
    corridor = grid.rect_mask(model.corridor) & grid.usable
    rel = grid.height - model.z_floor

    e = band_edges(model, config)
    front_centre = grid.usable & grid.rect_mask(
        Rect(e["x_left"], e["x_right"], e["y0"], e["y_mid"])
    )

    def _stats(mask):
        if not mask.any():
            return {"area_m2": 0.0, "free_ratio": None,
                    "mean_height_m": None, "max_height_m": None}
        free = mask & ~grid.occupied
        return {
            "area_m2": round(float(mask.sum()) * grid.cell_area, 4),
            "free_ratio": round(float(free.sum()) / float(mask.sum()), 3),
            "mean_height_m": round(float(rel[mask].mean()), 3),
            "max_height_m": round(float(rel[mask].max()), 3),
        }

    # a clear lane is a full-depth run of free cells at some x
    lane = np.zeros(grid.nx, dtype=bool)
    front_rows = grid.usable & grid.rect_mask(
        Rect(e["x0"], e["x1"], e["y0"], e["y_mid"])
    )
    for i in range(grid.nx):
        column = front_rows[i]
        if column.any():
            lane[i] = bool((~grid.occupied[i][column]).all())

    return {
        "corridor": _stats(corridor),
        "front_centre": _stats(front_centre),
        "approach": approach_clearance(terrain, model),
        "reach": reach_report(terrain, model),
        "clear_lane_width_m": round(float(lane.sum()) * grid.cell, 3),
        "front_half_max_height_m": round(
            float(rel[front_rows].max()) if front_rows.any() else 0.0, 3
        ),
        "back_half_mean_height_m": round(
            float(
                rel[grid.usable & grid.rect_mask(
                    Rect(e["x0"], e["x1"], e["y_mid"], e["y1"])
                )].mean()
            ), 3
        ),
    }


def approach_clearance(terrain: Terrain, model: ContainerModel) -> dict:
    """How tall an item could still be walked in, column by column.

    An approximation of the real transport check, and labelled as one: the
    validator sweeps in ``y`` at a clamped entry ``x`` and then in ``x`` at the
    target ``y``, while this asks the simpler question "at this ``x``, what is
    the worst headroom between the built surface and whatever is above it".
    The ceiling is the shelf underside where a shelf overhangs, and the
    container ceiling elsewhere, because an item entering below a shelf never
    gets the full height.

    It is the right shape of number for a Layer 2 discussion: it says which
    columns are still *reachable at all*, which free-floor area alone does not.
    """
    grid = terrain.grid
    ceiling = np.full(grid.height.shape, model.z_ceiling, dtype=np.float64)
    for shelf in model.shelves:
        rect = model.shelf_rect(shelf)
        ceiling[grid.rect_mask(rect)] = min(
            float(shelf.minimum[2]), model.z_ceiling
        )

    front = grid.usable & (grid.yy < 0.5 * (model.y_opening + model.y_back))
    clearance = np.where(front, ceiling - grid.height, np.nan)
    with np.errstate(invalid="ignore"):
        per_column = np.nanmin(
            np.where(np.isnan(clearance), np.inf, clearance), axis=1
        )
    per_column = np.where(front.any(axis=1), per_column, np.nan)
    valid = per_column[~np.isnan(per_column)]
    if valid.size == 0:
        return {"width_m": 0.0}

    width = float(valid.size) * grid.cell
    return {
        "width_m": round(width, 3),
        "median_clearance_m": round(float(np.median(valid)), 3),
        "max_clearance_m": round(float(valid.max()), 3),
        "width_over_0.30m": round(float((valid >= 0.30).sum()) * grid.cell, 3),
        "width_over_0.50m": round(float((valid >= 0.50).sum()) * grid.cell, 3),
        "width_over_0.70m": round(float((valid >= 0.70).sum()) * grid.cell, 3),
    }


def reach_report(terrain: Terrain, model: ContainerModel,
                 heights=(0.0, 0.20, 0.40, 0.60)) -> dict:
    """How much of the floor plan can still be *reached*, by target height.

    The official validator sweeps in along ``y`` at an entry ``x`` and then
    along ``x`` at the target ``y``, where the entry ``x`` is the *target*
    ``x`` clamped only far enough inboard for the box to fit laterally
    (``transport_sweeps`` in ``agent/agent.py``).  For any target away from the
    two side walls the clamp does nothing, the lateral leg is degenerate, and
    the path is exactly the straight-in sweep modelled here: an item whose
    underside is at ``z_b`` gets in along column ``x`` only if everything
    already standing between the opening and its target is at or below ``z_b``.

    Two known deviations, both stated rather than hidden.  Near the side walls
    the real check gets a short lateral leg this does not model.  And an item
    that will land on a stack is swept at drop height, *above* its own
    underside, so the rows above ``0.00`` are conservative — the real check is
    harder than this, not easier.  The ``0.00`` row, the floor case, is exact:
    a floor-resting item is swept at its own height.

    That is the number a Layer 2 design needs and free floor area does not
    give: a back cell can be empty and still be unreachable, because the way in
    is walled off.
    """
    grid = terrain.grid
    rel = np.where(grid.usable, grid.height - model.z_floor, 0.0)
    # running max from the opening (-Y, index 0) inwards
    blocking = np.maximum.accumulate(rel, axis=1)
    # a cell is blocked by what stands *before* it, not by itself
    before = np.concatenate(
        [np.zeros((grid.nx, 1)), blocking[:, :-1]], axis=1
    )

    mid = 0.5 * (model.y_opening + model.y_back)
    back = grid.usable & (grid.yy >= mid)
    free = grid.free_mask()
    out = {}
    for z_b in heights:
        reachable = grid.usable & (before <= z_b + 1e-9)
        out[f"{z_b:.2f}"] = {
            "reachable_ratio": round(
                float(reachable.sum()) / max(float(grid.usable.sum()), 1.0), 3
            ),
            "reachable_free_m2": round(
                float((reachable & free).sum()) * grid.cell_area, 4
            ),
            "reachable_back_ratio": round(
                float((reachable & back).sum()) / max(float(back.sum()), 1.0), 3
            ),
        }
    return out


# ---------------------------------------------------------------------------
# Everything, for one container
# ---------------------------------------------------------------------------
def container_terrain(model: ContainerModel, placements, config) -> dict:
    terrain = build_terrain(model, placements, config)
    front_mean = access_report(terrain, model, config)
    return {
        "container_index": model.index,
        "has_shelf": model.has_shelf,
        "is_prioritized": model.is_prioritized,
        "placed_total": len(placements),
        "normal_hard": normal_hard_report(model, placements, config),
        "tall": tall_report(model, placements, config),
        "cells": cell_terrain_report(terrain, model, placements, config),
        "support_area": support_area_report(terrain, model),
        "height_bands": height_band_report(terrain, model),
        "buildable": buildable_report(terrain, model, config),
        "shelf": shelf_report(model, placements, config),
        "access": front_mean,
        "order": order_report(model, placements),
        "volume": volume_report(model, placements, config),
        "compaction": compaction_report(placements),
    }


def compaction_report(placements) -> dict:
    """How much slack the backward compaction actually took out."""
    moved = [
        p for p in placements
        if p.surface == "floor" and abs(p.features.get("compacted_y_m", 0.0)) > 1e-6
    ]
    if not moved:
        return {"items_moved": 0, "total_y_m": 0.0, "max_y_m": 0.0, "total_x_m": 0.0}
    ys = [float(p.features.get("compacted_y_m", 0.0)) for p in moved]
    xs = [abs(float(p.features.get("compacted_x_m", 0.0))) for p in placements]
    return {
        "items_moved": len(moved),
        "total_y_m": round(sum(ys), 4),
        "max_y_m": round(max(ys), 4),
        "total_x_m": round(sum(xs), 4),
    }
