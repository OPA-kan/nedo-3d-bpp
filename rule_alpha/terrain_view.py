"""Pictures for the terrain report.

Four panels per container, all read-only:

* **opening elevation** — looking along +Y from the transport entry, which is
  the view the loader actually has.  Boxes are drawn in x-z with the pentagon
  cross section behind them, so the chamfer, the shelf and the wall front are
  all in one picture.
* **top view, order and role** — the same footprints numbered by placement
  step, coloured by role, with the reporting partition drawn over them.
* **height map** — the Layer 1 top surface as a field.
* **support type** — what that surface is *made of*, which is the part a
  Layer 2 stacker cares about: a hard top can be built on, a soft top cannot.
"""

from __future__ import annotations

import math
import pathlib

import matplotlib

matplotlib.use("Agg")

import matplotlib.patheffects as path_effects  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib import patches  # noqa: E402
from matplotlib.colors import BoundaryNorm, ListedColormap  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402

from . import classify as cls  # noqa: E402
from . import terrain as trn  # noqa: E402
from .diagnostics import (  # noqa: E402
    SUPPORT_FREE,
    SUPPORT_HARD,
    SUPPORT_PRIORITY,
    SUPPORT_SOFT,
    SUPPORT_SOFT_PRIORITY,
)
from .geometry import ContainerModel  # noqa: E402
from .visualize import CLASS_COLOR, ROLE_EDGE, _cross_section  # noqa: E402


SUPPORT_COLORS = {
    SUPPORT_FREE: "#f2f2f2",
    SUPPORT_HARD: "#3d6fb5",
    SUPPORT_SOFT: "#d98c3f",
    SUPPORT_PRIORITY: "#4fa363",
    SUPPORT_SOFT_PRIORITY: "#a45fb5",
}
SUPPORT_LABELS = {
    SUPPORT_FREE: "bare floor",
    SUPPORT_HARD: "hard top (buildable)",
    SUPPORT_SOFT: "soft top",
    SUPPORT_PRIORITY: "priority top",
    SUPPORT_SOFT_PRIORITY: "soft+priority top",
}


def _partition(ax, model: ContainerModel, config, vertical_axis: str = "y"):
    """Draw the 4 x 2 reporting partition over a top view."""
    e = trn.band_edges(model, config)
    for x in (e["x_chamfer"], e["x_left"], e["x_right"]):
        ax.axvline(x, color="#555555", linewidth=0.8, linestyle="--", alpha=0.7,
                   zorder=9)
    ax.axhline(e["y_mid"], color="#555555", linewidth=0.8, linestyle="--",
               alpha=0.7, zorder=9)
    labels = {
        "chamfer": 0.5 * (e["x0"] + e["x_chamfer"]),
        "left": 0.5 * (e["x_chamfer"] + e["x_left"]),
        "centre": 0.5 * (e["x_left"] + e["x_right"]),
        "right": 0.5 * (e["x_right"] + e["x1"]),
    }
    for name, x in labels.items():
        ax.text(x, e["y1"] + 0.03, name, ha="center", va="bottom", fontsize=6,
                color="#555555")


def draw_opening_elevation(ax, model: ContainerModel, placements, config):
    """Looking along +Y: what the loader sees standing at the opening."""
    ax.set_title("opening elevation  (looking in along +Y)", fontsize=10)
    ax.set_xlabel("x  [m]     chamfer -X  ->  +X")
    ax.set_ylabel("z  [m]")

    ax.add_patch(
        patches.Polygon(_cross_section(model), closed=True, fill=False,
                        edgecolor="#222222", linewidth=1.8, zorder=8)
    )
    for shelf in model.shelves:
        ax.add_patch(
            patches.Rectangle(
                (float(shelf.minimum[0]), float(shelf.minimum[2])),
                float(shelf.size[0]), float(shelf.size[2]),
                facecolor="#7d3cbd", edgecolor="#4b2273", alpha=0.65, zorder=7,
            )
        )

    # far items first so nearer ones draw on top, as in a real elevation
    for placement in sorted(placements, key=lambda p: -p.rect.y_min):
        rect = placement.rect
        edge, width, style = ROLE_EDGE.get(placement.role, ROLE_EDGE[cls.ROLE_NONE])
        depth = (rect.y_min - model.y_opening) / max(
            model.y_back - model.y_opening, 1e-9
        )
        ax.add_patch(
            patches.Rectangle(
                (rect.x_min, float(placement.box.minimum[2])),
                rect.x_max - rect.x_min,
                float(placement.box.size[2]),
                facecolor=CLASS_COLOR[placement.profile.cargo_class],
                edgecolor=edge, linewidth=width, linestyle=style,
                # further back = paler, so depth is readable in a flat view
                alpha=0.85 - 0.45 * depth,
                zorder=5 + int(10 * (1.0 - depth)),
            )
        )
        ax.text(
            0.5 * (rect.x_min + rect.x_max),
            float(placement.box.center[2]),
            f"{placement.step}",
            ha="center", va="center", fontsize=7, color="white",
            zorder=20,
            path_effects=[
                path_effects.withStroke(linewidth=2.0, foreground="#00000099")
            ],
        )

    ax.axhline(model.z_chamfer_top, color="#b52ea8", linestyle=":", linewidth=1.0)
    ax.text(model.x_wall_min + 0.02, model.z_chamfer_top + 0.01,
            "chamfer top", fontsize=6, color="#b52ea8")
    ax.set_xlim(model.x_wall_min - 0.05, model.x_wall_max + 0.05)
    ax.set_ylim(0.0, model.height + 0.05)
    ax.set_aspect("equal")
    ax.tick_params(labelsize=7)


def draw_role_order_top(ax, model: ContainerModel, placements, config):
    """Top view: role by fill colour, placement step as the label."""
    ax.set_title("top view — role + placement order", fontsize=10)
    ax.set_xlabel("x  [m]")
    ax.set_ylabel("y  [m]   opening -Y  ->  back +Y")

    ax.add_patch(
        patches.Rectangle(
            (model.x_wall_min, model.y_opening),
            model.x_floor_min - model.x_wall_min,
            model.y_back - model.y_opening,
            facecolor="#bbbbbb", edgecolor="none", alpha=0.5, zorder=0,
        )
    )
    ax.add_patch(
        patches.Rectangle(
            (model.x_wall_min, model.y_opening),
            model.x_wall_max - model.x_wall_min,
            model.y_back - model.y_opening,
            fill=False, edgecolor="#222222", linewidth=1.8, zorder=10,
        )
    )
    _partition(ax, model, config)

    for placement in sorted(placements, key=lambda p: p.step):
        rect = placement.rect
        edge, width, style = ROLE_EDGE.get(placement.role, ROLE_EDGE[cls.ROLE_NONE])
        on_shelf = placement.surface == "shelf"
        ax.add_patch(
            patches.Rectangle(
                (rect.x_min, rect.y_min),
                rect.x_max - rect.x_min, rect.y_max - rect.y_min,
                facecolor=CLASS_COLOR[placement.profile.cargo_class],
                edgecolor="#7d3cbd" if on_shelf else edge,
                linewidth=width, linestyle="dotted" if on_shelf else style,
                alpha=0.45 if on_shelf else 0.85,
                # shelf cargo sits above everything and would otherwise read as
                # a washed-out floor item in a flat top view
                hatch="///" if on_shelf else None,
                zorder=5 if not on_shelf else 6,
            )
        )
        ax.text(
            0.5 * (rect.x_min + rect.x_max), 0.5 * (rect.y_min + rect.y_max),
            f"{placement.step}\n{placement.top_z - model.z_floor:.2f}",
            ha="center", va="center", fontsize=6, color="white", zorder=8,
            path_effects=[
                path_effects.withStroke(linewidth=2.0, foreground="#00000099")
            ],
        )

    ax.set_xlim(model.x_wall_min - 0.05, model.x_wall_max + 0.05)
    ax.set_ylim(model.y_opening - 0.05, model.y_back + 0.10)
    ax.set_aspect("equal")
    ax.tick_params(labelsize=7)


def draw_height_map(ax, terrain, model: ContainerModel, config):
    ax.set_title("Layer 1 top surface — height above floor  [m]", fontsize=10)
    ax.set_xlabel("x  [m]")
    ax.set_ylabel("y  [m]")
    grid = terrain.grid
    field = np.where(grid.usable, grid.height - model.z_floor, np.nan)
    mesh = ax.pcolormesh(
        grid.xs, grid.ys, field.T, cmap="magma", shading="nearest",
        vmin=0.0, vmax=max(0.1, float(np.nanmax(field))),
    )
    plt.colorbar(mesh, ax=ax, fraction=0.046, pad=0.03).ax.tick_params(labelsize=6)
    _partition(ax, model, config)
    ax.set_xlim(model.x_wall_min - 0.05, model.x_wall_max + 0.05)
    ax.set_ylim(model.y_opening - 0.05, model.y_back + 0.10)
    ax.set_aspect("equal")
    ax.tick_params(labelsize=7)


def draw_support_map(ax, terrain, model: ContainerModel, config):
    ax.set_title("Layer 1 top surface — support type", fontsize=10)
    ax.set_xlabel("x  [m]")
    ax.set_ylabel("y  [m]")
    grid = terrain.grid
    codes = sorted(SUPPORT_COLORS)
    cmap = ListedColormap([SUPPORT_COLORS[c] for c in codes])
    norm = BoundaryNorm([c - 0.5 for c in codes] + [codes[-1] + 0.5], cmap.N)
    field = np.where(grid.usable, grid.support, np.nan).astype(float)
    ax.pcolormesh(grid.xs, grid.ys, field.T, cmap=cmap, norm=norm,
                  shading="nearest")
    _partition(ax, model, config)
    ax.legend(
        handles=[
            patches.Patch(facecolor=SUPPORT_COLORS[c], edgecolor="#888888",
                          label=SUPPORT_LABELS[c])
            for c in codes
        ],
        loc="upper left", fontsize=6, ncol=1, framealpha=0.85,
        borderpad=0.4, labelspacing=0.3,
    )
    ax.set_xlim(model.x_wall_min - 0.05, model.x_wall_max + 0.05)
    ax.set_ylim(model.y_opening - 0.05, model.y_back + 0.10)
    ax.set_aspect("equal")
    ax.tick_params(labelsize=7)


# ---------------------------------------------------------------------------
# Isometric stack view
# ---------------------------------------------------------------------------
_ISO_U = 1.0 / math.sqrt(2.0)
_ISO_V = 1.0 / math.sqrt(6.0)


def _iso(x: float, y: float, z: float) -> tuple[float, float]:
    """True isometric projection for a viewer at ``(+x, -y, +z)``.

    Derived rather than guessed: with the view direction ``d = (1, -1, 1)``,
    screen-up is ``z`` with ``d`` projected out and screen-right is ``s x d``,
    which gives these two rows.  The three faces that can be seen are therefore
    the ``+x`` side, the ``-y`` side -- the one facing the loading opening --
    and the top; the back of the container falls up-and-left, further away, as
    it should.  Painting far-to-near gives exact occlusion for axis-aligned
    boxes that do not overlap, which is what a settled board is.
    """
    return ((x + y) * _ISO_U, (-x + y + 2.0 * z) * _ISO_V)


def _shade(colour: str, factor: float) -> tuple:
    rgb = matplotlib.colors.to_rgb(colour)
    return tuple(min(1.0, max(0.0, c * factor)) for c in rgb)


def _iso_box(ax, box, colour, edge, linewidth, style, alpha=1.0, label=None):
    """Three visible faces, each shaded so the solid reads as a solid."""
    x0, y0, z0 = (float(v) for v in box.minimum)
    x1, y1, z1 = (float(v) for v in box.maximum)
    faces = (
        # top, brightest
        ([(x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)], 1.0),
        # the face towards the opening
        ([(x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1)], 0.78),
        # the +x face
        ([(x1, y0, z0), (x1, y1, z0), (x1, y1, z1), (x1, y0, z1)], 0.58),
    )
    for corners, factor in faces:
        ax.add_patch(
            patches.Polygon(
                [_iso(*c) for c in corners], closed=True,
                facecolor=_shade(colour, factor), edgecolor=edge,
                linewidth=linewidth, linestyle=style, alpha=alpha, zorder=5,
            )
        )
    if label is not None:
        u, v = _iso(0.5 * (x0 + x1), y0, 0.5 * (z0 + z1))
        ax.text(u, v, label, ha="center", va="center", fontsize=7,
                color="white", zorder=9,
                path_effects=[
                    path_effects.withStroke(linewidth=2.0, foreground="#000000aa")
                ])


def _iso_depth(box) -> float:
    """Distance from the viewer at ``(+x, -y, +z)``; smaller is further away."""
    return (
        float(box.minimum[0]) - float(box.maximum[1]) + float(box.minimum[2])
    )


def draw_iso_stack(ax, model: ContainerModel, placements, config,
                   numbered: bool = True):
    ax.set_title("how it is stacked  (isometric, viewed from the opening)",
                 fontsize=10)
    ax.set_axis_off()

    # container: the floor pentagon extruded, drawn as a wireframe so nothing
    # is hidden behind it
    section = _cross_section(model)
    for y, width in ((model.y_opening, 1.6), (model.y_back, 0.9)):
        ax.add_patch(
            patches.Polygon(
                [_iso(px, y, pz) for px, pz in section], closed=True,
                fill=False, edgecolor="#333333", linewidth=width, zorder=1,
            )
        )
    for px, pz in section:
        a, b = _iso(px, model.y_opening, pz), _iso(px, model.y_back, pz)
        ax.plot([a[0], b[0]], [a[1], b[1]], color="#333333", linewidth=0.8,
                alpha=0.6, zorder=1)

    for shelf in model.shelves:
        _iso_box(ax, shelf, "#7d3cbd", "#4b2273", 0.8, "solid", alpha=0.45)

    for placement in sorted(placements, key=lambda p: _iso_depth(p.box)):
        edge, width, style = ROLE_EDGE.get(placement.role, ROLE_EDGE[cls.ROLE_NONE])
        _iso_box(
            ax, placement.box,
            CLASS_COLOR[placement.profile.cargo_class],
            edge, width, style,
            label=str(placement.step) if numbered else None,
        )

    corners = [
        _iso(x, y, z)
        for x in (model.x_wall_min, model.x_wall_max)
        for y in (model.y_opening, model.y_back)
        for z in (0.0, model.height)
    ]
    us = [c[0] for c in corners]
    vs = [c[1] for c in corners]
    ax.set_xlim(min(us) - 0.1, max(us) + 0.1)
    ax.set_ylim(min(vs) - 0.1, max(vs) + 0.1)
    ax.set_aspect("equal")


def draw_side_elevation(ax, model: ContainerModel, placements, config):
    """Looking along +X: depth against height — the terrace question itself.

    ``H_back >= H_mid >= H_front`` is not a matter of taste: the validator
    sweeps straight in, so a profile that rises towards the opening seals
    everything behind it.  This is the view that shows whether it does.
    """
    ax.set_title("side elevation  (depth profile — is the back higher?)",
                 fontsize=10)
    ax.set_xlabel("y  [m]     opening -Y  ->  back +Y")
    ax.set_ylabel("z  [m]")

    ax.add_patch(
        patches.Rectangle(
            (model.y_opening, model.z_floor),
            model.y_back - model.y_opening,
            model.z_ceiling - model.z_floor,
            fill=False, edgecolor="#222222", linewidth=1.8, zorder=8,
        )
    )
    for shelf in model.shelves:
        ax.add_patch(
            patches.Rectangle(
                (float(shelf.minimum[1]), float(shelf.minimum[2])),
                float(shelf.size[1]), float(shelf.size[2]),
                facecolor="#7d3cbd", edgecolor="#4b2273", alpha=0.6, zorder=7,
            )
        )

    span = max(model.x_wall_max - model.x_wall_min, 1e-9)
    for placement in sorted(placements, key=lambda p: p.rect.x_min):
        rect = placement.rect
        edge, width, style = ROLE_EDGE.get(placement.role, ROLE_EDGE[cls.ROLE_NONE])
        across = (rect.x_min - model.x_wall_min) / span
        ax.add_patch(
            patches.Rectangle(
                (rect.y_min, float(placement.box.minimum[2])),
                rect.y_max - rect.y_min, float(placement.box.size[2]),
                facecolor=CLASS_COLOR[placement.profile.cargo_class],
                edgecolor=edge, linewidth=width, linestyle=style,
                # further across = paler, so the overlap is readable
                alpha=0.85 - 0.5 * across,
                zorder=5 + int(10 * (1.0 - across)),
            )
        )

    # the floor terrain seen from the side: the highest thing at each depth
    grid = trn.build_terrain(model, placements, config).grid
    profile = np.where(grid.usable, grid.height, np.nan)
    with np.errstate(invalid="ignore"):
        skyline = np.nanmax(profile, axis=0)
    ax.step(grid.ys, skyline, where="mid", color="#d62828", linewidth=1.6,
            zorder=12, label="floor skyline")
    ax.legend(loc="upper left", fontsize=6, frameon=False)

    ax.set_xlim(model.y_opening - 0.05, model.y_back + 0.05)
    ax.set_ylim(0.0, model.height + 0.05)
    ax.set_aspect("equal")
    ax.tick_params(labelsize=7)


def render_stack(model: ContainerModel, placements, config, title: str,
                 path: pathlib.Path) -> list:
    """The stack on its own, square, because it is the picture people read."""
    figure, ax = plt.subplots(figsize=(11.0, 10.0))
    figure.suptitle(title, fontsize=12)
    draw_iso_stack(ax, model, placements, config)
    ax.set_title("")  # the figure title already says it
    figure.legend(
        handles=_stack_legend(), loc="lower center", ncol=6, fontsize=7,
        frameon=False,
    )
    figure.tight_layout(rect=(0, 0.06, 1, 0.96))
    path.parent.mkdir(parents=True, exist_ok=True)
    written = []
    for suffix in (".png", ".svg"):
        target = path.with_suffix(suffix)
        figure.savefig(target, dpi=140)
        written.append(target)
    plt.close(figure)
    return written


def _stack_legend():
    return (
        [patches.Patch(facecolor=colour, edgecolor="#333333", label=name)
         for name, colour in CLASS_COLOR.items()]
        + [Line2D([0], [0], color=colour, lw=lw, linestyle=style,
                  label=f"role: {role}")
           for role, (colour, lw, style) in ROLE_EDGE.items()
           if role != cls.ROLE_NONE]
        + [Line2D([0], [0], color="#7d3cbd", lw=1.4, linestyle="-",
                  label="shelf")]
    )


def render_terrain(model: ContainerModel, placements, config, title: str,
                   path: pathlib.Path) -> list:
    terrain = trn.build_terrain(model, placements, config)
    figure, axes = plt.subplots(3, 2, figsize=(15.0, 19.5))
    figure.suptitle(title, fontsize=12)

    draw_opening_elevation(axes[0][0], model, placements, config)
    draw_side_elevation(axes[0][1], model, placements, config)
    draw_role_order_top(axes[1][0], model, placements, config)
    draw_height_map(axes[1][1], terrain, model, config)
    draw_support_map(axes[2][0], terrain, model, config)
    axes[2][1].set_axis_off()

    figure.legend(
        handles=(
            [patches.Patch(facecolor=colour, edgecolor="#333333", label=name)
             for name, colour in CLASS_COLOR.items()]
            + [Line2D([0], [0], color=colour, lw=lw, linestyle=style,
                      label=f"role: {role}")
               for role, (colour, lw, style) in ROLE_EDGE.items()
               if role != cls.ROLE_NONE]
            + [Line2D([0], [0], color="#7d3cbd", lw=1.4, linestyle=":",
                      label="shelf")]
        ),
        loc="lower center", ncol=6, fontsize=7, frameon=False,
    )
    figure.tight_layout(rect=(0, 0.035, 1, 0.975), h_pad=3.0)

    path.parent.mkdir(parents=True, exist_ok=True)
    written = []
    for suffix in (".png", ".svg"):
        target = path.with_suffix(suffix)
        figure.savefig(target, dpi=130)
        written.append(target)
    plt.close(figure)
    return written
