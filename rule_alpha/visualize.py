"""Pictures of a rule-alpha Layer 1 board.

Four views per container:

* top view          - what the floor plan looks like
* opening view      - looking along +X: depth vs height, opening on the left
* slope view        - looking along +Y: the chamfer cross section and the wall
                      front built against it
* diagnostic overlay- plateaus, holes, zones, structural mask, corridor, pocket

Matplotlib only; nothing here needs PyBullet.
"""

from __future__ import annotations

import pathlib

import matplotlib

matplotlib.use("Agg")

import matplotlib.patches as patches
import matplotlib.patheffects as path_effects
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D

from . import classify as cls
from .diagnostics import (
    build_floor_grid,
    hole_report,
    plateau_report,
)
from .geometry import ContainerModel


CLASS_COLOR = {
    cls.NORMAL_HARD: "#c8a06a",
    cls.SOFT: "#5b8dd9",
    cls.PRIORITY: "#5fbf6a",
    cls.SOFT_PRIORITY: "#9b6fd0",
}
ROLE_EDGE = {
    cls.ROLE_NONE: ("#3a3a3a", 1.0, "solid"),
    cls.ROLE_WALL_FRONT: ("#c0392b", 2.4, "solid"),
    cls.ROLE_ELONGATED: ("#e07b00", 2.0, "dashed"),
    cls.ROLE_SLOPE_INFILL: ("#b52ea8", 2.2, "dashdot"),
    cls.ROLE_TALL_PERIMETER: ("#1f7a8c", 2.2, "solid"),
    cls.ROLE_WEDGE_STEP: ("#7a5c00", 2.2, "dashdot"),
    # Layer 2 growth families, so a picture can answer "which of these is
    # Layer 2 and what kind" without cross-referencing the step log
    "terrace": ("#00a2a2", 2.6, "solid"),
    "bridge": ("#d81b60", 3.0, "solid"),
    "wedge-bridge": ("#8e24aa", 3.0, "dashed"),
    "hole-fill": ("#2e7d32", 2.6, "dotted"),
    "typed-cap": ("#f9a825", 2.6, "dashdot"),
    "last-resort": ("#6d4c41", 2.4, "dotted"),
    "front-wedge": ("#00838f", 2.8, "dashed"),
}
ZONE_STYLE = {
    "wall_front_strip": ("#c0392b", "slope wall-front strip"),
    "soft_zone": ("#5b8dd9", "soft zone"),
    "priority_zone": ("#5fbf6a", "priority / SP zone"),
    "corridor": ("#d93b3b", "transport corridor"),
    "back_band": ("#666666", "back foundation band"),
}


def _cross_section(model: ContainerModel):
    """Pentagon of the inner cross section in the (x, z) plane."""
    return [
        (model.x_floor_min, model.z_floor),
        (model.x_wall_max, model.z_floor),
        (model.x_wall_max, model.z_ceiling),
        (model.x_wall_min, model.z_ceiling),
        (model.x_wall_min, model.z_chamfer_top),
    ]


def _zone_patch(ax, rect, color, alpha=0.10):
    ax.add_patch(
        patches.Rectangle(
            (rect.x_min, rect.y_min),
            rect.x_max - rect.x_min,
            rect.y_max - rect.y_min,
            facecolor=color, edgecolor="none", alpha=alpha, zorder=1,
        )
    )
    ax.add_patch(
        patches.Rectangle(
            (rect.x_min, rect.y_min),
            rect.x_max - rect.x_min,
            rect.y_max - rect.y_min,
            fill=False, edgecolor=color, alpha=0.9,
            linewidth=1.2, linestyle="--", zorder=2,
        )
    )


# ---------------------------------------------------------------------------
# Panels
# ---------------------------------------------------------------------------
def draw_top(ax, model: ContainerModel, placements, show_zones=True):
    ax.set_title(f"top view  (container {model.index})", fontsize=10)
    ax.set_xlabel("x  [m]   <- chamfer / small shelf side")
    ax.set_ylabel("y  [m]   opening -Y  ...  back +Y")

    # container walls
    ax.add_patch(
        patches.Rectangle(
            (model.x_wall_min, model.y_opening),
            model.x_wall_max - model.x_wall_min,
            model.y_back - model.y_opening,
            fill=False, edgecolor="#222222", linewidth=1.8, zorder=4,
        )
    )
    # region the chamfer takes away from the floor
    ax.add_patch(
        patches.Rectangle(
            (model.x_wall_min, model.y_opening),
            model.x_floor_min - model.x_wall_min,
            model.y_back - model.y_opening,
            facecolor="#bbbbbb", edgecolor="none", alpha=0.55, zorder=0,
        )
    )
    ax.text(
        (model.x_wall_min + model.x_floor_min) / 2.0,
        (model.y_opening + model.y_back) / 2.0,
        "slope\npocket\n(no floor)",
        ha="center", va="center", fontsize=7, color="#444444", rotation=90, zorder=1,
    )

    if show_zones:
        for name, (color, _label) in ZONE_STYLE.items():
            _zone_patch(ax, getattr(model, name), color, alpha=0.07)

    for shelf in model.shelves:
        ax.add_patch(
            patches.Rectangle(
                (float(shelf.minimum[0]), float(shelf.minimum[1])),
                float(shelf.size[0]), float(shelf.size[1]),
                fill=False, edgecolor="#7d3cbd", linewidth=1.4, linestyle=":", zorder=3,
            )
        )

    floor_items = [p for p in placements if p.surface != "shelf"]
    shelf_items = [p for p in placements if p.surface == "shelf"]
    for placement in floor_items + shelf_items:
        rect = placement.rect
        edge, width, style = ROLE_EDGE.get(placement.role, ROLE_EDGE[cls.ROLE_NONE])
        on_shelf = placement.surface == "shelf"
        ax.add_patch(
            patches.Rectangle(
                (rect.x_min, rect.y_min),
                rect.x_max - rect.x_min,
                rect.y_max - rect.y_min,
                facecolor=CLASS_COLOR[placement.profile.cargo_class],
                edgecolor=edge if not on_shelf else "#7d3cbd",
                linewidth=width,
                linestyle=style if not on_shelf else "dotted",
                alpha=0.50 if on_shelf else 0.85,
                zorder=5 if not on_shelf else 6,
            )
        )
        ax.text(
            0.5 * (rect.x_min + rect.x_max),
            0.5 * (rect.y_min + rect.y_max),
            f"{placement.profile.index}\n{placement.top_z - model.z_floor:.2f}",
            ha="center", va="center", fontsize=6.5,
            color="#111111", zorder=7,
        )

    ax.axvline(model.x_floor_min, color="#c0392b", linewidth=1.0, linestyle="-.")
    ax.set_xlim(model.x_wall_min - 0.05, model.x_wall_max + 0.05)
    ax.set_ylim(model.y_opening - 0.05, model.y_back + 0.05)
    ax.set_aspect("equal")
    ax.tick_params(labelsize=7)


def draw_opening_view(ax, model: ContainerModel, placements):
    """Looking along +X: depth (y) against height (z).  Opening on the left."""
    ax.set_title("opening view  (looking along +X)", fontsize=10)
    ax.set_xlabel("y  [m]   opening -Y  ->  back +Y")
    ax.set_ylabel("z  [m]")

    ax.add_patch(
        patches.Rectangle(
            (model.y_opening, model.z_floor),
            model.y_back - model.y_opening,
            model.z_ceiling - model.z_floor,
            fill=False, edgecolor="#222222", linewidth=1.8,
        )
    )
    for shelf in model.shelves:
        ax.add_patch(
            patches.Rectangle(
                (float(shelf.minimum[1]), float(shelf.minimum[2])),
                float(shelf.size[1]), float(shelf.size[2]),
                facecolor="#7d3cbd", edgecolor="#4b2273", alpha=0.6,
            )
        )
    for placement in sorted(placements, key=lambda p: p.rect.x_min):
        rect = placement.rect
        edge, width, style = ROLE_EDGE.get(placement.role, ROLE_EDGE[cls.ROLE_NONE])
        ax.add_patch(
            patches.Rectangle(
                (rect.y_min, float(placement.box.minimum[2])),
                rect.y_max - rect.y_min,
                float(placement.box.size[2]),
                facecolor=CLASS_COLOR[placement.profile.cargo_class],
                edgecolor=edge, linewidth=width, linestyle=style, alpha=0.45,
            )
        )
    ax.axhline(
        model.z_floor + 0.5 * (model.z_ceiling - model.z_floor),
        color="#c0392b", linestyle=":", linewidth=1.0,
    )
    ax.text(
        model.y_opening + 0.02,
        model.z_floor + 0.5 * (model.z_ceiling - model.z_floor) + 0.01,
        "half height (wall-front target)", fontsize=6, color="#c0392b",
    )
    ax.set_xlim(model.y_opening - 0.05, model.y_back + 0.05)
    ax.set_ylim(0.0, model.height + 0.05)
    ax.set_aspect("equal")
    ax.tick_params(labelsize=7)


def draw_slope_view(ax, model: ContainerModel, placements):
    """Looking along +Y: the chamfer cross section and what stands in front."""
    ax.set_title("slope view  (looking along +Y)", fontsize=10)
    ax.set_xlabel("x  [m]")
    ax.set_ylabel("z  [m]")

    polygon = _cross_section(model)
    ax.add_patch(
        patches.Polygon(polygon, closed=True, fill=False,
                        edgecolor="#222222", linewidth=1.8)
    )
    # the wedge a floor layer can never reach
    ax.add_patch(
        patches.Polygon(
            [
                (model.x_floor_min, model.z_floor),
                (model.x_wall_min, model.z_chamfer_top),
                (model.x_wall_min, model.z_floor),
            ],
            closed=True, facecolor="#bbbbbb", edgecolor="none", alpha=0.6,
        )
    )
    ax.add_patch(
        patches.Rectangle(
            (model.x_wall_min, model.z_floor),
            model.x_floor_min - model.x_wall_min,
            model.slope_pocket["z_max"] - model.z_floor,
            fill=False, edgecolor="#b52ea8", linestyle="--", linewidth=1.2,
        )
    )
    for shelf in model.shelves:
        ax.add_patch(
            patches.Rectangle(
                (float(shelf.minimum[0]), float(shelf.minimum[2])),
                float(shelf.size[0]), float(shelf.size[2]),
                facecolor="#7d3cbd", edgecolor="#4b2273", alpha=0.6,
            )
        )
    for placement in sorted(placements, key=lambda p: -p.rect.y_min):
        rect = placement.rect
        edge, width, style = ROLE_EDGE.get(placement.role, ROLE_EDGE[cls.ROLE_NONE])
        ax.add_patch(
            patches.Rectangle(
                (rect.x_min, float(placement.box.minimum[2])),
                rect.x_max - rect.x_min,
                float(placement.box.size[2]),
                facecolor=CLASS_COLOR[placement.profile.cargo_class],
                edgecolor=edge, linewidth=width, linestyle=style, alpha=0.45,
            )
        )
    ax.axhline(
        model.z_floor + 0.5 * (model.z_ceiling - model.z_floor),
        color="#c0392b", linestyle=":", linewidth=1.0,
    )
    ax.set_xlim(model.x_wall_min - 0.05, model.x_wall_max + 0.05)
    ax.set_ylim(0.0, model.height + 0.05)
    ax.set_aspect("equal")
    ax.tick_params(labelsize=7)




def draw_order(ax, model: ContainerModel, placements):
    """Top view labelled by placement order, with the path between centroids.

    This is the picture for "was it filled from the back forward?".  The arrow
    chain is the order the rules actually chose, so a jump from the back to the
    opening and back again is visible as a zig-zag rather than having to be
    inferred from the step log.
    """
    ax.set_title("placement order (top view)", fontsize=10)
    ax.set_xlabel("x  [m]")
    ax.set_ylabel("y  [m]   opening -Y  ...  back +Y")

    ax.add_patch(
        patches.Rectangle(
            (model.x_wall_min, model.y_opening),
            model.x_wall_max - model.x_wall_min,
            model.y_back - model.y_opening,
            fill=False, edgecolor="#222222", linewidth=1.8, zorder=4,
        )
    )
    ax.add_patch(
        patches.Rectangle(
            (model.x_wall_min, model.y_opening),
            model.x_floor_min - model.x_wall_min,
            model.y_back - model.y_opening,
            facecolor="#bbbbbb", edgecolor="none", alpha=0.55, zorder=0,
        )
    )

    ordered = sorted(placements, key=lambda p: p.step)
    if not ordered:
        ax.set_xlim(model.x_wall_min - 0.05, model.x_wall_max + 0.05)
        ax.set_ylim(model.y_opening - 0.05, model.y_back + 0.05)
        ax.set_aspect("equal")
        return

    palette = plt.get_cmap("viridis")
    span = max(1, len(ordered) - 1)
    centres = []
    for position, placement in enumerate(ordered):
        rect = placement.rect
        colour = palette(position / span)
        on_shelf = placement.surface == "shelf"
        ax.add_patch(
            patches.Rectangle(
                (rect.x_min, rect.y_min),
                rect.x_max - rect.x_min,
                rect.y_max - rect.y_min,
                facecolor=colour,
                edgecolor="#ffffff" if not on_shelf else "#7d3cbd",
                linewidth=1.2,
                linestyle="solid" if not on_shelf else "dotted",
                alpha=0.45 if on_shelf else 0.9,
                zorder=5,
            )
        )
        cx = 0.5 * (rect.x_min + rect.x_max)
        cy = 0.5 * (rect.y_min + rect.y_max)
        centres.append((cx, cy))
        ax.text(
            cx, cy, f"{placement.step}",
            ha="center", va="center", fontsize=8, fontweight="bold",
            color="white", zorder=7,
            path_effects=[
                path_effects.withStroke(linewidth=2.0, foreground="#00000090")
            ],
        )

    for (x0, y0), (x1, y1) in zip(centres, centres[1:]):
        ax.annotate(
            "", xy=(x1, y1), xytext=(x0, y0),
            arrowprops=dict(arrowstyle="->", color="#d62828", lw=1.2,
                            alpha=0.85, shrinkA=6, shrinkB=6),
            zorder=8,
        )

    ax.axvline(model.x_floor_min, color="#c0392b", linewidth=1.0, linestyle="-.")
    ax.set_xlim(model.x_wall_min - 0.05, model.x_wall_max + 0.05)
    ax.set_ylim(model.y_opening - 0.05, model.y_back + 0.05)
    ax.set_aspect("equal")
    ax.tick_params(labelsize=7)


def draw_fill_progression(ax, model: ContainerModel, placements):
    """Depth against step: does the frontier march from the back to the opening?

    Each bar spans the item's depth.  A board that respects "back first" draws
    a staircase falling to the right; a bar that jumps back up after the
    frontier has moved forward is cargo placed behind something already
    packed.
    """
    ax.set_title("fill progression (depth vs step)", fontsize=10)
    ax.set_xlabel("placement step")
    ax.set_ylabel("y  [m]   back +Y  ->  opening -Y")

    ordered = sorted(placements, key=lambda p: p.step)
    frontier = model.y_back
    for placement in ordered:
        rect = placement.rect
        colour = CLASS_COLOR[placement.profile.cargo_class]
        edge, width, style = ROLE_EDGE.get(placement.role, ROLE_EDGE[cls.ROLE_NONE])
        ax.bar(
            placement.step, rect.y_max - rect.y_min, bottom=rect.y_min,
            width=0.72, color=colour, edgecolor=edge, linewidth=width,
            linestyle=style, alpha=0.5 if placement.surface == "shelf" else 0.9,
        )
        frontier = min(frontier, rect.y_min)
        ax.plot(
            [placement.step - 0.36, placement.step + 0.36], [frontier, frontier],
            color="#d62828", linewidth=1.4, zorder=5,
        )

    ax.axhline(model.y_back, color="#666666", linestyle=":", linewidth=1.0)
    ax.axhline(model.y_opening, color="#d93b3b", linestyle=":", linewidth=1.0)
    ax.text(0.5, model.y_back, " back wall", fontsize=6, color="#666666",
            va="bottom")
    ax.text(0.5, model.y_opening, " opening", fontsize=6, color="#d93b3b",
            va="bottom")
    ax.set_ylim(model.y_opening - 0.06, model.y_back + 0.06)
    ax.invert_yaxis()
    if ordered:
        ax.set_xlim(0.4, max(p.step for p in ordered) + 0.6)
    ax.tick_params(labelsize=7)
    ax.grid(axis="y", alpha=0.2)


def draw_diagnostic(ax, model: ContainerModel, placements, config):
    """Top-view overlay: plateaus, holes, zones, structural mask, corridor."""
    ax.set_title("top-view diagnostics", fontsize=10)
    grid = build_floor_grid(model, placements, config.grid_cell)
    plateaus = plateau_report(grid, config)
    holes = hole_report(grid, config)
    plateau_labels = plateaus.pop("_labels")
    holes.pop("_labels")

    extent = (
        grid.x0, grid.x0 + grid.nx * grid.cell,
        grid.y0, grid.y0 + grid.ny * grid.cell,
    )
    canvas = np.zeros((grid.nx, grid.ny, 4), dtype=float)

    # plateaus of the non-structural surface
    palette = plt.get_cmap("tab20")
    for label in range(1, int(plateau_labels.max()) + 1):
        mask = plateau_labels == label
        if not mask.any():
            continue
        colour = palette((label - 1) % 20)
        canvas[mask] = (*colour[:3], 0.85)

    # structural mask (wall front, elongated, slope structure)
    structural = grid.usable & grid.structural
    canvas[structural] = (0.75, 0.16, 0.16, 0.85)

    # holes
    free = grid.free_mask()
    from .layer1 import reachable_from_boundary

    reached = reachable_from_boundary(free, grid.usable)
    interior = free & ~reached
    canvas[reached] = (1.0, 1.0, 1.0, 0.9)
    canvas[interior] = (0.05, 0.05, 0.05, 0.9)
    canvas[~grid.usable] = (0.72, 0.72, 0.72, 0.9)

    ax.imshow(
        np.transpose(canvas, (1, 0, 2)),
        origin="lower", extent=extent, interpolation="nearest", zorder=1,
    )

    for name, (colour, label) in ZONE_STYLE.items():
        rect = getattr(model, name)
        ax.add_patch(
            patches.Rectangle(
                (rect.x_min, rect.y_min),
                rect.x_max - rect.x_min, rect.y_max - rect.y_min,
                fill=False, edgecolor=colour, linewidth=1.4, linestyle="--", zorder=3,
            )
        )
    ax.axvline(model.x_floor_min, color="#b52ea8", linewidth=1.4, linestyle="-.")

    for hole in holes["interior_holes"]:
        cx, cy = hole["centroid"]
        ax.text(cx, cy, f"H{hole['id']}\n{hole['area']:.2f}",
                ha="center", va="center", fontsize=6, color="white", zorder=5)

    ax.set_xlim(model.x_wall_min - 0.05, model.x_wall_max + 0.05)
    ax.set_ylim(model.y_opening - 0.05, model.y_back + 0.05)
    ax.set_aspect("equal")
    ax.set_xlabel("x  [m]")
    ax.set_ylabel("y  [m]")
    ax.tick_params(labelsize=7)
    return plateaus, holes


def _legend_handles():
    handles = [
        patches.Patch(facecolor=colour, edgecolor="#333333", label=name)
        for name, colour in CLASS_COLOR.items()
    ]
    handles += [
        Line2D([0], [0], color=colour, lw=lw, linestyle=style, label=f"role: {role}")
        for role, (colour, lw, style) in ROLE_EDGE.items()
        if role != cls.ROLE_NONE
    ]
    handles += [
        Line2D([0], [0], color=colour, lw=1.4, linestyle="--", label=label)
        for _key, (colour, label) in ZONE_STYLE.items()
    ]
    handles.append(
        Line2D([0], [0], color="#7d3cbd", lw=1.4, linestyle=":", label="shelf")
    )
    return handles


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------
def render_container(model: ContainerModel, placements, config, title: str,
                     path: pathlib.Path) -> dict:
    figure = plt.figure(figsize=(20.5, 9.6))
    grid_spec = figure.add_gridspec(2, 3, height_ratios=[1.15, 1.0], hspace=0.34,
                                    wspace=0.22, top=0.80)
    ax_top = figure.add_subplot(grid_spec[0, 0])
    ax_order = figure.add_subplot(grid_spec[0, 1])
    ax_diag = figure.add_subplot(grid_spec[0, 2])
    ax_open = figure.add_subplot(grid_spec[1, 0])
    ax_slope = figure.add_subplot(grid_spec[1, 1])
    ax_progress = figure.add_subplot(grid_spec[1, 2])

    draw_top(ax_top, model, placements)
    draw_order(ax_order, model, placements)
    plateaus, holes = draw_diagnostic(ax_diag, model, placements, config)
    draw_opening_view(ax_open, model, placements)
    draw_slope_view(ax_slope, model, placements)
    draw_fill_progression(ax_progress, model, placements)

    from .diagnostics import build_floor_grid, corridor_report, wall_front_report

    grid = build_floor_grid(model, placements, config.grid_cell)
    corridor = corridor_report(grid, model)
    wall = wall_front_report(model, placements, config)
    largest_hole = holes["largest_interior_hole"]
    caption = (
        f"floor coverage {grid.coverage():.2f}   |   "
        f"largest plateau {plateaus['largest_plateau_ratio']:.2f} of the floor "
        f"(built {plateaus['largest_built_plateau_ratio']:.2f}) over "
        f"{plateaus['plateau_count']} plateaus   |   "
        f"roughness {plateaus['local_roughness']:.3f} m   |   "
        f"height spread {plateaus['height_spread']:.2f} m\n"
        f"interior holes {holes['interior_hole_count']} "
        f"({holes['interior_hole_area']:.3f} m², largest "
        f"{largest_hole['area'] if largest_hole else 0.0:.3f} m²)   |   "
        f"remaining contiguous free floor {holes['largest_open_free_area']:.2f} m² "
        f"(best rectangle {holes['largest_open_free_rect']:.2f} m²)\n"
        f"wall_height / container_height {wall['wall_height_ratio']:.2f} "
        f"(target {config.wall_front_target_ratio})   |   "
        f"corridor free {corridor['corridor_free_ratio']:.2f}, "
        f"clear entry lanes {corridor['corridor_clear_lane_ratio']:.2f}"
    )
    figure.suptitle(title, fontsize=12)
    figure.text(0.5, 0.925, caption, ha="center", va="top", fontsize=7.5,
                color="#333333", linespacing=1.5)
    figure.legend(
        handles=_legend_handles(), loc="lower center", ncol=6, fontsize=7,
        frameon=False, bbox_to_anchor=(0.5, -0.01),
    )
    figure.savefig(path, dpi=110, bbox_inches="tight")
    # SVG alongside: the boards are worth zooming into, and a raster at this
    # size loses the clearances that decide whether a placement is legal
    figure.savefig(path.with_suffix(".svg"), bbox_inches="tight")
    plt.close(figure)
    return {"flatness": plateaus, "holes": holes}


def render_step(result, config, step_index: int, out_dir: pathlib.Path) -> list:
    """Render every container at the board state after ``step_index`` steps."""
    from .layer1 import Board

    board = Board(result.containers_raw, config)
    # the reserved strips were sized from the manifest at optimize time; a
    # freshly built board would draw the default full-width strips instead
    for idx, scale in (result.zone_scales or {}).items():
        if idx < len(board.models):
            board.models[idx].set_zone_scales(
                scale["soft_zone_scale"], scale["priority_zone_scale"]
            )
    for placement in result.sequence[:step_index]:
        board.apply(placement)

    written = []
    for idx, model in enumerate(board.models):
        name = f"c{model.index}_step{step_index:03d}.png"
        path = out_dir / name
        title = (
            f"{result.scenario}  |  container {model.index}"
            f"{'  [priority]' if model.is_prioritized else ''}"
            f"{'  [shelf]' if model.has_shelf else ''}"
            f"  |  after {step_index} placement(s)"
        )
        render_container(model, board.placements[idx], config, title, path)
        written.append(path)
    return written
