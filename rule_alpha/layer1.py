"""The rule-alpha Layer 1 builder.

Design notes
------------
* One placement is chosen by a *ladder of candidate archetypes*, not by one
  weighted score.  Each archetype keeps its own best candidate; the item's class
  and role decide which archetype gets asked first.  A small tie-break score
  only ever separates candidates that a single archetype ranked equal.
* Layer 1 means: supports are the floor and the shelves.  The single exception
  is a slope-infill candidate, which may rest on a hard item because the slope
  pocket is unreachable from the floor (see README).
* Every veto is recorded, so a board that looks wrong can be traced back to the
  rule that produced it.
"""

from __future__ import annotations

import math

from dataclasses import dataclass, field

import numpy as np

from . import classify as cls
from . import layer2 as l2
from . import stability
from . import triangle as tri
from ._reuse import (
    AABB,
    packed_dimensions,
    packed_aabbs_local,
    shelf_aabbs,
    simulator_action_center,
    transport_samples,
    within_euclidean_clearance,
    penetrates_with_lateral_clearance,
)
from .diagnostics import FloorGrid, support_code
from .geometry import ContainerModel, Rect, box_rect, union_area


# --- candidate archetypes ----------------------------------------------------
A_MAX_FOOTPRINT = "max-footprint"
A_BACK_CORNER = "back-corner"
A_MIN_HOLE = "minimum-hole"
A_LARGEST_RESIDUAL = "largest-residual-rectangle"
A_SHELF_SAVING = "shelf-space-saving"
A_SOFT_EDGE = "soft-edge"
A_PRIORITY_EDGE = "priority-edge"
A_SP_CLUSTER = "sp-cluster"
A_ELONGATED_WALL = "elongated-wall"
A_SLOPE_INFILL = "slope-infill"
A_WALL_FRONT = "wall-front"
A_TALL_PERIMETER = "tall-perimeter"
A_WEDGE_STEP = "wedge-step"
A_WEDGE_CAP = "wedge-soft-cap"
A_TERRACE = "terrace-extension"
A_BRIDGE = "plateau-merge"
A_WEDGE_BRIDGE = "wedge-bridge"
A_HOLE_FILL = "hole-fill"
A_TYPED_CAP = "typed-cap"
A_LAST_RESORT = "last-resort"
A_FRONT_WEDGE = "front-wedge"

ALL_ARCHETYPES = (
    A_MAX_FOOTPRINT,
    A_BACK_CORNER,
    A_MIN_HOLE,
    A_LARGEST_RESIDUAL,
    A_SHELF_SAVING,
    A_SOFT_EDGE,
    A_PRIORITY_EDGE,
    A_SP_CLUSTER,
    A_ELONGATED_WALL,
    A_SLOPE_INFILL,
    A_WALL_FRONT,
    A_TALL_PERIMETER,
    A_WEDGE_STEP,
    A_WEDGE_CAP,
    A_TERRACE,
    A_BRIDGE,
    A_WEDGE_BRIDGE,
    A_HOLE_FILL,
    A_TYPED_CAP,
    A_LAST_RESORT,
    A_FRONT_WEDGE,
)


# ---------------------------------------------------------------------------
# Fast free-space helpers
# ---------------------------------------------------------------------------
def _dilate(mask: np.ndarray) -> np.ndarray:
    out = mask.copy()
    out[1:, :] |= mask[:-1, :]
    out[:-1, :] |= mask[1:, :]
    out[:, 1:] |= mask[:, :-1]
    out[:, :-1] |= mask[:, 1:]
    return out


def reachable_from_boundary(free: np.ndarray, usable: np.ndarray) -> np.ndarray:
    """Free cells connected to the outside of the usable region.

    Morphological reconstruction: seed with free cells that touch either the
    array border or a non-usable cell, then grow inside ``free``.
    """
    if not free.any():
        return np.zeros_like(free)
    border = np.zeros_like(free)
    border[0, :] = border[-1, :] = True
    border[:, 0] = border[:, -1] = True
    seed = free & (border | _dilate(~usable))
    reached = seed.copy()
    while True:
        grown = _dilate(reached) & free
        if grown.sum() == reached.sum():
            return grown
        reached = grown


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------
@dataclass
class Placement:
    profile: cls.ItemProfile
    orientation: cls.Orientation
    container_idx: int
    box: AABB
    surface: str            # "floor" | "shelf" | "item"
    surface_name: str
    role: str
    archetype: str
    reason: str
    features: dict = field(default_factory=dict)
    transport_ok: bool = True
    settle_ok: bool = True
    settle_note: str = "analytic"
    container_is_prioritized: bool = False
    container_has_shelf: bool = False
    layer: int = 1
    step: int = 0

    @property
    def rect(self) -> Rect:
        return box_rect(self.box)

    @property
    def top_z(self) -> float:
        return float(self.box.maximum[2])

    @property
    def volume(self) -> float:
        return float(np.prod(self.box.size))

    @property
    def is_structural(self) -> bool:
        return self.role in (
            cls.ROLE_WALL_FRONT,
            cls.ROLE_ELONGATED,
            cls.ROLE_SLOPE_INFILL,
            cls.ROLE_TALL_PERIMETER,
            cls.ROLE_WEDGE_STEP,
        )

    @property
    def role_is_wall_front(self) -> bool:
        return self.role == cls.ROLE_WALL_FRONT

    def as_dict(self, config=None) -> dict:
        return {
            "item_index": self.profile.index,
            "is_soft": self.profile.is_soft,
            "is_prioritized": self.profile.is_prioritized,
            "class": self.profile.cargo_class,
            "role": self.role,
            "elongation_rho": round(self.profile.elongation, 3),
            "step": self.step,
            "container_idx": self.container_idx,
            "container_is_prioritized": self.container_is_prioritized,
            "container_has_shelf": self.container_has_shelf,
            "surface": self.surface,
            "surface_name": self.surface_name,
            "orientation": self.orientation.index,
            "dx": round(self.orientation.dx, 4),
            "dy": round(self.orientation.dy, 4),
            "dz": round(self.orientation.dz, 4),
            "footprint": round(self.orientation.footprint, 4),
            "tipping_ratio": round(self.orientation.tipping_ratio, 3),
            "tipping_band": (
                self.orientation.tipping_band(config) if config is not None else None
            ),
            "pos_local": [round(float(v), 4) for v in self.box.center],
            "archetype": self.archetype,
            "reason": self.reason,
            "support_type_created": support_code(
                self.profile.is_soft, self.profile.is_prioritized
            ),
            "transport_ok": self.transport_ok,
            "settle_ok": self.settle_ok,
            "settle_note": self.settle_note,
        }


@dataclass
class Candidate:
    box: AABB
    profile: cls.ItemProfile
    orientation: cls.Orientation
    container_idx: int
    surface: str
    surface_name: str
    role: str
    family: str = "floor"
    features: dict = field(default_factory=dict)
    archetypes: set = field(default_factory=set)
    vetoes: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# Board state
# ---------------------------------------------------------------------------
class Board:
    """Mutable Layer 1 state for every container in the episode."""

    def __init__(self, containers: list[dict], config):
        self.config = config
        self.containers = [dict(c) for c in containers]
        for container in self.containers:
            container["packed_items"] = list(container.get("packed_items", []))
        self.models = [ContainerModel(c, config) for c in self.containers]
        self.placements: list[list[Placement]] = [[] for _ in self.containers]
        self._grids: list[FloorGrid | None] = [None for _ in self.containers]
        self.triangle_demand: list = [
            tri.WedgeDemand(source="no-manifest") for _ in self.containers
        ]
        self._triangle: list = [None for _ in self.containers]
        self._reach: list = [None for _ in self.containers]
        self._plateau: list = [None for _ in self.containers]
        self._plateau_labels: list = [None for _ in self.containers]
        self._back_height: list = [None for _ in self.containers]
        self._holes: list = [None for _ in self.containers]
        # manifest-derived: what the outstanding frontier cargo still needs.
        # The manifest is handed to optimize(), so reading it is information the
        # policy legitimately has -- not a peek at future arrivals.
        self.foundation_pending: dict[int, tuple[float, float]] = {}
        self.large_threshold: float = float("inf")
        self.small_threshold: float = 0.0
        self.min_useful_width: float = config.row_min_useful_width

    # -- accessors -------------------------------------------------------
    def model(self, idx: int) -> ContainerModel:
        return self.models[idx]

    def container(self, idx: int) -> dict:
        return self.containers[idx]

    def grid(self, idx: int) -> FloorGrid:
        grid = self._grids[idx]
        if grid is None:
            from .diagnostics import build_floor_grid, grid_from_packed

            if self.placements[idx] or not self.containers[idx].get("packed_items"):
                grid = build_floor_grid(
                    self.models[idx], self.placements[idx],
                    self.config.candidate_grid_cell,
                )
            else:
                # Driving the real environment the board is rebuilt from each
                # observation, which carries packed_items and no placements.
                # Building the height map from placements then gave an empty
                # grid every turn, and everything that reads it -- coverage,
                # reachability, holes, plateaus, the wedge state -- answered as
                # if the container were empty.
                grid = grid_from_packed(
                    self.models[idx], self.containers[idx],
                    self.config.candidate_grid_cell,
                )
            self._grids[idx] = grid
        return grid

    def has_priority_container(self) -> bool:
        return any(m.is_prioritized for m in self.models)

    def set_triangle_demand(self, profiles, config) -> dict:
        """Price the triangle reservation from the declared stream."""
        out = {}
        for idx, model in enumerate(self.models):
            demand = tri.measure_demand(profiles, model, config)
            self.triangle_demand[idx] = demand
            out[idx] = demand.as_dict()
        self._triangle = [None for _ in self.containers]
        return out

    def triangle_state(self, idx: int):
        state = self._triangle[idx]
        if state is None:
            from .diagnostics import corridor_report, lane_bottleneck

            grid = self.grid(idx)
            model = self.models[idx]
            if self.config.wedge_bottleneck_is_local:
                # Charge the reservation for congestion in the lane it actually
                # uses.  It was charged for the *central* corridor, which the
                # wedge strip does not go through: on the first board the strip
                # was empty, 0.16 m of reach was still on offer, and the zone
                # closed anyway because the middle of the floor had filled up.
                bottleneck = lane_bottleneck(grid, model, model.wall_front_strip)
            else:
                corridor = corridor_report(grid, model)
                bottleneck = 1.0 - float(corridor["corridor_clear_lane_ratio"])
            state = tri.evaluate(
                model,
                self.placements[idx],
                self.triangle_demand[idx],
                grid.coverage(),
                bottleneck,
                self.config,
            )
            self._triangle[idx] = state
        return state

    def set_zone_demand(self, profiles, config) -> dict:
        """Size the reserved edge strips from the declared manifest.

        The environment gives ``optimize()`` the whole item list, so this reads
        a list it was handed — it is not a guess about unseen cargo.  A strip
        reaches full width once its class holds ``zone_reference_share`` of the
        stream by footprint, and vanishes when the class is absent.
        """
        total = sum(p.max_footprint for p in profiles) or 1.0
        soft_area = sum(
            p.max_footprint for p in profiles if p.cargo_class == cls.SOFT
        )
        priority_area = sum(
            p.max_footprint for p in profiles
            if p.cargo_class == cls.PRIORITY
        )
        sp_area = sum(
            p.max_footprint for p in profiles if p.cargo_class == cls.SOFT_PRIORITY
        )
        reference = max(1e-6, config.zone_reference_share)
        has_priority_uld = self.has_priority_container()

        scales = {}
        for idx, model in enumerate(self.models):
            if model.is_prioritized:
                # soft-only never comes here; the strip is for SP clustering
                soft_scale = 0.0
                priority_scale = min(1.0, (sp_area / total) / reference)
            else:
                shelf_relief = 0.0
                if model.main_shelf is not None:
                    shelf_relief = float(
                        model.main_shelf.size[0] * model.main_shelf.size[1]
                    )
                soft_floor_area = max(0.0, soft_area - shelf_relief)
                soft_scale = min(1.0, (soft_floor_area / total) / reference)
                routed = 0.0 if has_priority_uld else (priority_area + sp_area)
                priority_scale = min(1.0, (routed / total) / reference)
            model.set_zone_scales(soft_scale, priority_scale)
            scales[idx] = {
                "soft_zone_scale": round(soft_scale, 3),
                "priority_zone_scale": round(priority_scale, 3),
            }
        self._grids = [None for _ in self.containers]
        return scales

    # -- mutation --------------------------------------------------------
    def apply(self, placement: Placement) -> None:
        idx = placement.container_idx
        item = placement.profile.item
        centre = placement.box.center
        model = self.models[idx]
        offset_x = float(self.containers[idx].get("center", (0.0, 0.0, 0.0))[0])
        self.containers[idx]["packed_items"].append(
            {
                "index": placement.profile.index,
                "length": float(item["length"]),
                "width": float(item["width"]),
                "height": float(item["height"]),
                "mass": placement.profile.mass,
                "is_prioritized": placement.profile.is_prioritized,
                "is_soft": placement.profile.is_soft,
                "orientation": placement.orientation.index,
                "dims": tuple(float(v) for v in placement.box.size),
                "pos": (
                    float(centre[0]) + offset_x,
                    float(centre[1]),
                    float(centre[2]),
                ),
                "belongs_to": model.index,
                "layer": int(placement.layer),
            }
        )
        self.placements[idx].append(placement)
        self._grids[idx] = None
        self._triangle[idx] = None
        self._reach = [None for _ in self.containers]
        self._plateau = [None for _ in self.containers]
        self._plateau_labels = [None for _ in self.containers]
        self._back_height = [None for _ in self.containers]
        self._holes = [None for _ in self.containers]
        self.foundation_pending.pop(placement.profile.index, None)


    # -- reachability and frontier demand --------------------------------
    def plateau_stats(self, idx: int) -> dict:
        """Connected hard plateau statistics, cached per board state."""
        cached = self._plateau[idx]
        if cached is None:
            cached = l2.hard_plateau_stats(
                self.grid(idx), self.models[idx].z_floor,
                self.config.plateau_height_tolerance,
            )
            self._plateau[idx] = cached
        return cached

    def holes(self, idx: int) -> list:
        """Pockets one layer could not close, cached per board state."""
        cached = self._holes[idx]
        if cached is None:
            cached = l2.surface_holes(
                self.grid(idx), self.models[idx], self.config
            )
            self._holes[idx] = cached
        return cached

    def plateau_labels(self, idx: int):
        """``(labels, count)`` of the hard top surface, cached per board state."""
        cached = self._plateau_labels[idx]
        if cached is None:
            cached = l2.plateau_map(
                self.grid(idx), self.models[idx].z_floor,
                self.config.plateau_height_tolerance,
            )
            self._plateau_labels[idx] = cached
        return cached

    def back_height(self, idx: int) -> float:
        """How high the back band stands, as a share-robust quantile.

        A single tall box at the back is not "the back has been built up", so
        this asks how high ``front_release_back_share`` of the band has got
        rather than how high its tallest point is.
        """
        cached = self._back_height[idx]
        if cached is None:
            grid = self.grid(idx)
            model = self.models[idx]
            band = grid.rect_mask(model.back_band) & grid.usable
            if not band.any():
                cached = 0.0
            else:
                heights = grid.height[band] - model.z_floor
                cached = float(
                    np.quantile(heights, 1.0 - self.config.front_release_back_share)
                )
            self._back_height[idx] = cached
        return cached

    def back_headroom(self, idx: int) -> float:
        """How tall the back band is allowed to get in the first place.

        Where there is a shelf it caps the back at its underside, and the back
        band is entirely under it, so the height available there is 0.76 m
        against the container's 1.53.  A release threshold stated as an
        absolute height therefore means something completely different with a
        shelf and without one.
        """
        model = self.models[idx]
        grid = self.grid(idx)
        band = grid.rect_mask(model.back_band) & grid.usable
        if not band.any():
            return max(1e-6, model.z_ceiling - model.z_floor)
        # Per cell, because a shelf need not cover the band.  Reading
        # "there is a shelf, so the ceiling is its underside" put task 000's
        # back band at 0.765 m when only the 0.44 m chamfer shelf overhangs a
        # 1.47 m wide floor -- which dropped the release threshold to 0.344 and
        # opened the front while the back was still at 0.48.
        ceilings = np.full(grid.height.shape, model.z_ceiling, dtype=np.float64)
        for shelf in model.shelves:
            under = grid.rect_mask(
                Rect(float(shelf.minimum[0]), float(shelf.maximum[0]),
                     float(shelf.minimum[1]), float(shelf.maximum[1]))
            )
            ceilings[under] = np.minimum(
                ceilings[under], float(shelf.minimum[2])
            )
        available = ceilings[band] - model.z_floor
        return max(
            1e-6,
            float(np.quantile(available, 1.0 - self.config.front_release_back_share)),
        )

    def front_is_released(self, idx: int) -> bool:
        """Has the back been built high enough to spend the front?

        The front is the way in and the landing pad for typed overflow, so
        Layer 1 keeps it low while the back is still the cheaper place to
        build.  Once the back stands this high, keeping the front flat costs
        more than it saves: there is nowhere else left that does not require
        reaching over something.

        Measured as a share of the headroom the back band actually has, not as
        an absolute height.  The absolute form was calibrated while the height
        map was wrongly counting shelf-borne cargo as floor terrain, which read
        the back as 1.43 m in a container whose back band cannot exceed 0.76.
        """
        share = self.config.front_release_back_share_of_headroom
        if share <= 0.0:
            return False
        return self.back_height(idx) >= share * self.back_headroom(idx)

    def floor_reach(self, idx: int) -> tuple[float, float]:
        """``(reachable, sealed)`` bare floor area, cached per board state."""
        return self.reach_at_height(idx, 0.0)

    def reach_at_height(self, idx: int, z_rel: float) -> tuple[float, float]:
        """``(reachable, sealed)`` usable area at a working height.

        Cached per board state and rounded height, because the same few working
        heights recur across a step's candidates.
        """
        cache = self._reach[idx]
        if cache is None:
            cache = {}
            self._reach[idx] = cache
        key = round(float(z_rel), 3)
        if key not in cache:
            cache[key] = reach_at(self.grid(idx), self.models[idx].z_floor, key)
        return cache[key]

    def set_foundation_demand(self, profiles, config) -> dict:
        """Split the hard manifest into frontier material and followers.

        Measured as quantiles of *this* manifest rather than an absolute area:
        a stream of uniformly small boxes still has a largest box, and that box
        is still the one that should set the frontier.
        """
        hard = [
            p for p in profiles
            if p.cargo_class == cls.NORMAL_HARD and not p.is_elongated
        ]
        self.foundation_pending = {}
        if not hard:
            self.large_threshold = float("inf")
            self.small_threshold = 0.0
            return {"large_threshold": None, "small_threshold": None, "pending": 0}

        widths = [
            min(o.dx for o in p.orientations)
            for p in hard if p.orientations
        ]
        self.min_useful_width = min(widths) if widths else config.row_min_useful_width

        footprints = sorted(p.max_footprint for p in hard)
        self.large_threshold = float(
            np.quantile(footprints, config.foundation_large_quantile)
        )
        self.small_threshold = float(
            np.quantile(footprints, config.foundation_small_quantile)
        )
        for profile in hard:
            if profile.max_footprint >= self.large_threshold - 1e-12:
                self.foundation_pending[profile.index] = _flattest_floor_rect(profile)
        return {
            "large_threshold": round(self.large_threshold, 4),
            "small_threshold": round(self.small_threshold, 4),
            "pending": len(self.foundation_pending),
        }

    def is_frontier_material(self, profile) -> bool:
        return (
            profile.cargo_class == cls.NORMAL_HARD
            and not profile.is_elongated
            and profile.max_footprint >= self.large_threshold - 1e-12
        )

    def is_follower(self, profile) -> bool:
        return (
            profile.cargo_class == cls.NORMAL_HARD
            and not profile.is_elongated
            and profile.max_footprint <= self.small_threshold + 1e-12
        )

    def foundation_still_fits(self, idx: int, dims, placing) -> bool:
        """Would the largest outstanding frontier item still fit afterwards?

        ``dims`` is the largest free rectangle left by the candidate.  This is
        a proxy -- an item can fit somewhere that is not the single maximal
        rectangle -- but it is the cheap, monotone question, and it is the one
        that catches a small box laid across the middle of the only bay a big
        one had left.
        """
        pending = [
            rect for index, rect in self.foundation_pending.items()
            if index != placing.index
        ]
        if not pending:
            return True
        want = max(pending, key=lambda r: r[0] * r[1])
        return _rect_fits(want, dims)


def _flattest_floor_rect(profile) -> tuple[float, float]:
    """The footprint an item takes when laid down as flat as it can be."""
    best = min(profile.orientations, key=lambda o: (round(o.dz, 6), -o.footprint))
    return (float(best.dx), float(best.dy))


def _rect_fits(want: tuple[float, float], have: tuple[float, float]) -> bool:
    w, h = want
    a, b = have
    return (w <= a + 1e-9 and h <= b + 1e-9) or (h <= a + 1e-9 and w <= b + 1e-9)


# ---------------------------------------------------------------------------
# Validity
# ---------------------------------------------------------------------------
def _supports(model: ContainerModel, container: dict, config, allow_item_tops: bool):
    """Candidate support surfaces for a Layer 1 placement."""
    surfaces = [(model.floor_surface(), "floor", "floor")]
    for shelf in shelf_aabbs(container):
        surfaces.append((shelf, "shelf", shelf.name))
    if allow_item_tops:
        for box, is_soft, is_prio in packed_aabbs_local(container):
            if is_soft or is_prio:
                continue
            surfaces.append((box, "item", "packed_item"))
    return surfaces


def action_center(box: AABB, model: ContainerModel, container: dict, config):
    """The pose rule-alpha *commands*, as opposed to the settled pose it draws.

    ``simulator_action_center`` is the single source of truth for the release
    height, and the transport sweep is derived from it, so rule-alpha must not
    add a lift the sweep does not know about.  It only fills the gap when the
    shared helper applied no lift at all — which is what an older
    ``agent/agent.py`` without a floor lift would do.  Adding one on top of an
    existing lift moved the commanded pose 4 cm up while the sweep was still
    modelled at 2 cm, and put tall wall-front items inside the small shelf's
    safety margin.
    """
    centre = np.asarray(simulator_action_center(box, container), dtype=np.float64)
    already_lifted = abs(float(centre[2]) - float(box.center[2])) > 1e-9
    if already_lifted:
        return centre
    if abs(float(box.minimum[2]) - model.z_floor) <= config.contact_tolerance:
        centre[2] += config.floor_action_lift
    return centre


def validate(box: AABB, model: ContainerModel, container: dict, config) -> tuple[bool, str]:
    """Analytic mirror of the official validator's accept path.

    ``box`` is the *settled* pose.  Three poses have to be legal: the settled
    pose (what the evaluator finally measures), the commanded pose (what
    ``check_inclusion`` sees) and the transported pose (what the sweep sees).
    """
    if not model.inside(box, config.settled_wall_clearance, floor_clearance=0.0):
        return False, "settled-pose-outside"

    commanded = AABB(
        center=tuple(action_center(box, model, container, config)),
        size=box.size,
        name="action",
    )
    if not model.inside(commanded, config.inclusion_clearance):
        return False, "outside-container"

    samples = transport_samples(box, container)
    if samples:
        transport_z = float(samples[0].center[2])
        transported = AABB(
            center=(float(box.center[0]), float(box.center[1]), transport_z),
            size=box.size,
            name="transported",
        )
        if not model.inside(transported, config.settled_wall_clearance,
                            floor_clearance=0.0):
            return False, "transport-pose-outside"

    for shelf in shelf_aabbs(container):
        if penetrates_with_lateral_clearance(box, shelf, config.settled_clearance):
            return False, f"overlaps-{shelf.name}"
    for packed, _soft, _prio in packed_aabbs_local(container):
        if penetrates_with_lateral_clearance(box, packed, config.settled_clearance):
            return False, "overlaps-packed-item"

    # Stability, not bureaucracy.  The competition has no support-ratio rule;
    # ``place_item`` just drops the box and checks it did not move.  A rigid
    # body topples exactly when its centre of mass leaves the convex hull of
    # its contact patches, and that criterion reproduces both measured shapes:
    # a cantilever going marginal at o = w/2, and a bridge holding on two small
    # contacts.  The old largest-single-patch ratio got the first right by
    # accident and made the second impossible.
    stable, margin = stability.is_stable(box, container, config)
    if not stable:
        return False, (
            "no-support" if margin == -float("inf") else "centre-of-mass-outside-support"
        )

    for sample in samples:
        for obstacle in shelf_aabbs(container):
            if within_euclidean_clearance(sample, obstacle, config.settled_clearance):
                return False, f"transport-hits-{obstacle.name}"
        for obstacle, _soft, _prio in packed_aabbs_local(container):
            if within_euclidean_clearance(sample, obstacle, config.settled_clearance):
                return False, "transport-hits-packed-item"
    return True, "ok"


# ---------------------------------------------------------------------------
# Candidate generation
# ---------------------------------------------------------------------------
def _anchor_values(values, low, high, limit):
    seen = []
    for value in values:
        if value < low - 1e-6 or value > high + 1e-6:
            continue
        if any(abs(value - other) < 1e-4 for other in seen):
            continue
        seen.append(float(value))
        if len(seen) >= limit:
            break
    return seen


WEDGE_BASE_LAYER = 0
"""A wedge step's layer tag.

Zero rather than a real depth, so a normal box landing on one gets
``1 + 0 = 1`` and counts as a first layer.  A wedge step is a *structural
base*, not a storey: the staircase is a ramp built out of the container's own
geometry, and charging its depth to the cargo above it would forbid the
mechanism the moment the chain got two steps long.
"""


def stack_level(box: AABB, container: dict, role: str, config,
                model: "ContainerModel | None" = None) -> int:
    """Layer depth from the actual support relation.

        L(i) = 1                              resting on the floor or a shelf
        L(i) = 1 + max L(j) over supports j   resting on cargo

    Not "how many items are under the centre".  A box can be offset so that its
    centre happens to sit over a first-layer item while it is really carried by
    a second-layer one beside it -- and the other way round.  The depth that
    matters is the one along the chain that holds it up.
    """
    if role in (cls.ROLE_WEDGE_STEP, cls.ROLE_SLOPE_INFILL):
        return WEDGE_BASE_LAYER
    supports = stability.supporting_items(box, container, config.contact_tolerance)
    if not supports:
        return 1  # floor or shelf
    depths = packed_layers(container, config, model)
    return 1 + max(depths.get(id(p), 1) for p in supports)


def packed_layers(container: dict, config,
                  model: "ContainerModel | None" = None) -> dict:
    """Depth of every packed item, worked out from the support relation.

    The depth used to be read from a ``layer`` key the planner wrote as it
    placed things.  Driving the real environment there is no such key: the
    board is rebuilt from each observation, whose packed items carry position
    and size and nothing else.  Every support therefore answered "layer 1", so
    a box on a box on a box reported depth 2 for ever, the free depth passed it
    unconditionally, and the plateau condition that exists to tell a terrace
    from a tower never ran at all.  Task 000 built a six-storey column of
    0.24 m boxes with every one of them labelled depth 1.

    So derive it instead.  An item with nothing under it is depth 1; anything
    else is one more than the deepest thing holding it up.  Resolved lowest
    first, which is enough to make one pass sufficient because a support is
    always strictly below what it supports.
    """
    items = container.get("packed_items", [])
    # memoised on the container: this is O(n^2) in the packed count and the
    # vetoes ask for it once per candidate.  The packed count is enough of a
    # key because a container only ever grows.
    cached = container.get("_rule_alpha_layers")
    if cached is not None and cached[0] == len(items):
        return cached[1]

    packed = [
        item for item in items
        if not bool(item.get("is_soft", False))
        and not bool(item.get("is_prioritized", False))
    ]
    boxes = []
    for item in packed:
        try:
            dims = packed_dimensions(item)
            pos = stability.world_to_local_position(item, container)
        except (KeyError, TypeError, ValueError):
            continue
        boxes.append((
            item,
            AABB((float(pos[0]), float(pos[1]), float(pos[2])),
                 tuple(float(v) for v in dims), "packed"),
        ))
    boxes.sort(key=lambda pair: float(pair[1].minimum[2]))

    depths: dict[int, int] = {}
    for item, box in boxes:
        stored = item.get("layer")
        if stored is not None and int(stored) == WEDGE_BASE_LAYER:
            depths[id(item)] = WEDGE_BASE_LAYER
            continue
        if model is not None and tri.in_strip(box, model, config):
            # the chamfer staircase is a ramp, not a stack, and in the physics
            # path there is no stored role to say so -- but ``in_strip`` is a
            # geometric test and is available either way
            depths[id(item)] = WEDGE_BASE_LAYER
            continue
        supports = stability.supporting_items(box, container, config.contact_tolerance)
        below = [
            depths[id(s)] for s in supports
            if id(s) in depths and s is not item
        ]
        depths[id(item)] = 1 + max(below) if below else 1
    container["_rule_alpha_layers"] = (len(items), depths)
    return depths


def shelf_residual(shelf: AABB, container: dict, rect: Rect, config
                   ) -> tuple[float, int]:
    """``(largest free rectangle, free component count)`` left on a shelf.

    The shelf is the scarce surface and it is scarce in *area*, not in volume,
    so what matters about a shelf placement is the shape of what it leaves
    behind.  Landing in the middle of an empty shelf can consume a fifth of it
    and destroy all of it, by cutting the one free rectangle into four useless
    slivers.
    """
    from .diagnostics import connected_components, largest_rectangle_in_mask

    cell = config.candidate_grid_cell
    x0, y0 = float(shelf.minimum[0]), float(shelf.minimum[1])
    nx = max(1, int(round(float(shelf.size[0]) / cell)))
    ny = max(1, int(round(float(shelf.size[1]) / cell)))
    xs = x0 + (np.arange(nx) + 0.5) * cell
    ys = y0 + (np.arange(ny) + 0.5) * cell
    xx, yy = np.meshgrid(xs, ys, indexing="ij")

    free = np.ones((nx, ny), dtype=bool)
    top = float(shelf.maximum[2])
    occupied = [rect]
    for box, _soft, _prio in packed_aabbs_local(container):
        if abs(float(box.minimum[2]) - top) > config.contact_tolerance:
            continue
        occupied.append(box_rect(box))
    for taken in occupied:
        free &= ~(
            (xx >= taken.x_min - 1e-9) & (xx <= taken.x_max + 1e-9)
            & (yy >= taken.y_min - 1e-9) & (yy <= taken.y_max + 1e-9)
        )

    cells, _box = largest_rectangle_in_mask(free)
    _labels, count = connected_components(free)
    return cells * cell * cell, count


def usable_shelf_rect(shelf: AABB, model: ContainerModel, config) -> Rect:
    """The part of a shelf a box may actually occupy.

    The floor has had this all along -- ``floor_rect`` is inset from the walls
    by the inclusion clearance -- and the shelf did not.  A shelf AABB runs to
    the wall and the main shelf runs 20 mm *past* it, so every anchor derived
    from its edges asked for a pose flush with the wall, which
    ``check_inclusion`` refuses at a 16 mm margin.  The wall-side anchors were
    therefore always dead, and cargo landed at whatever anchor came next --
    which is the gap between the wall and the shelf items.
    """
    clearance = config.inclusion_clearance
    return Rect(
        max(float(shelf.minimum[0]), model.x_wall_min + clearance),
        min(float(shelf.maximum[0]), model.x_wall_max - clearance),
        max(float(shelf.minimum[1]), model.y_opening + clearance),
        min(float(shelf.maximum[1]), model.y_back - clearance),
    )


def _shelf_anchors(shelf: AABB, container: dict, dx: float, dy: float,
                   gap: float, config, model: ContainerModel) -> tuple[list, list]:
    """Anchors measured from the shelf itself, and from what is already on it.

    Back corner first, then flush against every edge of every item already up
    there, so the shelf packs from the back and from the sides instead of one
    item landing in the middle of it.
    """
    rect = usable_shelf_rect(shelf, model, config)
    top = float(shelf.maximum[2])
    xs = [rect.x_min + dx / 2.0, rect.x_max - dx / 2.0]
    ys = [rect.y_max - dy / 2.0, rect.y_min + dy / 2.0]
    for box, _soft, _prio in packed_aabbs_local(container):
        if abs(float(box.minimum[2]) - top) > config.contact_tolerance:
            continue  # resting on some other surface, not this shelf
        xs.extend(
            (
                float(box.minimum[0]) - dx / 2.0 - gap,
                float(box.maximum[0]) + dx / 2.0 + gap,
            )
        )
        ys.extend(
            (
                float(box.minimum[1]) - dy / 2.0 - gap,
                float(box.maximum[1]) + dy / 2.0 + gap,
            )
        )
    return (
        _anchor_values(
            sorted(xs), rect.x_min + dx / 2.0, rect.x_max - dx / 2.0 + 1e-9,
            config.max_anchor_x,
        ),
        _anchor_values(
            sorted(ys, reverse=True), rect.y_min + dy / 2.0,
            rect.y_max - dy / 2.0 + 1e-9, config.max_anchor_y,
        ),
    )


def generate_candidates(board: Board, profile: cls.ItemProfile, container_idx: int,
                        orientation: cls.Orientation, surface_filter, config) -> list[Candidate]:
    model = board.model(container_idx)
    container = board.container(container_idx)
    dx, dy, dz = orientation.dx, orientation.dy, orientation.dz
    gap = config.settled_clearance
    rect = model.floor_rect

    packed = [b for b, _s, _p in packed_aabbs_local(container)]
    pocket_ceiling = slope_pocket_ceiling(board, container_idx, model)
    allow_item_tops = config.allow_slope_infill_on_items and "item" in surface_filter
    surfaces = [
        (surface, kind, name)
        for surface, kind, name in _supports(model, container, config, allow_item_tops)
        if kind in surface_filter
    ]
    if not surfaces:
        return []

    # ---- x anchors ----
    xs = [
        rect.x_min + dx / 2.0,
        rect.x_max - dx / 2.0,
        0.0,
        model.soft_zone.x_max - dx / 2.0,
        model.priority_zone.x_min + dx / 2.0,
        model.corridor.x_min - dx / 2.0 - gap,
        model.corridor.x_max + dx / 2.0 + gap,
        model.centre_band.x_min + dx / 2.0,
        model.centre_band.x_max - dx / 2.0,
    ]
    if allow_item_tops:
        xs.append(model.x_wall_min + dx / 2.0 + config.inclusion_clearance)
        # the next staircase step reaches past the one it stands on, as far as
        # the chamfer and the support ratio allow
        for box in packed:
            if not tri.in_strip(box, model, config):
                continue
            support_left = float(box.minimum[0])
            bottom_z = float(box.maximum[2])
            overhang = tri.max_overhang(model, support_left, bottom_z, dx, config)
            xs.append(support_left - overhang + dx / 2.0)
            xs.append(support_left + dx / 2.0)
    for box in packed:
        xs.extend(
            (
                float(box.maximum[0]) + dx / 2.0 + gap,
                float(box.minimum[0]) - dx / 2.0 - gap,
                float(box.minimum[0]) + dx / 2.0,
                float(box.maximum[0]) - dx / 2.0,
            )
        )
    xs = _anchor_values(
        sorted(xs, key=lambda v: (-abs(v), v)),
        model.x_wall_min + dx / 2.0,
        rect.x_max - dx / 2.0 + 1e-9,
        config.max_anchor_x,
    )

    # ---- y anchors (back first: Layer 1 grows from the back wall forward) ----
    ys = [rect.y_max - dy / 2.0, model.corridor.y_max + dy / 2.0 + gap, rect.y_min + dy / 2.0]
    for box in packed:
        ys.extend(
            (
                float(box.minimum[1]) - dy / 2.0 - gap,
                float(box.maximum[1]) + dy / 2.0 + gap,
                float(box.maximum[1]) - dy / 2.0,
                float(box.minimum[1]) + dy / 2.0,
            )
        )
    ys = _anchor_values(
        sorted(ys, reverse=True),
        rect.y_min + dy / 2.0,
        rect.y_max - dy / 2.0 + 1e-9,
        config.max_anchor_y,
    )

    candidates: list[Candidate] = []
    seen = set()
    for surface, kind, name in surfaces:
        top = float(surface.maximum[2]) if kind != "floor" else model.z_floor
        z = top + dz / 2.0
        surface_xs, surface_ys = xs, ys
        if kind == "shelf" and config.shelf_own_anchors:
            # A shelf is its own surface with its own back corner.  Sharing the
            # floor's anchors meant a shelf placement was never offered the
            # shelf's back edge, nor a position flush beside something already
            # up there -- which is precisely why shelf cargo sat at the front
            # and used a fifth of the area.
            shelf_xs, shelf_ys = _shelf_anchors(
                surface, container, dx, dy, gap, config, model
            )
            # union, shelf-derived first: the shared floor anchors still find
            # perfectly good positions, they just never included the shelf's
            # own back corner.  Replacing them lost more than it gained.
            surface_xs = shelf_xs + [x for x in xs if x not in shelf_xs]
            surface_ys = shelf_ys + [y for y in ys if y not in shelf_ys]
        if kind == "item":
            # staircase only: the support has to be a step in the strip
            if not tri.in_strip(surface, model, config):
                continue
        for x in surface_xs:
            for y in surface_ys:
                key = (round(x, 4), round(y, 4), round(z, 4))
                if key in seen:
                    continue
                seen.add(key)
                box = AABB((float(x), float(y), float(z)), (dx, dy, dz), "candidate")
                if kind == "item":
                    state = board.triangle_state(container_idx)
                    support_rect = box_rect(surface)
                    if not tri.is_wedge_step(box, support_rect, model, config):
                        continue
                    if not tri.strip_reserved_for(profile, state, model, config):
                        continue
                ok, why = validate(box, model, container, config)
                if not ok:
                    continue
                role = _role_for(
                    box, model, profile, orientation, board, container_idx,
                    config, kind, pocket_ceiling,
                )
                candidates.append(
                    Candidate(
                        box=box,
                        profile=profile,
                        orientation=orientation,
                        container_idx=container_idx,
                        surface=kind,
                        surface_name=name,
                        role=role,
                        family=(
                            l2.FAMILY_SHELF if kind == "shelf"
                            else l2.FAMILY_WEDGE_STEP if kind == "item"
                            else l2.FAMILY_FLOOR
                        ),
                    )
                )
                if len(candidates) >= config.max_candidates_per_orientation:
                    return candidates
    return candidates


def slope_pocket_ceiling(board: "Board | None", container_idx: int,
                         model: ContainerModel) -> float:
    """Upper limit for a slope-infill placement.

    The pocket is capped by the small shelf above it, and — spec section 9,
    condition 4 — by the slope wall front already standing in front of it: an
    infill piece that overtops the wall has nothing shielding it.
    """
    ceiling = model.slope_pocket["z_max"]
    if board is None:
        return ceiling
    wall_tops = [
        p.top_z for p in board.placements[container_idx] if p.role_is_wall_front
    ]
    if wall_tops:
        ceiling = min(ceiling, max(wall_tops))
    return ceiling


def in_slope_pocket(box: AABB, model: ContainerModel, config,
                    ceiling: float | None = None) -> bool:
    """A genuine slope-pocket filler.

    Not "the box pokes 4 mm past the floor limit": the box has to live *inside*
    the wedge — a real penetration, a majority of its footprint left of the
    floor limit, and its whole body under the small shelf.  Anything wider is a
    Layer 2 bridging move and out of scope for this prototype.
    """
    pocket = model.slope_pocket
    limit = pocket["z_max"] if ceiling is None else min(pocket["z_max"], ceiling)
    penetration = model.x_floor_min - float(box.minimum[0])
    if penetration < config.slope_pocket_min_penetration:
        return False
    if float(box.maximum[2]) > limit + 1e-6:
        return False
    if float(box.minimum[2]) < pocket["z_min"] - 1e-6:
        return False
    width = max(1e-9, float(box.size[0]))
    inside_share = min(penetration, width) / width
    return inside_share >= config.slope_pocket_min_share


def _role_for(box, model, profile, orientation, board, container_idx, config,
              surface: str, pocket_ceiling: float | None = None) -> str:
    if surface == "item":
        return cls.ROLE_WEDGE_STEP
    if surface == "shelf":
        # A shelf placement is never a structural member: its pose comes from
        # the shelf orientation policy, not from the structural exception, and
        # it is not part of the floor foundation.  Tagging it "elongated" here
        # would put it behind the structural mask and inflate
        # structural_volume_m3 with cargo that is just lying on a shelf.
        return cls.ROLE_NONE
    if in_slope_pocket(box, model, config, pocket_ceiling):
        return cls.ROLE_SLOPE_INFILL
    near_wall_front = (
        float(box.minimum[0]) <= model.x_floor_min + config.wall_front_band
    )
    if (
        profile.cargo_class == cls.NORMAL_HARD
        and near_wall_front
        and wall_front_material(profile, model, config)
        and orientation.dz >= config.wall_front_min_height
    ):
        # The wall front stays low on purpose: the wedge volume is recovered by
        # the staircase above it, not by one tall piece, so the transport lane
        # is never traded away for structure.
        if orientation.dz <= wall_front_height_limit(model, config) and (
            _wall_front_wanted(board, container_idx, model, config)
        ):
            return cls.ROLE_WALL_FRONT
    if profile.is_elongated and not profile.is_soft:
        return cls.ROLE_ELONGATED
    if is_tall_perimeter(box, model, profile, orientation, config):
        return cls.ROLE_TALL_PERIMETER
    return cls.ROLE_NONE


def in_wedge_approach(rect: Rect, model: ContainerModel, config) -> bool:
    """Is this footprint in the band everything wedge-side is delivered through?

    The chamfer runs the whole depth and the sweep comes straight in along
    ``y``, so a single band of ``x`` carries the approach to every wedge step
    and every terrace above them.  Depth does not enter into it: a tall box at
    the back of this band blocks nothing, but one at the front blocks all of it,
    and ``sealed_added`` already prices that difference.  What this identifies
    is *which columns matter*.
    """
    return rect.x_min <= model.x_floor_min + config.wedge_approach_band + 1e-9


def blocks_wedge_approach(box: AABB, model: ContainerModel, role: str,
                          config) -> bool:
    """A placement that stands tall in the wedge approach.

    The wall front is exempt: it is *meant* to be the wall against the chamfer
    foot and already has its own, lower, height cap.  Wedge steps and slope
    infill are exempt because they are the thing being protected.
    """
    if role in (cls.ROLE_WALL_FRONT, cls.ROLE_WEDGE_STEP, cls.ROLE_SLOPE_INFILL):
        return False
    if not in_wedge_approach(box_rect(box), model, config):
        return False
    return (
        float(box.maximum[2]) - model.z_floor
        > config.wedge_approach_max_height + 1e-9
    )


def is_tall_perimeter(box: AABB, model: ContainerModel, profile: cls.ItemProfile,
                      orientation: cls.Orientation, config) -> bool:
    """A standing pose parked against a wall rather than laid down.

    This is the fallback for cargo that is too tall to be wall-front material
    but not slender enough to be classified elongated.  Without it such an item
    has no structural role at all and the max-footprint rule lays it down,
    spending floor area to store the air above it.  It has to be a genuinely
    standing pose (taller than the item's flattest one), tall enough to be
    worth it, and touching a perimeter — the tipping veto and the transport
    check decide the rest.
    """
    if profile.is_soft:
        return False
    if orientation.dz < config.tall_perimeter_min_height:
        return False
    budget = config.tall_perimeter_max_footprint_fraction * model.usable_floor_area
    if profile.max_footprint > budget + 1e-9:
        return False
    flattest = min(o.dz for o in profile.orientations)
    if orientation.dz <= flattest + 1e-9:
        return False
    rect = box_rect(box)
    if in_wedge_approach(rect, model, config) and (
        orientation.dz > config.wedge_approach_max_height + 1e-9
    ):
        # Standing up here is the one placement that costs more than it buys:
        # it seals the approach to every wedge step and every terrace above
        # them.  Laid flat the same item is a low top a terrace can grow from.
        # The test is the height, not the label, so one setting governs both
        # this and the veto and the pair can be switched off together.
        return False
    tol = config.settled_clearance * 1.6
    against_left = abs(rect.x_min - model.floor_rect.x_min) <= tol
    against_right = abs(model.floor_rect.x_max - rect.x_max) <= tol
    against_back = abs(model.floor_rect.y_max - rect.y_max) <= tol
    return bool(against_left or against_right or against_back)


def wall_front_height_limit(model: ContainerModel, config) -> float:
    """How tall a slope wall-front piece may be.

    Two limits, whichever is lower:

    * half the floor-to-shelf gap.  The wall front lives under the small shelf,
      and a piece that fills most of that gap leaves the strip unusable while
      spending a large item on structure — ordinary tall cargo does more good
      on the perimeter.
    * what can actually be carried in: the commanded pose is lifted for
      release-and-drop, and the transport sweep still has to clear the shelf
      underside by the official safety margin.
    """
    gap = max(0.0, model.shelf_bottom_z - model.z_floor)
    transportable = gap - (config.floor_action_lift + config.settled_clearance)
    return max(0.0, min(config.wall_front_max_height_shelf_fraction * gap,
                        transportable))


def wall_front_material(profile: cls.ItemProfile, model: ContainerModel, config) -> bool:
    """Is this item wall material rather than foundation material?

    Spec section 10 values height over base area at the wall front, so an item
    with a big base is worth more lying flat in the foundation than standing
    against the slope.  The cap is expressed as a share of the usable floor.
    """
    budget = config.wall_front_max_footprint_fraction * model.usable_floor_area
    return profile.max_footprint <= budget + 1e-9


def _wall_height_ratio(board: Board, container_idx: int, model: ContainerModel) -> float:
    tops = [
        p.top_z for p in board.placements[container_idx] if p.role_is_wall_front
    ]
    if not tops:
        return 0.0
    return (max(tops) - model.z_floor) / max(1e-9, model.z_ceiling - model.z_floor)


def _wall_front_depth_ratio(board: Board, container_idx: int,
                            model: ContainerModel) -> float:
    covered = sum(
        p.rect.y_max - p.rect.y_min
        for p in board.placements[container_idx]
        if p.role_is_wall_front
    )
    return covered / max(1e-9, model.y_back - model.y_opening)


def _wall_front_wanted(board: Board, container_idx: int, model: ContainerModel,
                       config) -> bool:
    """The slope wall is finished once it spans the depth or reaches height."""
    if _wall_front_depth_ratio(board, container_idx, model) >= config.wall_front_depth_target:
        return False
    return _wall_height_ratio(board, container_idx, model) < config.wall_front_target_ratio


# ---------------------------------------------------------------------------
# Features
# ---------------------------------------------------------------------------
def _wall_contact(box: AABB, model: ContainerModel, container: dict, config) -> float:
    """Perimeter length in contact with a container wall or a settled item."""
    tol = config.settled_clearance * 1.6
    rect = box_rect(box)
    contact = 0.0
    if abs(rect.x_min - model.floor_rect.x_min) <= tol:
        contact += rect.y_max - rect.y_min
    if abs(model.floor_rect.x_max - rect.x_max) <= tol:
        contact += rect.y_max - rect.y_min
    if abs(model.floor_rect.y_max - rect.y_max) <= tol:
        contact += rect.x_max - rect.x_min
    for packed, _s, _p in packed_aabbs_local(container):
        pr = box_rect(packed)
        z_overlap = min(float(packed.maximum[2]), float(box.maximum[2])) - max(
            float(packed.minimum[2]), float(box.minimum[2])
        )
        if z_overlap <= 0.02:
            continue
        if abs(pr.x_min - rect.x_max) <= tol or abs(rect.x_min - pr.x_max) <= tol:
            overlap = min(pr.y_max, rect.y_max) - max(pr.y_min, rect.y_min)
            contact += max(0.0, overlap)
        if abs(pr.y_min - rect.y_max) <= tol or abs(rect.y_min - pr.y_max) <= tol:
            overlap = min(pr.x_max, rect.x_max) - max(pr.x_min, rect.x_min)
            contact += max(0.0, overlap)
    return contact


def _item_contact(box: AABB, container: dict, config) -> float:
    """Shared boundary length with already-settled items (walls excluded)."""
    tol = config.settled_clearance * 1.6
    rect = box_rect(box)
    contact = 0.0
    for packed, _soft, _prio in packed_aabbs_local(container):
        pr = box_rect(packed)
        z_overlap = min(float(packed.maximum[2]), float(box.maximum[2])) - max(
            float(packed.minimum[2]), float(box.minimum[2])
        )
        if z_overlap <= 0.02:
            continue
        if abs(pr.x_min - rect.x_max) <= tol or abs(rect.x_min - pr.x_max) <= tol:
            contact += max(0.0, min(pr.y_max, rect.y_max) - max(pr.y_min, rect.y_min))
        if abs(pr.y_min - rect.y_max) <= tol or abs(rect.y_min - pr.y_max) <= tol:
            contact += max(0.0, min(pr.x_max, rect.x_max) - max(pr.x_min, rect.x_min))
    return contact


def _cluster_contact(box: AABB, container: dict, want_soft: bool, want_prio: bool,
                     config) -> float:
    tol = config.settled_clearance * 1.6
    rect = box_rect(box)
    contact = 0.0
    for packed in container.get("packed_items", []):
        if bool(packed.get("is_soft", False)) != want_soft:
            continue
        if bool(packed.get("is_prioritized", False)) != want_prio:
            continue
        dims = packed.get("dims")
        pos = packed.get("pos")
        if dims is None or pos is None:
            continue
        offset_x = float(container.get("center", (0.0, 0.0, 0.0))[0])
        pr = Rect(
            pos[0] - offset_x - dims[0] / 2.0,
            pos[0] - offset_x + dims[0] / 2.0,
            pos[1] - dims[1] / 2.0,
            pos[1] + dims[1] / 2.0,
        )
        if abs(pr.x_min - rect.x_max) <= tol or abs(rect.x_min - pr.x_max) <= tol:
            contact += max(0.0, min(pr.y_max, rect.y_max) - max(pr.y_min, rect.y_min))
        if abs(pr.y_min - rect.y_max) <= tol or abs(rect.y_min - pr.y_max) <= tol:
            contact += max(0.0, min(pr.x_max, rect.x_max) - max(pr.x_min, rect.x_min))
    return contact


def _has_backing(box: AABB, model: ContainerModel, container: dict, config) -> bool:
    """A wall, or a settled item at least 60 % as tall, on some side."""
    rect = box_rect(box)
    tol = config.settled_clearance * 1.8
    if abs(rect.x_min - model.floor_rect.x_min) <= tol:
        return True
    if abs(model.floor_rect.x_max - rect.x_max) <= tol:
        return True
    if abs(model.floor_rect.y_max - rect.y_max) <= tol:
        return True
    needed = float(box.minimum[2]) + 0.6 * float(box.size[2])
    for packed, _s, _p in packed_aabbs_local(container):
        if float(packed.maximum[2]) < needed:
            continue
        pr = box_rect(packed)
        if abs(pr.x_min - rect.x_max) <= tol or abs(rect.x_min - pr.x_max) <= tol:
            if min(pr.y_max, rect.y_max) - max(pr.y_min, rect.y_min) > 0.05:
                return True
        if abs(pr.y_min - rect.y_max) <= tol or abs(rect.y_min - pr.y_max) <= tol:
            if min(pr.x_max, rect.x_max) - max(pr.x_min, rect.x_min) > 0.05:
                return True
    return False


def row_waste(grid, rect: Rect, extra_mask, min_width: float) -> float:
    """Free floor this placement would strand in its own row, in m^2.

    A row of the container is a fixed width, and what tiles it is a *sequence*
    of poses, not a single best one.  The floor is 1.472 m across: two 0.55 m
    boxes use 1.126 and leave 0.346, which is too narrow for anything in the
    manifest; 0.55 + 0.40 + 0.40 uses 1.402 and leaves 0.070.  Both of those
    poses have exactly the same footprint, so every key that ranks by footprint
    scores them equal and the tie is settled by depth -- by something that
    cannot see the difference between a row that tiles and a row that does not.

    So measure it: after this box goes down, how much of the free floor beside
    it lies in runs narrower than the narrowest thing still to come.  That area
    is not free space, it is waste, and it should be priced as waste.
    """
    band = grid.rect_mask(rect)
    free = grid.usable & ~grid.occupied & ~extra_mask
    rows = np.nonzero(band.any(axis=0))[0]
    if rows.size == 0:
        return 0.0
    need = max(1, int(math.ceil(min_width / grid.cell)))
    waste_cells = 0
    for iy in rows:
        column = free[:, iy]
        run = 0
        for value in column:
            if value:
                run += 1
                continue
            if 0 < run < need:
                waste_cells += run
            run = 0
        if 0 < run < need:
            waste_cells += run
    return float(waste_cells) * grid.cell_area


def terrain_behind(grid, rect: Rect) -> float:
    """Highest terrain standing between ``rect`` and the back wall.

    Only the columns ``rect`` itself occupies count, because delivery is a
    straight sweep in y at the target's own x: what a box in front of you
    blocks is your column, not the whole floor.  With nothing behind it the
    answer is the floor, which is what makes "stay lower than what is behind
    you" also mean "do not be the first thing in an empty column".
    """
    columns = (grid.xs >= rect.x_min - 1e-9) & (grid.xs <= rect.x_max + 1e-9)
    if not columns.any():
        return float(grid.model.z_floor)
    behind = grid.usable & (grid.yy > rect.y_max - 1e-9)
    behind = behind & columns[:, None]
    if not behind.any():
        return float(grid.model.z_floor)
    return float(grid.height[behind].max())


def reach_at(grid, z_floor: float, z_rel: float, extra_mask=None,
             extra_top: float = 0.0) -> tuple[float, float]:
    """``(usable-and-reachable, usable-but-sealed)`` area at working height ``z``.

    The validator sweeps straight in along ``y`` at the target ``x``, so a cell
    is reachable for something whose underside is ``z_rel`` above the floor
    exactly when nothing between it and the opening in its own column stands
    higher than ``z_rel``.  "Usable at ``z``" means the terrain there is at or
    below ``z`` -- bare floor at ``z`` = 0, and anything you could still build
    on at greater heights.

    Everything usable but not reachable is *sealed*: a per-placement legality
    check cannot see it, because each individual placement was legal when it
    was made.

    ``z_rel`` = 0 is the floor case and the one that is exact.  Evaluating the
    same question at a candidate's own top is what prices a wall: a tall box
    with lower ground behind it seals that ground for everything after it --
    but only if the ground was still worth something, which is why this asks
    about usable area rather than about height alone.
    """
    height = grid.height - z_floor
    if extra_mask is not None:
        height = np.where(extra_mask, max(extra_top, 0.0), height)
    running = np.maximum.accumulate(height, axis=1)
    before = np.concatenate(
        [np.zeros((height.shape[0], 1)), running[:, :-1]], axis=1
    )
    usable = grid.usable & (height <= z_rel + 1e-9)
    reachable = usable & (before <= z_rel + 1e-9)
    reachable_area = float(reachable.sum()) * grid.cell_area
    usable_area = float(usable.sum()) * grid.cell_area
    return reachable_area, usable_area - reachable_area


def floor_reach(grid, z_floor: float, extra_mask=None) -> tuple[float, float]:
    """``reach_at`` at floor level: what can still be put on the bare floor."""
    return reach_at(grid, z_floor, 0.0, extra_mask, 0.0)


def _plateau_after(grid, model: ContainerModel, rect: Rect, top_z: float,
                   config) -> dict:
    """Hard plateau statistics with one extra hard top stamped in.

    Works on a shallow copy of the two arrays the statistic reads, so the real
    grid is untouched and no cache has to be invalidated.
    """
    import copy as _copy

    from .diagnostics import SUPPORT_HARD

    scratch = _copy.copy(grid)
    scratch.height = grid.height.copy()
    scratch.support = grid.support.copy()
    mask = grid.rect_mask(rect)
    higher = mask & (top_z >= scratch.height - 1e-9)
    scratch.height[higher] = top_z
    scratch.support[higher] = SUPPORT_HARD
    return l2.hard_plateau_stats(
        scratch, model.z_floor, config.plateau_height_tolerance
    )


def compute_features(candidate: Candidate, board: Board, config,
                     with_grid: bool = True, with_rect: bool = False) -> None:
    model = board.model(candidate.container_idx)
    container = board.container(candidate.container_idx)
    box = candidate.box
    rect = box_rect(box)
    features = candidate.features

    features["y_back"] = float(box.maximum[1])
    features["y_centre"] = float(box.center[1])
    features["top_z"] = float(box.maximum[2])
    features["footprint"] = candidate.orientation.footprint
    features["volume"] = float(np.prod(box.size))
    features["wall_contact"] = _wall_contact(box, model, container, config)
    features["item_contact"] = _item_contact(box, container, config)
    # extending the packed frontier beats hugging a far wall: it is what keeps
    # the leftover space in one piece at an edge instead of a strip up the
    # middle
    features["frontier_contact"] = (
        features["wall_contact"]
        + config.frontier_item_contact_weight * features["item_contact"]
    )
    features["has_backing"] = _has_backing(box, model, container, config)
    features["corridor_overlap"] = rect.overlap_area(model.corridor)
    features["soft_zone_fit"] = rect.overlap_area(model.soft_zone) / max(rect.area, 1e-9)
    features["priority_zone_fit"] = (
        rect.overlap_area(model.priority_zone) / max(rect.area, 1e-9)
    )
    features["back_band_fit"] = rect.overlap_area(model.back_band) / max(rect.area, 1e-9)
    features["wall_strip_fit"] = (
        rect.overlap_area(model.wall_front_strip) / max(rect.area, 1e-9)
    )
    features["edge_affinity"] = max(
        rect.overlap_area(model.left_edge), rect.overlap_area(model.right_edge)
    ) / max(rect.area, 1e-9)
    # distance from the right-front corner, normalised: 0 there, 1 at the far
    # back left.  Typed cargo on the floor is ranked by this rather than by
    # depth, because depth is what hard wants and these two must not compete
    # for the same corner.
    floor = model.floor_rect
    span_x = max(floor.x_max - floor.x_min, 1e-9)
    span_y = max(floor.y_max - floor.y_min, 1e-9)
    features["front_right_cost"] = round(
        (floor.x_max - 0.5 * (rect.x_min + rect.x_max)) / span_x
        + (0.5 * (rect.y_min + rect.y_max) - floor.y_min) / span_y,
        6,
    )
    features["soft_cluster"] = _cluster_contact(box, container, True, False, config)
    features["priority_cluster"] = _cluster_contact(box, container, False, True, config)
    features["sp_cluster"] = _cluster_contact(box, container, True, True, config)
    features["slope_pocket_volume"] = (
        max(0.0, model.x_floor_min - rect.x_min)
        * (rect.y_max - rect.y_min)
        * float(box.size[2])
        if model.touches_slope_pocket(box)
        else 0.0
    )

    # what this placement does to the connected hard plateau, which is the
    # thing Layer 2 exists to grow.  Cheap: one stamp on a copied grid.
    if with_grid and candidate.surface == "item" and candidate.role in (
        l2.ROLE_TERRACE, l2.ROLE_BRIDGE, l2.ROLE_WEDGE_BRIDGE
    ):
        grid = board.grid(candidate.container_idx)
        before = board.plateau_stats(candidate.container_idx)
        after = _plateau_after(grid, model, rect, float(box.maximum[2]), config)
        features["plateau_gain"] = max(0.0, after["largest"] - before["largest"])
        features["hard_plateau_largest"] = after["largest"]
        features["hard_plateau_total_gain"] = after["total"] - before["total"]
        state = stability.evaluate(box, container, config)
        features["stability_margin"] = state.margin
        features["support_contacts"] = state.contact_count
        features["support_area_ratio"] = round(
            min(1.0, state.contact_area / max(1e-9, rect.area)), 4
        )

    if with_grid and candidate.surface == "shelf" and config.shelf_residual_key:
        shelf = next(
            (s for s in shelf_aabbs(container) if s.name == candidate.surface_name),
            None,
        )
        if shelf is not None:
            residual, fragments = shelf_residual(shelf, container, rect, config)
            features["shelf_residual_rect"] = residual
            features["shelf_fragments"] = fragments

    if not with_grid or candidate.surface != "floor":
        features.setdefault("new_interior_hole_area", 0.0)
        features.setdefault("open_free_area", 0.0)
        features.setdefault("free_component_count", 0)
        features.setdefault("largest_residual_rect", 0.0)
        features.setdefault("largest_residual_rect_dims", (0.0, 0.0))
        features.setdefault("neighbour_height_step", 0.0)
        # a shelf or step placement takes nothing away from the floor approach
        features.setdefault("stranded_added", 0.0)
        features.setdefault("reach_free_after", 0.0)
        features.setdefault("sealed_added", 0.0)
        features.setdefault("large_fit_kept", True)
        features.setdefault("plateau_gain", 0.0)
        features.setdefault("hard_plateau_largest", 0.0)
        features.setdefault("stability_margin", 0.0)
        features.setdefault("terrain_behind", float(model.z_floor))
        features.setdefault("row_waste", 0.0)
        return

    grid = board.grid(candidate.container_idx)
    mask = grid.rect_mask(rect)
    free_after = grid.free_mask() & ~mask
    reached = reachable_from_boundary(free_after, grid.usable)
    interior = free_after & ~reached
    features["new_interior_hole_area"] = float(interior.sum()) * grid.cell_area
    features["open_free_area"] = float(reached.sum()) * grid.cell_area
    features["free_component_count"] = _count_components(interior)

    # flatness: how far this top sits from the tops it will neighbour
    ring = _dilate(mask) & ~mask & grid.usable & grid.occupied
    if ring.any():
        features["neighbour_height_step"] = float(
            np.abs(grid.height[ring] - float(box.maximum[2])).mean()
        )
    else:
        features["neighbour_height_step"] = 0.0

    features["terrain_behind"] = terrain_behind(grid, rect)
    features["row_waste"] = (
        row_waste(grid, rect, mask, board.min_useful_width)
        if config.row_tiling and candidate.surface == "floor" else 0.0
    )

    # what this placement costs the way in.  ``reachable_before`` is a property
    # of the board, so it is cached per step rather than recomputed per
    # candidate.
    top_rel = float(box.maximum[2]) - model.z_floor
    reach_after, stranded_after = floor_reach(grid, model.z_floor, mask)
    reachable_before, stranded_before = board.floor_reach(candidate.container_idx)
    features["reach_free_after"] = reach_after
    features["reach_loss"] = max(0.0, reachable_before - reach_after)
    features["stranded_added"] = max(0.0, stranded_after - stranded_before)

    # the same question asked at the heights a later item might arrive at.  It
    # cannot be asked at this box's own top: a box travelling at 0.40 clears a
    # wall whose top is 0.40, so a wall never seals anything at its own height
    # and the answer would always be zero.  What a wall really costs is
    # delivery to the lower ground behind it.
    worst = 0.0
    for probe in config.reach_probe_heights:
        if probe >= top_rel - 1e-9:
            continue  # this box is not in the way at or above its own top
        _r_before, sealed_before = board.reach_at_height(
            candidate.container_idx, probe
        )
        _r_after, sealed_after = reach_at(
            grid, model.z_floor, probe, mask, top_rel
        )
        worst = max(worst, sealed_after - sealed_before)
    features["sealed_added"] = max(0.0, worst)

    if with_rect:
        from .diagnostics import largest_rectangle_in_mask

        cells, cell_box = largest_rectangle_in_mask(reached)
        features["largest_residual_rect"] = cells * grid.cell_area
        r0, c0, r1, c1 = cell_box
        dims = ((r1 - r0 + 1) * grid.cell, (c1 - c0 + 1) * grid.cell) if cells else (0.0, 0.0)
        features["largest_residual_rect_dims"] = dims
        features["large_fit_kept"] = board.foundation_still_fits(
            candidate.container_idx, dims, candidate.profile
        )
    else:
        features.setdefault("largest_residual_rect", 0.0)
        features.setdefault("largest_residual_rect_dims", (0.0, 0.0))
        features.setdefault("large_fit_kept", True)


def _count_components(mask: np.ndarray) -> int:
    """Cheap component count for the (usually tiny) interior-hole mask."""
    if not mask.any():
        return 0
    from .diagnostics import connected_components

    _labels, count = connected_components(mask)
    return count


# ---------------------------------------------------------------------------
# Archetype comparators
# ---------------------------------------------------------------------------
def _waste_bucket(c, step: float = 0.02):
    """Row waste, bucketed so it separates real differences and nothing else.

    Two poses of the same box have the same footprint, so this is the term that
    decides between the row that tiles and the row that leaves a dead strip.
    Bucketed because a centimetre of difference is noise and should not
    outrank depth.
    """
    return round(c.features.get("row_waste", 0.0) / step)


def _key_max_footprint(c):
    return (
        -c.features["footprint"],
        _waste_bucket(c),
        -c.features["y_back"],
        c.features.get("stranded_added", 0.0),
        -c.features["frontier_contact"],
        c.features["top_z"],
    )


def _key_back_corner(c):
    return (
        -c.features["y_back"],
        _waste_bucket(c),
        c.features.get("stranded_added", 0.0),
        -c.features["frontier_contact"],
        -c.features["footprint"],
    )


def _key_min_hole(c):
    # The row waste was tried here, where the choice is actually made, and it
    # made things worse: task 000 went 15 placements to 14, fill 17.714 to
    # 12.054, and the dead strips it was meant to remove grew from 0.146 to
    # 0.253 m^2.  Added to the interior-hole area it does not refine that
    # ranking, it replaces it.
    return (
        c.features["new_interior_hole_area"],
        c.features["free_component_count"],
        c.features.get("stranded_added", 0.0),
        -c.features["y_back"],
    )


def _key_largest_residual(c):
    return (
        -c.features["largest_residual_rect"],
        c.features["new_interior_hole_area"],
        c.features.get("stranded_added", 0.0),
        -c.features["y_back"],
    )


def _key_shelf_saving(c, depth_bucket: float = 0.05):  # noqa: D401
    """Back-most feasible, then keep the biggest bay whole, then least
    fragmentation.

    Depth is bucketed rather than compared exactly, because "back-most" to
    within a few centimetres is not a real preference and comparing it exactly
    means the residual-area term never gets to decide anything.  A shelf is
    scarce in area, so what a placement leaves behind matters more than the
    last two centimetres of push-in.
    """
    depth = -round(c.features["y_back"] / max(depth_bucket, 1e-6))
    return (
        depth,
        -c.features.get("shelf_residual_rect", 0.0),
        c.features.get("shelf_fragments", 0),
        c.features["footprint"],
        c.orientation.tipping_ratio,
    )


def _key_soft_edge(c):
    # right front, not merely "in the zone": hard grows from the back right, so
    # typed cargo wants the opposite corner and wants it measured, not implied.
    return (
        -c.features["soft_zone_fit"],
        -c.features["soft_cluster"],
        c.features.get("front_right_cost", 0.0),
    )


def _key_priority_edge(c):
    return (
        -c.features["priority_zone_fit"],
        -c.features["priority_cluster"],
        c.features.get("front_right_cost", 0.0),
    )


def _key_sp_cluster(c):
    return (
        -c.features["sp_cluster"],
        -max(c.features["priority_zone_fit"], c.features["soft_zone_fit"]),
        c.features.get("front_right_cost", 0.0),
    )


def _key_elongated_wall(c):
    return (
        0 if c.features["has_backing"] else 1,
        -c.features["y_back"],
        -c.features["wall_contact"],
        -c.features["top_z"],
    )


def _key_slope_infill(c):
    return (-c.features["slope_pocket_volume"], -c.features["y_back"])


def _key_wedge_step(c):
    # climb: reach as far towards the wall as the step legally can, and stay low
    # so the next step still has headroom under the shelf
    return (c.box.minimum[0], c.features["top_z"], -c.features["y_back"])


def _key_wedge_cap(c):
    return (c.box.minimum[0], -c.features["y_back"], c.features["footprint"])


def _key_tall_perimeter(c, depth_first: bool = True):
    # "the deepest legal perimeter", not "the tallest anywhere".  Height used to
    # come first, which is how tall items ended up at the opening with lower
    # terrain behind them -- the one arrangement the straight-in sweep cannot
    # cope with.
    backing = 0 if c.features["has_backing"] else 1
    if depth_first:
        return (backing, -c.features["y_back"], -c.features["top_z"],
                -c.features["frontier_contact"])
    return (backing, -c.features["top_z"], -c.features["frontier_contact"],
            -c.features["y_back"])


def _key_wall_front(c):
    return (
        -c.features["top_z"],
        c.box.minimum[0],
        -c.features["y_back"],
    )


def _key_terrace(c):
    # widen the plateau, and prefer the growth that keeps the back high
    return (
        -c.features.get("plateau_gain", 0.0),
        -c.features.get("hard_plateau_largest", 0.0),
        c.features.get("sealed_added", 0.0),
        -c.features["y_back"],
    )


def _key_bridge(c):
    # a merge is worth exactly the plateau it creates that did not exist
    return (
        -c.features.get("plateau_gain", 0.0),
        -c.features.get("stability_margin", 0.0),
        c.features.get("sealed_added", 0.0),
        -c.features["y_back"],
    )


def _key_front_wedge(c):
    # use the headroom the step behind it leaves, keep the tread wide, and
    # start from the back of the band so the descent runs door-ward
    return (
        -c.features["top_z"],
        -c.features["footprint"],
        -c.features["y_back"],
    )


def _key_last_resort(c):
    # lie as flat as the space allows, keep to the back, and take the pose that
    # spends the least height on the way
    return (
        c.orientation.dz,
        -c.features["footprint"],
        -c.features["y_back"],
    )


def _key_typed_cap(c):
    # cap the highest terrain first -- that is the space nothing else can use
    # -- and sit flat on it rather than perched
    return (
        -c.features["top_z"],
        -c.features.get("stability_margin", 0.0),
        -c.features["y_back"],
    )


def _key_hole_fill(c):
    # take the most of the pocket, lying as flat as the pocket allows, and
    # among equals the one furthest back
    return (
        -c.features.get("hole_coverage", 0.0),
        c.orientation.dz,
        -c.features["y_back"],
        -c.features["frontier_contact"],
    )


def _key_wedge_bridge(c):
    # reach over the bevel first, then the plateau it lands
    return (
        c.box.minimum[0],
        -c.features.get("plateau_gain", 0.0),
        -c.features.get("stability_margin", 0.0),
    )


ARCHETYPE_KEYS = {
    A_MAX_FOOTPRINT: _key_max_footprint,
    A_BACK_CORNER: _key_back_corner,
    A_MIN_HOLE: _key_min_hole,
    A_LARGEST_RESIDUAL: _key_largest_residual,
    A_SHELF_SAVING: _key_shelf_saving,
    A_SOFT_EDGE: _key_soft_edge,
    A_PRIORITY_EDGE: _key_priority_edge,
    A_SP_CLUSTER: _key_sp_cluster,
    A_ELONGATED_WALL: _key_elongated_wall,
    A_SLOPE_INFILL: _key_slope_infill,
    A_WALL_FRONT: _key_wall_front,
    A_TALL_PERIMETER: _key_tall_perimeter,
    A_WEDGE_STEP: _key_wedge_step,
    A_WEDGE_CAP: _key_wedge_cap,
    A_TERRACE: _key_terrace,
    A_BRIDGE: _key_bridge,
    A_WEDGE_BRIDGE: _key_wedge_bridge,
    A_HOLE_FILL: _key_hole_fill,
    A_TYPED_CAP: _key_typed_cap,
    A_LAST_RESORT: _key_last_resort,
    A_FRONT_WEDGE: _key_front_wedge,
}


def eligible_archetypes(candidate: Candidate, config) -> set:
    tags = set()
    if candidate.surface == "shelf":
        tags.add(A_SHELF_SAVING)
        return tags
    if candidate.role == cls.ROLE_SLOPE_INFILL:
        tags.add(A_SLOPE_INFILL)
        return tags
    if (
        candidate.role == l2.ROLE_HOLE_FILL
        and candidate.features.get("hole_coverage", 0.0)
        >= config.hole_fill_min_coverage
    ):
        # only a placement that actually *plugs* the gap earns the tag.  A small
        # box loose in a large clearing is ordinary floor cargo, and calling it
        # a hole fill would turn the archetype into "anywhere there is room".
        tags.add(A_HOLE_FILL)
    tags.update({A_MAX_FOOTPRINT, A_BACK_CORNER, A_MIN_HOLE, A_LARGEST_RESIDUAL})
    if candidate.role == cls.ROLE_WALL_FRONT:
        tags.add(A_WALL_FRONT)
    if candidate.role == cls.ROLE_TALL_PERIMETER:
        tags.add(A_TALL_PERIMETER)
    if candidate.role == cls.ROLE_WEDGE_STEP:
        tags.add(A_WEDGE_CAP if candidate.profile.is_soft else A_WEDGE_STEP)
    if candidate.role == l2.ROLE_TERRACE:
        tags.add(A_TERRACE)
    if candidate.role == l2.ROLE_BRIDGE:
        tags.add(A_BRIDGE)
    if candidate.role == l2.ROLE_WEDGE_BRIDGE:
        tags.add(A_WEDGE_BRIDGE)
    if candidate.role == l2.ROLE_TYPED_CAP:
        tags.add(A_TYPED_CAP)
    if candidate.role == l2.ROLE_FRONT_WEDGE:
        tags.add(A_FRONT_WEDGE)
    if candidate.role == l2.ROLE_LAST_RESORT:
        # its own rung, at the very bottom of every ladder: it is only ever
        # generated when nothing else was, so it competes with nothing
        tags.add(A_LAST_RESORT)
    if candidate.profile.is_elongated:
        tags.add(A_ELONGATED_WALL)
    klass = candidate.profile.cargo_class
    if klass == cls.SOFT:
        tags.add(A_SOFT_EDGE)
    elif klass == cls.PRIORITY:
        tags.add(A_PRIORITY_EDGE)
    elif klass == cls.SOFT_PRIORITY:
        tags.add(A_SP_CLUSTER)
    return tags


# ---------------------------------------------------------------------------
# Rule ladder
# ---------------------------------------------------------------------------
def archetype_ladder(profile: cls.ItemProfile, board: Board, container_idx: int,
                     config) -> list[str]:
    model = board.model(container_idx)
    klass = profile.cargo_class
    wall_ratio = _wall_height_ratio(board, container_idx, model)

    ladder: list[str] = [A_WEDGE_STEP, A_WEDGE_CAP, A_SLOPE_INFILL]
    if config.hole_fill_enabled and klass == cls.NORMAL_HARD:
        # A pocket the board already has is worth more than a pose that starts
        # a new one, and the tag is only ever offered to a placement that fills
        # most of the gap -- so this is not a licence to go anywhere.  It has to
        # come before the foundation archetypes: put it after them and the
        # highest-footprint candidate somewhere else always wins, which is why
        # the gaps were still there.
        ladder.append(A_HOLE_FILL)
    growth: list[str] = []
    if config.layer2_enabled and klass == cls.NORMAL_HARD:
        # Growth before ground was the original call: a bridge or a terrace
        # turns two supports into one bigger one, which is worth more than
        # another footprint on a floor Layer 1 has already spent.  The
        # alternative is that it outranks every floor archetype from the moment
        # a terrace is possible, and the floor layer is abandoned half-tiled --
        # which is what the official boards look like, five to seven items on
        # a 2.03 m^2 floor.
        growth = [A_BRIDGE, A_WEDGE_BRIDGE, A_TERRACE]
        if not config.ground_before_growth:
            ladder.extend(growth)
            growth = []
    if config.front_wedge_enabled and klass == cls.NORMAL_HARD:
        # the descent to the door is the same kind of move as a terrace -- grow
        # structure from structure -- so it belongs beside them and not at the
        # bottom, where every candidate's max-footprint tag outranks it and it
        # is never chosen at all.
        ladder.append(A_FRONT_WEDGE)
    if klass == cls.NORMAL_HARD:
        if wall_ratio < config.wall_front_target_ratio:
            ladder.append(A_WALL_FRONT)
        if profile.is_elongated:
            ladder.extend([A_ELONGATED_WALL, A_BACK_CORNER, A_MIN_HOLE])
        elif not config.frontier_prefers_lying:
            ladder.extend([
                A_TALL_PERIMETER, A_MAX_FOOTPRINT, A_BACK_CORNER,
                A_MIN_HOLE, A_LARGEST_RESIDUAL,
            ])
        elif board.is_frontier_material(profile):
            # Frontier material builds the skeleton: lay it down, back first
            # and dense.  Standing it up is demoted below every foundation
            # archetype -- a big flat hard box spent as a tall perimeter is the
            # one item that could have made a large connected support and did
            # not.
            ladder.extend([
                A_MAX_FOOTPRINT, A_BACK_CORNER, A_LARGEST_RESIDUAL,
                A_MIN_HOLE, A_TALL_PERIMETER,
            ])
        elif board.is_follower(profile):
            # Followers do not get to decide where the frontier is.  Close a
            # hole, keep the residual rectangle whole, cluster at the back --
            # and only then behave like foundation.
            ladder.extend([
                A_MIN_HOLE, A_LARGEST_RESIDUAL, A_BACK_CORNER,
                A_TALL_PERIMETER, A_MAX_FOOTPRINT,
            ])
        else:
            ladder.extend([
                A_MAX_FOOTPRINT, A_BACK_CORNER, A_MIN_HOLE,
                A_LARGEST_RESIDUAL, A_TALL_PERIMETER,
            ])
        if config.shelf_takes_hard and model.shelves:
            # Opening the shelf to hard cargo left it with no rung of its own:
            # a shelf candidate carries only A_SHELF_SAVING, and that was in
            # the soft ladders alone, so no rung matched, the choice fell
            # through to "fallback" -- survivors[0], whatever the shortlist
            # happened to sort first -- and task 000 stood a box upright on the
            # shelf.  Last, because the floor is still the better home.
            ladder.append(A_SHELF_SAVING)
    elif klass == cls.SOFT:
        ladder.append(A_SHELF_SAVING)
        ladder.append(A_SOFT_EDGE)
        if profile.is_elongated:
            ladder.append(A_ELONGATED_WALL)
        ladder.extend([A_HOLE_FILL, A_MIN_HOLE, A_BACK_CORNER, A_TYPED_CAP])
    elif klass == cls.PRIORITY:
        if model.is_prioritized:
            ladder.extend([
                A_MAX_FOOTPRINT, A_BACK_CORNER, A_HOLE_FILL, A_MIN_HOLE,
                A_TYPED_CAP,
            ])
        else:
            ladder.extend([
                A_PRIORITY_EDGE, A_HOLE_FILL, A_MIN_HOLE, A_BACK_CORNER,
                A_TYPED_CAP,
            ])
    else:  # soft + priority
        ladder.append(A_SHELF_SAVING)
        ladder.extend([
            A_SP_CLUSTER, A_PRIORITY_EDGE, A_HOLE_FILL, A_MIN_HOLE,
            A_BACK_CORNER, A_TYPED_CAP,
        ])
    ladder.extend(growth)
    ladder.append(A_MAX_FOOTPRINT)
    ladder.append(A_LAST_RESORT)
    seen, out = set(), []
    for name in ladder:
        if name not in seen:
            seen.add(name)
            out.append(name)
    return out


# ---------------------------------------------------------------------------
# Layer 2 candidate generation
# ---------------------------------------------------------------------------
def generate_layer2_candidates(board: "Board", profile: cls.ItemProfile,
                               container_idx: int, orientation: cls.Orientation,
                               config) -> list[Candidate]:
    """Terrace extensions, plateau merges and wedge bridges, on hard tops.

    Kept apart from ``generate_candidates`` because these are *proposals of a
    different kind*, and mixing them into one list is what lets a single
    depth-sorted shortlist quietly delete a whole behaviour.
    """
    if not config.layer2_enabled:
        return []
    typed = profile.cargo_class != cls.NORMAL_HARD
    if typed and not config.typed_cap_enabled:
        return []

    model = board.model(container_idx)
    container = board.container(container_idx)
    dx, dy, dz = orientation.dx, orientation.dy, orientation.dz
    gap = config.settled_clearance
    tops = l2.hard_tops(container, model, config)
    if not tops:
        return []

    proposals: list[tuple[str, str, float, float, float]] = []

    if typed:
        # Soft and priority on top of hard.  Layer 2 was normal-hard only, so
        # typed cargo could never rest on cargo at all -- which is backwards
        # near the ceiling, where the last usable space is a lid and the class
        # that wants a lid is the one that has to support nothing above it.
        # Only the top of the terrain, so it caps rather than buries.
        for rect, top in tops:
            if top + dz > model.z_ceiling:
                continue
            if top < model.z_floor + config.typed_cap_min_height:
                continue  # low down there is still floor to use
            for x, y in l2.terrace_anchors(rect, dx, dy, gap):
                proposals.append(
                    (l2.FAMILY_TYPED_CAP, l2.ROLE_TYPED_CAP, x, y, top)
                )
        return _build_layer2(
            board, profile, container_idx, orientation, proposals, config
        )

    # A terrace sits on *one* top, so it uses that top's own height.  Grouping
    # first and building at the group's level would float the box above every
    # member but the tallest, which is how the first version of this quietly
    # lost most of its candidates.
    for rect, top in tops:
        if top + dz > model.z_ceiling:
            continue
        for x, y in l2.terrace_anchors(rect, dx, dy, gap):
            proposals.append((l2.FAMILY_TERRACE, l2.ROLE_TERRACE, x, y, top))

    # A bridge spans two, so it needs the pairing -- and rests on the higher.
    for level, members in l2.level_groups(
        tops, config.layer2_bridge_level_tolerance
    ):
        if level + dz > model.z_ceiling:
            continue
        for x, y in l2.bridge_anchors(members, dx, dy):
            proposals.append((l2.FAMILY_BRIDGE, l2.ROLE_BRIDGE, x, y, level))
        for x, y in l2.wedge_bridge_anchors(members, model, level, dx, dy, config):
            proposals.append(
                (l2.FAMILY_WEDGE_BRIDGE, l2.ROLE_WEDGE_BRIDGE, x, y, level)
            )

    return _build_layer2(
        board, profile, container_idx, orientation, proposals, config
    )


def _build_layer2(board: "Board", profile: cls.ItemProfile, container_idx: int,
                  orientation: cls.Orientation, proposals, config
                  ) -> list[Candidate]:
    """Turn (family, role, x, y, bottom) proposals into validated candidates."""
    model = board.model(container_idx)
    container = board.container(container_idx)
    dx, dy, dz = orientation.dx, orientation.dy, orientation.dz
    candidates: list[Candidate] = []
    seen = set()
    for family, role, x, y, bottom in proposals:
        key = (round(x, 4), round(y, 4), round(bottom, 4), orientation.index, family)
        if key in seen:
            continue
        seen.add(key)
        box = AABB(
            (float(x), float(y), float(bottom) + dz / 2.0), (dx, dy, dz), "candidate"
        )
        ok, _why = validate(box, model, container, config)
        if not ok:
            continue
        candidates.append(
            Candidate(
                box=box, profile=profile, orientation=orientation,
                container_idx=container_idx, surface="item",
                surface_name="hard-top", role=role, family=family,
            )
        )
        if len(candidates) >= config.max_candidates_per_orientation:
            break
    return candidates


# ---------------------------------------------------------------------------
# What may be built on: the shape of the support, not how far up it is
# ---------------------------------------------------------------------------
def _hole_depth_ok(board: "Board", container_idx: int, box: AABB, config) -> bool:
    """The depth rule, asked before a hole-fill candidate is even built.

    Charging a refusal to the family's quota and deleting it in the veto later
    spent the whole quota on placements that could not happen -- which is what
    it did, and no floor hole was ever reached.
    """
    container = board.container(container_idx)
    level = stack_level(
        box, container, l2.ROLE_HOLE_FILL, config, board.model(container_idx)
    )
    if level <= config.layer2_free_depth:
        return True
    if level > config.layer2_max_layers:
        return False
    area, coverage = plateau_support(board, container_idx, box, config)
    return plateau_is_enough(area, coverage, box, config)


def plateau_is_enough(area: float, coverage: float, box: AABB, config) -> bool:
    """Is this a terrace to build on, or one box's lid?

    The absolute floor answers "wide enough to be a plateau at all".  The
    multiple, when set, answers the question that actually matters and that an
    area cannot answer on its own -- is there more than one box under you --
    because a single lid is a plateau of exactly that box's footprint, and the
    footprints in a real manifest span a factor of six.
    """
    required = config.plateau_support_min_area
    if config.plateau_support_footprint_multiple > 0.0:
        footprint = float(box.size[0]) * float(box.size[1])
        required = max(
            required, config.plateau_support_footprint_multiple * footprint
        )
    return area >= required and coverage >= config.plateau_support_coverage


def plateau_support(board: "Board", container_idx: int, box: AABB,
                    config) -> tuple[float, float]:
    """``(plateau area under this box, share of its footprint on that plateau)``.

    A depth counter cannot tell a terrace from a tower: both are "three boxes
    up".  What separates them is the *shape* of what is being built on -- a
    terrace's top is a wide connected plateau, a tower's is one box lid -- and
    that is a property the height map already carries.
    """
    grid = board.grid(container_idx)
    labels, count = board.plateau_labels(container_idx)
    if count == 0:
        return 0.0, 0.0
    rect = box_rect(box)
    mask = grid.rect_mask(rect)
    cells = int(mask.sum())
    if cells == 0:
        return 0.0, 0.0
    bottom = float(box.minimum[2])
    resting = mask & (np.abs(grid.height - bottom) <= config.contact_tolerance)
    under = labels[resting]
    under = under[under > 0]
    if under.size == 0:
        return 0.0, 0.0
    label = int(np.bincount(under).argmax())
    area = float((labels == label).sum()) * grid.cell_area
    coverage = float((resting & (labels == label)).sum()) / float(cells)
    return area, coverage


def may_build_here(board: "Board", container_idx: int, candidate: "Candidate",
                   config) -> tuple[bool, int]:
    """May this placement stand where it is, given how deep and on what?

    Below ``layer2_free_depth`` nothing has to be justified: the first storey
    above the floor is ordinary Layer 2.  Above it the support has to be a
    plateau -- wide enough, and enough of the box's underside actually on it.
    A tower cannot satisfy that on its own lid, so it stops; a terrace can, so
    it keeps growing sideways *and* upwards.  That is the same "grow hard
    support from hard support" rule as the rest of Layer 2, used as the
    criterion for depth instead of as a separate behaviour.
    """
    container = board.container(container_idx)
    level = stack_level(
        candidate.box, container, candidate.role, config,
        board.model(container_idx),
    )
    if level <= config.layer2_free_depth:
        return True, level
    if level > config.layer2_max_layers:
        return False, level  # backstop, so nothing can run away
    area, coverage = plateau_support(
        board, container_idx, candidate.box, config
    )
    return plateau_is_enough(area, coverage, candidate.box, config), level


# ---------------------------------------------------------------------------
# Hole filling: aim at the gap, then pick the pose that fits it
# ---------------------------------------------------------------------------
def generate_hole_candidates(board: "Board", profile: cls.ItemProfile,
                             container_idx: int, config) -> list[Candidate]:
    """Candidates seated inside a pocket one layer could not close.

    Generated over *all* the item's orientations at once, which is the whole
    point: the pose has to be chosen against the shape of the hole, and the
    per-orientation loops elsewhere have already committed to a pose before
    they ever look at the board.  For each pocket only the flattest tier of
    poses that fits is offered, so the box is laid down wherever lying down
    works and stood up only where nothing else goes in.
    """
    if not config.hole_fill_enabled:
        return []

    model = board.model(container_idx)
    container = board.container(container_idx)
    gap = config.settled_clearance
    holes = board.holes(container_idx)
    if not holes:
        return []

    orientations = list(profile.orientations)
    candidates: list[Candidate] = []
    seen = set()
    for hole in holes:
        if not hole.on_floor and not config.layer2_enabled:
            continue
        for orientation in l2.flattest_fitting_tier(
            hole, orientations, gap, config
        ):
            dx, dy, dz = orientation.dx, orientation.dy, orientation.dz
            if hole.bottom_z + dz > model.z_ceiling:
                continue
            coverage = min(1.0, orientation.footprint / max(1e-9, hole.rect.area))
            for x, y in l2.hole_anchors(hole, dx, dy, gap):
                key = (round(x, 4), round(y, 4), round(hole.bottom_z, 4),
                       orientation.index)
                if key in seen:
                    continue
                seen.add(key)
                box = AABB(
                    (float(x), float(y), float(hole.bottom_z) + dz / 2.0),
                    (dx, dy, dz), "candidate",
                )
                ok, _why = validate(box, model, container, config)
                if not ok:
                    continue
                if not hole.on_floor and config.layer2_max_layers > 0 and not (
                    _hole_depth_ok(board, container_idx, box, config)
                ):
                    # A notch high in the terrain is a real pocket and the cap
                    # still refuses to fill it.  Charging it to the family's
                    # quota here and letting the veto delete it later spends the
                    # whole quota on placements that cannot happen -- which is
                    # exactly what it did: every tagged candidate on the first
                    # board died at the cap, and no floor hole was ever reached.
                    continue
                candidate = Candidate(
                    box=box, profile=profile, orientation=orientation,
                    container_idx=container_idx,
                    surface="floor" if hole.on_floor else "item",
                    surface_name="hole" if hole.on_floor else "hard-top",
                    role=l2.ROLE_HOLE_FILL, family=l2.FAMILY_HOLE_FILL,
                )
                candidate.features["hole_coverage"] = coverage
                candidate.features["hole_area"] = hole.area
                candidate.features["hole_rect_area"] = hole.rect.area
                candidates.append(candidate)
                if len(candidates) >= config.max_candidates_per_orientation:
                    return candidates
    return candidates


# ---------------------------------------------------------------------------
# The front staircase: descend to the opening instead of walling it
# ---------------------------------------------------------------------------
def generate_front_wedge_candidates(board: "Board", profile: cls.ItemProfile,
                                    container_idx: int, config
                                    ) -> list[Candidate]:
    """Step down towards the opening once the back has been built up.

    ``front_stays_low`` says what the front may not do.  This says what it
    should: put a box on the ground in front of the frontier whose own top
    stays under the terrain behind it, so the surface descends to the door in
    steps instead of ending in a wall.  Every such box is reachable over the
    one behind it, and so is everything already placed, which is the property
    the whole front band exists to protect.

    Gated on the same condition as the front release, because while the back is
    still the cheaper place to build there is nothing to descend *from*.
    """
    if not config.front_wedge_enabled:
        return []
    if not board.front_is_released(container_idx):
        return []

    model = board.model(container_idx)
    container = board.container(container_idx)
    grid = board.grid(container_idx)
    gap = config.settled_clearance
    candidates: list[Candidate] = []
    seen = set()
    for rect, level_z, behind in l2.front_steps(grid, model, config):
        head = behind - level_z - config.front_wedge_min_drop
        if head <= 0.0:
            continue
        width = rect.x_max - rect.x_min
        depth = rect.y_max - rect.y_min
        fitting = [
            o for o in profile.orientations
            if l2.fits_with_clearance(width, depth, o.dx, o.dy, gap)
            and o.dz <= head + 1e-9
        ]
        if not fitting:
            continue
        # the tallest pose that still stays under the step behind it: a step
        # should use the headroom it has, not sit as low as it can
        fitting.sort(key=lambda o: (-o.dz, -o.footprint))
        for orientation in fitting[: config.front_wedge_poses]:
            dx, dy, dz = orientation.dx, orientation.dy, orientation.dz
            # a full gap on each side: the clearance the validator wants is
            # from each neighbour, and the patch's edges are where they are
            left, right = rect.x_min + dx / 2.0 + gap, rect.x_max - dx / 2.0 - gap
            front, back = rect.y_min + dy / 2.0 + gap, rect.y_max - dy / 2.0 - gap
            if right < left or back < front:
                continue
            for x, y in (
                (0.5 * (left + right), back), (right, back), (left, back),
                (0.5 * (left + right), 0.5 * (front + back)),
            ):
                key = (round(x, 4), round(y, 4), round(level_z, 4),
                       orientation.index)
                if key in seen:
                    continue
                seen.add(key)
                box = AABB(
                    (float(x), float(y), float(level_z) + dz / 2.0),
                    (dx, dy, dz), "candidate",
                )
                ok, _why = validate(box, model, container, config)
                if not ok:
                    continue
                on_floor = abs(level_z - model.z_floor) <= config.contact_tolerance
                if not on_floor and config.layer2_max_layers > 0:
                    allowed = stack_level(
                        box, container, l2.ROLE_FRONT_WEDGE, config, model
                    ) <= config.layer2_max_layers
                    if not allowed:
                        continue
                candidates.append(
                    Candidate(
                        box=box, profile=profile, orientation=orientation,
                        container_idx=container_idx,
                        surface="floor" if on_floor else "item",
                        surface_name="front-step",
                        role=l2.ROLE_FRONT_WEDGE,
                        family=l2.FAMILY_FRONT_WEDGE,
                    )
                )
                if len(candidates) >= config.max_candidates_per_orientation:
                    return candidates
    return candidates


# ---------------------------------------------------------------------------
# Last resort: somewhere it genuinely fits
# ---------------------------------------------------------------------------
def generate_last_resort_candidates(board: "Board", profile: cls.ItemProfile,
                                    container_idx: int, config
                                    ) -> list[Candidate]:
    """Seat the box in the largest empty rectangle, whatever pose that takes.

    Run only when every ordinary generator came back empty.  That case is not
    "the container is full": on task 000 the run stopped with 0.968 m^2 of bare
    floor and a clear 1.16 x 0.56 rectangle at the front, in which two of the
    item's six poses fitted.  Nothing proposed them.  Every anchor elsewhere is
    derived from the edge of something already packed or from a zone line, so
    on a fragmented board the anchors need not land anywhere the box fits, and
    the hole finder refuses rectangles this large by design.

    Flattest tier first, as everywhere else, so an upright pose is used only
    where nothing lying down goes in -- which, being the last resort, is
    exactly when standing it up beats not shipping it.
    """
    if not config.last_resort_enabled:
        return []
    model = board.model(container_idx)
    container = board.container(container_idx)
    grid = board.grid(container_idx)
    gap = config.settled_clearance
    candidates: list[Candidate] = []
    seen = set()
    for rect, level_z in l2.free_rectangles(grid, model, config):
        width = rect.x_max - rect.x_min
        depth = rect.y_max - rect.y_min
        fitting = [
            o for o in profile.orientations
            if l2.fits_with_clearance(width, depth, o.dx, o.dy, gap)
            and level_z + o.dz <= model.z_ceiling
        ]
        if not fitting:
            continue
        flattest = min(o.dz for o in fitting)
        tier = sorted(
            (o for o in fitting
             if o.dz <= flattest + config.hole_fill_tier_tolerance),
            key=lambda o: -o.footprint,
        )
        for orientation in tier:
            dx, dy, dz = orientation.dx, orientation.dy, orientation.dz
            # a full gap on each side: the clearance the validator wants is
            # from each neighbour, and the patch's edges are where they are
            left, right = rect.x_min + dx / 2.0 + gap, rect.x_max - dx / 2.0 - gap
            front, back = rect.y_min + dy / 2.0 + gap, rect.y_max - dy / 2.0 - gap
            if right < left or back < front:
                continue
            for x, y in (
                (right, back), (left, back), (right, front), (left, front),
                (0.5 * (left + right), back),
                (0.5 * (left + right), 0.5 * (front + back)),
            ):
                key = (round(x, 4), round(y, 4), round(level_z, 4),
                       orientation.index)
                if key in seen:
                    continue
                seen.add(key)
                box = AABB(
                    (float(x), float(y), float(level_z) + dz / 2.0),
                    (dx, dy, dz), "candidate",
                )
                ok, _why = validate(box, model, container, config)
                if not ok:
                    continue
                on_floor = abs(level_z - model.z_floor) <= config.contact_tolerance
                if not on_floor and config.layer2_max_layers > 0:
                    level = stack_level(
                        box, container, l2.ROLE_LAST_RESORT, config, model
                    )
                    if level > config.layer2_max_layers:
                        continue
                candidates.append(
                    Candidate(
                        box=box, profile=profile, orientation=orientation,
                        container_idx=container_idx,
                        surface="floor" if on_floor else "item",
                        surface_name="free-rectangle",
                        role=l2.ROLE_LAST_RESORT,
                        family=l2.FAMILY_LAST_RESORT,
                    )
                )
                if len(candidates) >= config.max_candidates_per_orientation:
                    return candidates
    return candidates


# ---------------------------------------------------------------------------
# Vetoes
# ---------------------------------------------------------------------------
def apply_vetoes(candidates: list[Candidate], board: Board, container_idx: int,
                 config) -> tuple[list[Candidate], dict]:
    model = board.model(container_idx)
    grid = board.grid(container_idx)
    coverage = grid.coverage()
    counts: dict[str, int] = {}

    def drop(candidate, reason):
        candidate.vetoes.append(reason)
        counts[reason] = counts.get(reason, 0) + 1

    survivors = list(candidates)

    # 0. floor poses stay flat.  No fallback: an item that only fits standing on
    #    end in the middle of the foundation is a Layer 2 item, not a Layer 1
    #    one, and forcing it in is exactly how a flat floor gets ruined.
    kept = []
    for candidate in survivors:
        if (
            candidate.surface == "floor"
            and candidate.role == cls.ROLE_NONE
            and not (candidate.profile.is_elongated and not candidate.profile.is_soft)
            and candidate.features["footprint"]
            < config.min_floor_footprint_fraction * candidate.profile.max_footprint - 1e-9
        ):
            drop(candidate, "low-footprint-pose")
        else:
            kept.append(candidate)
    survivors = kept
    if not survivors:
        return [], counts

    # 1. the way in, priced instead of scheduled.  The old rule protected the
    #    corridor until floor coverage passed a fixed threshold and then let go
    #    of it all at once, which is what left empty floor behind a wall.  What
    #    actually matters is not where the box is but what it seals off: a
    #    placement is refused when it strands still-reachable floor, or when it
    #    stands higher than the terrain behind it.  Early on that protects the
    #    corridor by itself, because blocking a column of an empty board
    #    strands the whole column; late on it releases the corridor by itself,
    #    because there is nothing left behind to strand.  No threshold has to
    #    name the moment.
    if coverage < config.corridor_release_fill:
        kept = []
        for candidate in survivors:
            if (
                candidate.surface == "floor"
                and candidate.role != l2.ROLE_LAST_RESORT
                and candidate.features["corridor_overlap"] > 1e-4
            ):
                drop(candidate, "corridor")
            else:
                kept.append(candidate)
        if kept:
            survivors = kept

    kept = []
    for candidate in survivors:
        if candidate.surface != "floor":
            kept.append(candidate)
            continue
        if candidate.features.get("stranded_added", 0.0) > config.stranded_veto_area:
            drop(candidate, "strands-reachable-floor")
        elif candidate.features.get("sealed_added", 0.0) > config.sealed_veto_area:
            drop(candidate, "seals-usable-ground-behind")
        else:
            kept.append(candidate)
    if kept:
        survivors = kept

    # 2. reserved edge zones.  No fallback: the soft and priority strips belong
    #    to constrained cargo for the whole of Layer 1.  Letting plain hard
    #    cargo spill into them "because nothing else fits" is exactly what
    #    starves the constrained classes, and the cost of the reservation is
    #    something a human should be able to see in the picture.
    kept = []
    for candidate in survivors:
        profile = candidate.profile
        if (
            candidate.surface == "floor"
            and profile.cargo_class == cls.NORMAL_HARD
            and not model.is_prioritized
            and max(
                candidate.features["soft_zone_fit"],
                candidate.features["priority_zone_fit"],
            )
            > config.zone_guard_fraction
            and candidate.role not in (cls.ROLE_WALL_FRONT, l2.ROLE_LAST_RESORT)
        ):
            # The last resort is exempt, and only it.  Holding the typed strips
            # against ordinary hard cargo is right while hard has anywhere else
            # to go -- that is the whole point of the reservation -- but a
            # last-resort candidate exists only because nothing else did, and
            # with the official `max_space: 1` refusing it does not cost the
            # strip, it ends the episode.
            drop(candidate, "reserved-zone")
        else:
            kept.append(candidate)
    survivors = kept
    if not survivors:
        return [], counts

    # 2b. the slope strip belongs to wall material, and while the wedge is not
    #     CLOSED it belongs to staircase material.  Putting ordinary cargo at
    #     the chamfer foot is irreversible: nothing can climb past it after,
    #     so the whole wedge above is gone for the episode.
    wedge_state = board.triangle_state(container_idx)
    reserving = wedge_state.state != tri.STATE_CLOSED
    if reserving or _wall_front_wanted(board, container_idx, model, config):
        kept = []
        for candidate in survivors:
            if candidate.surface != "floor":
                kept.append(candidate)
                continue
            if candidate.features.get("wall_strip_fit", 0.0) <= config.zone_guard_fraction:
                kept.append(candidate)
                continue
            if candidate.role == cls.ROLE_WALL_FRONT:
                kept.append(candidate)
                continue
            if reserving and tri.strip_reserved_for(
                candidate.profile, wedge_state, model, config
            ):
                kept.append(candidate)
                continue
            drop(candidate, "wedge-reserve" if reserving else "wall-front-strip")
        if kept:
            survivors = kept

    # 3. interior holes
    kept = [
        c for c in survivors
        if c.features.get("new_interior_hole_area", 0.0) <= config.max_new_interior_hole
    ]
    if kept and len(kept) < len(survivors):
        for candidate in survivors:
            if candidate not in kept:
                drop(candidate, "interior-hole")
        survivors = kept

    # 3b. a shelf placement has to be on the shelf.  The support polygon lets
    #     a box hang out to half its width, and on the small shelf -- 0.44 m
    #     wide, narrower than most cargo -- it did: 15 of 52 shelf placements
    #     overhung the edge, one by 0.486 m.  Those stay up, but they cap the
    #     open floor beneath them at shelf height, and that floor is where tall
    #     cargo has to go, because the main shelf already caps the back half at
    #     0.765 m.  No fallback is needed: the same item has floor candidates
    #     in the same pool, so refusing the overhang does not strand it.
    if config.shelf_min_support_fraction > 0.0:
        shelf_rects = [
            (Rect(float(sh.minimum[0]), float(sh.maximum[0]),
                  float(sh.minimum[1]), float(sh.maximum[1])),
             float(sh.maximum[2]))
            for sh in model.shelves
        ]
        kept = []
        for candidate in survivors:
            if candidate.surface != "shelf" or not shelf_rects:
                kept.append(candidate)
                continue
            bottom = float(candidate.box.minimum[2])
            rect = box_rect(candidate.box)
            # union, not sum: the two shelves overlap in a 0.2838 m^2 band and
            # summing counted that band twice, so a box straddling it could
            # score over 100% supported while hanging off the front edge
            on = union_area([
                Rect(max(r.x_min, rect.x_min), min(r.x_max, rect.x_max),
                     max(r.y_min, rect.y_min), min(r.y_max, rect.y_max))
                for r, top in shelf_rects
                if abs(top - bottom) <= config.contact_tolerance
            ])
            if on >= config.shelf_min_support_fraction * rect.area - 1e-9:
                kept.append(candidate)
            else:
                drop(candidate, "overhangs-the-shelf")
        survivors = kept
        if not survivors:
            return [], counts

    # 4. tip-over risk: a tall pose needs a wall or a backing item
    kept = []
    for candidate in survivors:
        ratio = candidate.orientation.tipping_ratio
        if ratio >= config.max_freestanding_ratio and not candidate.features["has_backing"]:
            drop(candidate, "free-standing-tipping-risk")
        else:
            kept.append(candidate)
    if kept:
        survivors = kept

    # 4b. height in the wedge approach.  Scoped to that band on purpose: tall
    #     cargo on the right perimeter or against the back wall is still wanted,
    #     because nothing is delivered through those columns afterwards.  Here
    #     it is, so a tall box buys one item's volume and pays with access to
    #     everything wedge-side behind and above it.
    kept = []
    for candidate in survivors:
        if candidate.surface == "floor" and blocks_wedge_approach(
            candidate.box, model, candidate.role, config
        ):
            drop(candidate, "blocks-wedge-approach")
        else:
            kept.append(candidate)
    if kept:
        survivors = kept

    # 4c. typed cargo that reaches the floor goes to the right front, as a
    #     principle rather than a tie-break.  The zone rect and the ranking key
    #     were both tried on their own and moved nothing: half of it landed
    #     elsewhere either way, because by the time a key runs the shortlist
    #     has already chosen which candidates exist.  So refuse the others
    #     outright while a right-front placement is available.
    if config.typed_floor_right_front:
        typed = [
            c for c in survivors
            if c.surface == "floor"
            and (c.profile.is_soft or c.profile.is_prioritized)
        ]
        if typed:
            best = min(c.features.get("front_right_cost", 9.9) for c in typed)
            kept = [
                c for c in survivors
                if c.surface != "floor"
                or not (c.profile.is_soft or c.profile.is_prioritized)
                or c.features.get("front_right_cost", 9.9)
                <= best + config.typed_front_right_slack
            ]
            if kept and len(kept) < len(survivors):
                for candidate in survivors:
                    if candidate not in kept:
                        drop(candidate, "not-right-front")
                survivors = kept

    # 4g. the front is open, on one condition: stay low.
    #     Yielding the whole front band was the wrong shape of rule.  The
    #     opening is wide, so the front is not scarce as *space* -- what makes
    #     it precious is the sight line down each column, and only a box that
    #     stands taller than what is behind it spends that.  So the band stops
    #     being a no-go area and becomes a height limit: a hard box may sit at
    #     the front for as long as it stays under the terrain behind it in its
    #     own columns.  On an empty column that terrain is the floor, which is
    #     how back-first survives the change without a second rule.
    if config.front_stays_low and not board.front_is_released(container_idx):
        front_limit = model.floor_rect.y_min + config.hard_front_band
        kept = []
        for candidate in survivors:
            if (
                candidate.surface != "floor"
                or candidate.profile.cargo_class != cls.NORMAL_HARD
                or candidate.role in (cls.ROLE_WALL_FRONT, cls.ROLE_WEDGE_STEP)
                or candidate.box.center[1] >= front_limit
                or float(candidate.box.maximum[2])
                <= candidate.features.get("terrain_behind", model.z_floor)
                + config.front_height_slack + 1e-9
            ):
                kept.append(candidate)
            else:
                drop(candidate, "front-would-stand-too-tall")
        if kept and len(kept) < len(survivors):
            survivors = kept

    # 4d. hard yields the front band.  Superseded by 4g and off by default;
    #     kept switchable so the two can be compared.  The right front is where
    #     typed cargo lands when the shelf overflows and the front centre is the
    #     way in; hard is the class with somewhere else to be, because it grows
    #     from the back.
    if config.hard_avoids_front:
        floor_rect = model.floor_rect
        front_limit = floor_rect.y_min + config.hard_front_band
        kept = [
            c for c in survivors
            if c.surface != "floor"
            or c.profile.cargo_class != cls.NORMAL_HARD
            or c.role in (cls.ROLE_WALL_FRONT, cls.ROLE_WEDGE_STEP)
            or c.box.center[1] >= front_limit
        ]
        if kept and len(kept) < len(survivors):
            for candidate in survivors:
                if candidate not in kept:
                    drop(candidate, "hard-yields-the-front")
            survivors = kept

    # 4i. do not perch a box on something much narrower than itself.
    #     Task 000 balanced a 0.55 m terrace on a 0.24 m upright column,
    #     overhanging both sides, at depth 2 -- where the depth rule asks
    #     nothing, because what is wrong there is not the height but the width
    #     of what it stands on.  A preference, not a refusal: as a refusal it
    #     cost both tasks placements at every threshold tried, 0.40 through
    #     0.70, and on task 001 at 0.70 it made the front taller than the back.
    #     With a fallback it can only choose better when there is better.
    if config.support_coverage_at_any_depth:
        kept = []
        for candidate in survivors:
            if candidate.surface != "item":
                kept.append(candidate)
                continue
            _area, coverage = plateau_support(
                board, container_idx, candidate.box, config
            )
            if coverage >= config.perch_min_coverage:
                kept.append(candidate)
            else:
                drop(candidate, "perched-on-something-narrow")
        if kept:
            survivors = kept

    # 4h. a bridge may not seal floor that is still worth having.
    #     On task 000 the fifth placement bridged the 0.371 m gap between the
    #     first and third, at 0.28 m above a floor that was still bare -- and
    #     from then on that floor could not be reached at all.  A merge is
    #     worth making over ground that is already spent or unreachable; over
    #     ground a later box could still use, it is a lid.
    if config.bridge_keeps_floor:
        kept = []
        for candidate in survivors:
            if candidate.role != l2.ROLE_BRIDGE:
                kept.append(candidate)
                continue
            mask = grid.rect_mask(box_rect(candidate.box))
            free_under = float(
                (mask & grid.usable & ~grid.occupied).sum()
            ) * grid.cell_area
            if free_under > config.bridge_max_sealed_floor:
                drop(candidate, "bridge-would-seal-floor")
            else:
                kept.append(candidate)
        if kept:
            survivors = kept

    # 4f. nothing may cap the staircase without climbing it.  A terrace is
    #     proposed flush with an existing hard top, and nothing in that
    #     proposal knows the chamfer is over to its left -- so on the shipped
    #     boards a terrace repeatedly landed on the top step and sat *back*
    #     from the reach that step had won (x=-0.495 on a step that had got to
    #     -0.655), sealing the climb under a box that gained nothing.  While
    #     the zone is still growing, a placement resting on the strip has to
    #     advance it.  Soft, and the rest of the cap ladder, are exempt: taking
    #     the top is what they are being held for.
    if config.wedge_top_must_advance:
        state = board.triangle_state(container_idx)
        if state.state in (tri.STATE_RAW, tri.STATE_STAIRCASE):
            kept = []
            for candidate in survivors:
                if (
                    candidate.surface == "item"
                    and candidate.role not in (
                        cls.ROLE_WEDGE_STEP, cls.ROLE_SLOPE_INFILL
                    )
                    and tri.in_strip(candidate.box, model, config)
                    and not tri.cap_allows(candidate.profile, state, config)
                    and float(candidate.box.minimum[0])
                    > state.left_reach - config.wedge_min_step_gain
                ):
                    drop(candidate, "caps-the-staircase")
                else:
                    kept.append(candidate)
            # a fallback: refusing the item outright is worse than one flat
            # top, and the zone closes on its own soon enough
            if kept:
                survivors = kept

    # 4e. what may be built on.  Not "how many layers up" -- a counter cannot
    #     tell a terrace from a tower, and raising it from two to three bought
    #     twenty placements while the second layer stayed put at thirty-one and
    #     a tall box ended up standing free on a stack of its own making.  The
    #     condition is on the *shape* of the support: past the free depth, the
    #     box has to land on a plateau wide enough to be one, with enough of
    #     its underside actually on it.  A tower's own lid cannot satisfy that,
    #     so it stops; a terrace can, so it keeps growing.  The wedge staircase
    #     is exempt either way: it is a ramp, not a stack.
    if config.layer2_max_layers > 0:
        kept = []
        for candidate in survivors:
            if candidate.role in (cls.ROLE_WEDGE_STEP, cls.ROLE_SLOPE_INFILL):
                kept.append(candidate)  # the ramp grows as far as it can
                continue
            if candidate.surface != "item":
                kept.append(candidate)
                continue
            allowed, level = may_build_here(
                board, container_idx, candidate, config
            )
            if candidate.role == l2.ROLE_LAST_RESORT:
                # The plateau condition is a preference about *shape*: build on
                # a terrace, not on a lid.  It is the right preference and it
                # has no fallback on purpose.  But a last-resort candidate is
                # generated only when nothing else was possible at all, and
                # with `max_space: 1` refusing it ends the episode -- so for it
                # the structural backstop is the whole rule.  Task 000 stopped
                # at seven items with 1.41 m^2 of bare floor because the
                # corridor veto held the one big opening and this rule deleted
                # everything else.
                allowed = level <= config.layer2_max_layers
            if allowed:
                kept.append(candidate)
            else:
                drop(
                    candidate,
                    "too-many-layers" if level > config.layer2_max_layers
                    else "no-plateau-to-build-on",
                )
        # No fallback.  Every other veto here yields when it would leave
        # nothing, because refusing an item outright is usually worse than a
        # compromised placement.  This one is a structural limit, not a
        # preference: a third layer is a third layer however badly the board
        # wants one, and letting it through when nothing else fits is exactly
        # how the cap silently stopped applying.
        survivors = kept
        if not survivors:
            # the only structural veto with no fallback, so it is also the only
            # one that can empty the list; everything after here assumes it is
            # looking at at least one candidate
            return [], counts

    # 5. a follower may not break the last bay the frontier cargo still needs.
    #    The manifest is given to optimize(), so the outstanding large
    #    footprints are known; this is not a peek at arrival order.
    if config.small_hard_fit_guard and board.is_follower(survivors[0].profile):
        kept = [c for c in survivors if c.features.get("large_fit_kept", True)]
        if kept and len(kept) < len(survivors):
            for candidate in survivors:
                if candidate not in kept:
                    drop(candidate, "breaks-frontier-bay")
            survivors = kept

    # 6. back-first, as a principle rather than a tie-break.  While a *good*
    #    legal placement remains further in, a candidate nearer the opening is
    #    refused outright -- it is not merely ranked below.  "Good" excludes a
    #    deep placement that only got there by opening a hole in front of
    #    itself, which is how "deepest wins" degenerates into corner-stuffing.
    #
    #    Structural roles are exempt because their depth is dictated by
    #    something other than the frontier: the wall front has to stand on the
    #    chamfer foot for the full depth, and a wedge step's position is fixed
    #    by the step underneath it.
    exempt = (cls.ROLE_WALL_FRONT, cls.ROLE_WEDGE_STEP, cls.ROLE_SLOPE_INFILL)
    good = [
        c for c in survivors
        if c.surface == "floor"
        and c.role not in exempt
        and c.features.get("new_interior_hole_area", 0.0)
        <= config.back_first_hole_tolerance
        and c.features.get("stranded_added", 0.0) <= config.stranded_veto_area
    ]
    if good:
        frontier = max(c.features["y_back"] for c in good)
        limit = frontier - config.back_first_slack
        kept = [
            c for c in survivors
            if c.surface != "floor"
            or c.role in exempt
            or c.features["y_back"] >= limit - 1e-9
        ]
        if kept and len(kept) < len(survivors):
            for candidate in survivors:
                if candidate not in kept:
                    drop(candidate, "not-back-first")
            survivors = kept

    return survivors, counts


def compact_backwards(box: AABB, board: Board, container_idx: int, role: str,
                      config) -> AABB:
    """Push a chosen box as far in as it will legally go, then sideways.

    Candidate x/y anchors are enumerated from a fixed list, so a box often
    lands a few centimetres short of what is legal simply because no anchor sat
    there.  That slack is worth nothing to anybody: it is gap between the item
    and whatever is behind it.

    Two rules make this safe rather than merely tighter.  Compaction must not
    strand reachable floor -- pushing back is normally the *opposite* of
    stranding, but a box slid behind a gap can seal it -- and only a wall or
    perimeter role is pushed sideways, because moving ordinary foundation
    against a wall is how the centre gets hollowed out.
    """
    model = board.model(container_idx)
    container = board.container(container_idx)
    grid = board.grid(container_idx)
    _reach_before, stranded_before = board.floor_reach(container_idx)

    # a tall pose is only legal because something is behind it, and `validate`
    # does not know that -- the tipping rule is a veto, not part of validation.
    # Sliding such a box away from its backing is exactly what compaction would
    # otherwise do, and did: a box at R=2.19 ended up standing free.
    ratio = float(box.size[2]) / max(1e-9, min(float(box.size[0]),
                                               float(box.size[1])))
    # Unconditional: a tall pose must be backed *after* the move.  Requiring
    # only that it keep backing it already had lets a box that slipped through
    # the tipping veto's fallback be slid further out; requiring it outright
    # simply forbids the slide in that case, which is no worse than not
    # compacting.
    needs_backing = ratio >= config.max_freestanding_ratio

    def acceptable(candidate: AABB) -> bool:
        ok, _why = validate(candidate, model, container, config)
        if not ok:
            return False
        if needs_backing and not _has_backing(candidate, model, container, config):
            return False
        _reach, stranded = floor_reach(
            grid, model.z_floor, grid.rect_mask(box_rect(candidate))
        )
        return stranded <= stranded_before + 1e-9

    def slide(current: AABB, axis: int, limit: float) -> AABB:
        """Binary search the furthest legal travel along one axis."""
        reach = limit - float(current.center[axis])
        if abs(reach) < config.compaction_min_gain:
            return current
        low, high = 0.0, reach
        best = current
        for _ in range(config.compaction_iterations):
            mid = 0.5 * (low + high)
            centre = list(current.center)
            centre[axis] = float(current.center[axis]) + mid
            trial = AABB(tuple(centre), current.size, current.name)
            if acceptable(trial):
                best, low = trial, mid
            else:
                high = mid
        return best

    rect = model.floor_rect
    moved = slide(box, 1, rect.y_max - float(box.size[1]) / 2.0)
    if config.compact_sideways_always or role in (
        cls.ROLE_WALL_FRONT, cls.ROLE_TALL_PERIMETER, cls.ROLE_ELONGATED
    ):
        half = float(moved.size[0]) / 2.0
        centre_x = float(moved.center[0])
        target = (
            rect.x_min + half
            if centre_x < 0.5 * (rect.x_min + rect.x_max)
            else rect.x_max - half
        )
        moved = slide(moved, 0, target)
    return moved


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------
def routing_order(profile: cls.ItemProfile, board: Board, config) -> list[int]:
    """Which containers this item may use, best first (spec section 3)."""
    priority_indices = [i for i, m in enumerate(board.models) if m.is_prioritized]
    normal_indices = [i for i, m in enumerate(board.models) if not m.is_prioritized]
    klass = profile.cargo_class

    if not priority_indices:
        return normal_indices or list(range(len(board.models)))

    if klass == cls.SOFT:
        # soft-only never enters a priority container
        return normal_indices
    if klass in (cls.PRIORITY, cls.SOFT_PRIORITY):
        return priority_indices + normal_indices
    # normal hard: usable as foundation in a priority container, but budgeted
    allowed = []
    for idx in priority_indices:
        grid = board.grid(idx)
        hard_area = float(
            (grid.support == support_code(False, False))[grid.usable & grid.occupied].sum()
        ) * grid.cell_area if (grid.usable & grid.occupied).any() else 0.0
        if hard_area / max(grid.usable_area, 1e-9) < config.priority_container_hard_budget:
            allowed.append(idx)
    return normal_indices + allowed


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------
@dataclass
class Decision:
    placement: Placement
    candidate_counts: dict
    veto_counts: dict
    considered: int
    ladder: list


def _surface_filters(profile: cls.ItemProfile, model: ContainerModel, config) -> list[tuple]:
    """(surface kinds, orientation policy surface) pairs to try, in order."""
    out = []
    if model.shelves and (profile.is_soft or config.shelf_takes_hard):
        # The shelf is a second floor, not a soft dump.  It carries 1.87 m^2
        # against the floor's 2.03, with 0.725 m of headroom over it against
        # the floor's 0.765 -- and offering it only to soft cargo meant that on
        # a manifest with no soft cargo it was measurably, exactly unused: five
        # scenarios at 0.00 utilisation, one of them placing eighteen hard
        # items with the shelf empty above them.  Soft still gets first refusal
        # below; this only stops hard being unable to ask.
        out.append((("shelf",), "shelf"))
    out.append((("floor",), "floor"))
    if config.allow_slope_infill_on_items:
        out.append((("item",), "wedge"))
    return out


def _certainly_vetoed(candidate: Candidate, board: Board, container_idx: int,
                      coverage: float, config) -> bool:
    """Would this candidate be refused for a reason already known?

    Only the two cheap floor vetoes, and only in the form they take *before*
    the fallbacks: a corridor placement while the corridor is held, and a floor
    pose worth less than its share of the item's best footprint.  Everything
    else needs the grid, or yields when it would leave nothing, and must stay
    downstream where the fallback can fire.
    """
    if candidate.surface != "floor":
        return False
    if (
        candidate.role == cls.ROLE_NONE
        and not (candidate.profile.is_elongated and not candidate.profile.is_soft)
        and candidate.features["footprint"]
        < config.min_floor_footprint_fraction * candidate.profile.max_footprint - 1e-9
    ):
        return True
    if (
        coverage < config.corridor_release_fill
        and candidate.role != l2.ROLE_LAST_RESORT
        and candidate.features["corridor_overlap"] > 1e-4
    ):
        return True
    return False


def _shortlist_key(candidate: Candidate, typed_right_front: bool = True):
    """What "the best few" means, per family.

    Depth first for cargo that builds the foundation -- but *not* for soft and
    priority on the floor.  Those want the right front, the corner hard is
    growing away from, and ranking them by depth here is what made both the
    zone rect and the ranking key inert: by the time either ran, the shortlist
    had already thrown away every front-right candidate.  Third time this
    pattern has appeared, so it is worth saying plainly: a rule downstream of a
    truncation cannot undo the truncation.
    """
    if candidate.family == l2.FAMILY_HOLE_FILL:
        # depth is the wrong question for a pocket: the one worth taking is the
        # one this box fills, wherever it is.  Ranking these by depth alongside
        # everything else would delete the far ones before the archetype ran --
        # the same truncation mistake, in a new family.
        return (
            -candidate.features.get("hole_coverage", 0.0),
            -candidate.features["y_back"],
        )
    if (
        typed_right_front
        and candidate.surface == "floor"
        and (candidate.profile.is_soft or candidate.profile.is_prioritized)
    ):
        return (
            candidate.features.get("front_right_cost", 9.9),
            -candidate.features["wall_contact"],
        )
    return (
        -candidate.features["y_back"],
        -candidate.features["wall_contact"],
    )


def choose_for_item(board: Board, profile: cls.ItemProfile, config,
                    max_orientations: int = 3) -> Decision | None:
    best: Decision | None = None
    for container_idx in routing_order(profile, board, config):
        model = board.model(container_idx)
        if profile.is_soft and not profile.is_prioritized and model.is_prioritized:
            continue
        pool: list[Candidate] = []
        for surface_kinds, surface_policy in _surface_filters(profile, model, config):
            role_hint = cls.ROLE_ELONGATED if profile.is_elongated else cls.ROLE_NONE
            orientations = list(
                cls.orientation_order(profile, surface_policy, role_hint, config)
            )[:max_orientations]
            if surface_policy == "floor" and not profile.is_soft:
                # A standing pose can earn a place against a wall even when the
                # item is not slender enough to be called elongated.  If it is
                # never generated, max-footprint is the only option left and the
                # item is laid down by default — which is what happened to every
                # item the wall-front height cap turned away.
                seen_orientations = {o.index for o in orientations}
                for tall in cls.structural_orientation_order(profile, config)[:2]:
                    if tall.index not in seen_orientations:
                        orientations.append(tall)
                        seen_orientations.add(tall.index)
            for orientation in orientations:
                pool.extend(
                    generate_candidates(
                        board, profile, container_idx, orientation, surface_kinds, config
                    )
                )
            if surface_kinds == ("shelf",) and pool and profile.is_soft:
                break  # shelf is strongly preferred for soft cargo -- but only
                # for soft: hard should weigh a shelf place against a floor one
                # on the merits, not take the shelf merely because it fits.

        # Layer 2 proposals are generated over their own orientation set: a
        # bridge wants the widest, flattest pose, which the floor policy would
        # not have offered.
        if config.layer2_enabled and (
            profile.cargo_class == cls.NORMAL_HARD or config.typed_cap_enabled
        ):
            for orientation in cls.layer2_orientation_order(profile, config)[
                : config.max_orientations_layer2
            ]:
                pool.extend(
                    generate_layer2_candidates(
                        board, profile, container_idx, orientation, config
                    )
                )

        # Hole filling is generated once for the whole item rather than per
        # pose, because the pose is what it decides: which orientation to use
        # is a property of the gap, and every loop above has already picked one
        # before it looks at the board.
        pool.extend(
            generate_hole_candidates(board, profile, container_idx, config)
        )
        pool.extend(
            generate_front_wedge_candidates(board, profile, container_idx, config)
        )
        if not pool:
            pool.extend(
                generate_last_resort_candidates(
                    board, profile, container_idx, config
                )
            )
        if not pool:
            continue

        # cheap features first, then the expensive grid features on a
        # shortlist.  The shortlist is taken per orientation so that a pose
        # with a big footprint is never starved by a pose that happens to
        # reach one centimetre deeper.
        for candidate in pool:
            compute_features(candidate, board, config, with_grid=False)
        # Shortlist per (family, orientation), not globally.  A single
        # depth-sorted truncation is what made five separate Layer 1 rules
        # no-ops: it decided the answer before they ran.  Every family keeps its
        # own quota and they are unioned afterwards, so a bridge never has to
        # out-depth a floor candidate merely to be looked at.
        # Drop what is certainly dead *before* truncating, not after.  The
        # shortlist keeps the deepest few, and once the back is full the
        # deepest remaining floor positions are exactly the ones the corridor
        # and low-footprint vetoes refuse -- so on task 000 from the eighth
        # decision on, 321 floor candidates were generated, 40 were
        # shortlisted, and none survived, while 1.31 m^2 of floor stood empty.
        # Both tests read only cheap features, so they can run here, where they
        # decide which candidates get looked at rather than which of the
        # already-chosen few are thrown away.
        if config.prefilter_dead_candidates:
            coverage_now = board.grid(container_idx).coverage()
            alive = [
                c for c in pool
                if not _certainly_vetoed(c, board, container_idx, coverage_now, config)
            ]
            if alive:
                pool = alive

        buckets: dict[tuple[str, int], list[Candidate]] = {}
        for candidate in pool:
            buckets.setdefault(
                (candidate.family, candidate.orientation.index), []
            ).append(candidate)
        # Each family's quota is divided among *its own* poses and nothing
        # else's.  Deriving one shared number from the average number of poses
        # per family coupled them: adding a family changed how many candidates
        # every other family was allowed to keep, so turning one on or off
        # perturbed decisions it had no business touching and no A/B on it
        # could be read.
        poses_in_family: dict[str, int] = {}
        for family, _index in buckets:
            poses_in_family[family] = poses_in_family.get(family, 0) + 1
        shortlist = []
        chosen_ids = set()
        typed_rf = config.typed_floor_right_front
        front_limit = model.floor_rect.y_min + config.hard_front_band
        for (family, _index), group in buckets.items():
            per_bucket = max(
                4, config.layer2_family_quota // max(1, poses_in_family[family])
            )
            group.sort(key=lambda c: _shortlist_key(c, typed_rf))
            take = list(group[:per_bucket])
            # The front gets slots of its own.  Hard floor candidates are
            # ranked by depth and the quota cuts the shallow ones, so a front
            # placement never reached a veto to be judged on its merits -- the
            # band rule that was supposed to govern the front turned out to be
            # inert for exactly this reason, and removing it changed one
            # placement in thirteen scenarios.  Ranked by height, because a low
            # box at the front is the one that costs nothing.
            if config.front_shortlist_quota > 0 and family == l2.FAMILY_FLOOR:
                front = [
                    c for c in group
                    if c.profile.cargo_class == cls.NORMAL_HARD
                    and c.box.center[1] < front_limit
                ]
                front.sort(
                    key=lambda c: (c.features["top_z"], -c.features["y_back"])
                )
                take.extend(front[: config.front_shortlist_quota])
            for candidate in take:
                if id(candidate) not in chosen_ids:
                    chosen_ids.add(id(candidate))
                    shortlist.append(candidate)
        shortlist.sort(key=lambda c: _shortlist_key(c, typed_rf))
        for position, candidate in enumerate(shortlist):
            compute_features(
                candidate, board, config, with_grid=True,
                with_rect=position < config.residual_rect_shortlist,
            )
            candidate.archetypes = eligible_archetypes(candidate, config)

        survivors, veto_counts = apply_vetoes(shortlist, board, container_idx, config)
        if not survivors:
            # Nothing ordinary survived.  Before giving the item up -- which,
            # with the official `max_space: 1`, ends the whole episode -- look
            # for somewhere it simply fits.  This has to be keyed on survivors
            # rather than on an empty pool: a family that proposes candidates
            # and then loses all of them to a veto would otherwise suppress the
            # rescue, which is exactly what the front staircase did on its
            # first outing -- 17 placements back to 15, with the last-resort
            # placement gone and no front-wedge placement to show for it.
            rescue = generate_last_resort_candidates(
                board, profile, container_idx, config
            )
            for candidate in rescue:
                compute_features(candidate, board, config, with_grid=True)
                candidate.archetypes = eligible_archetypes(candidate, config)
            survivors, rescue_counts = apply_vetoes(
                rescue, board, container_idx, config
            )
            for name, count in rescue_counts.items():
                veto_counts[name] = veto_counts.get(name, 0) + count
        if not survivors:
            continue

        counts = {name: 0 for name in ALL_ARCHETYPES}
        for candidate in survivors:
            for name in candidate.archetypes:
                counts[name] += 1

        ladder = archetype_ladder(profile, board, container_idx, config)
        chosen = None
        chosen_archetype = None
        for name in ladder:
            pool_for_archetype = [c for c in survivors if name in c.archetypes]
            if not pool_for_archetype:
                continue
            # inside every archetype, a candidate that leaves the opening alone
            # beats one that does not
            key_fn = ARCHETYPE_KEYS[name]
            if name == A_SHELF_SAVING and not config.shelf_residual_key:
                key_fn = lambda c: (  # noqa: E731
                    c.features["footprint"], -c.features["y_back"],
                    c.orientation.tipping_ratio,
                )
            if name == A_SHELF_SAVING and config.shelf_residual_key:
                bucket = config.shelf_depth_bucket
                key_fn = lambda c: _key_shelf_saving(c, bucket)  # noqa: E731
            if name == A_TALL_PERIMETER:
                depth_first = config.perimeter_prefers_depth
                key_fn = lambda c: _key_tall_perimeter(c, depth_first)  # noqa: E731
            pool_for_archetype.sort(
                key=lambda c: (
                    c.features.get("corridor_overlap", 0.0) > 1e-4,
                    *key_fn(c),
                )
            )
            chosen = pool_for_archetype[0]
            chosen_archetype = name
            break
        if chosen is None:
            chosen = survivors[0]
            chosen_archetype = "fallback"

        box = chosen.box
        if config.compaction_iterations > 0 and chosen.surface in (
            ("floor", "item") if config.compact_raised else ("floor",)
        ):
            # Raised placements were never compacted at all, so a terrace could
            # stop 0.10 m short of the chamfer strip -- and a step that reaches
            # the strip is a step that recovers wedge area.  The same slack
            # costs nothing anywhere else either: it is gap between the box and
            # whatever it should be touching.
            box = compact_backwards(box, board, container_idx, chosen.role, config)

        placement = Placement(
            profile=profile,
            orientation=chosen.orientation,
            container_idx=container_idx,
            box=box,
            surface=chosen.surface,
            surface_name=chosen.surface_name,
            role=chosen.role,
            archetype=chosen_archetype,
            reason=_reason_for(chosen, chosen_archetype, board, config),
            features={
                **{k: _round(v) for k, v in chosen.features.items()},
                "compacted_y_m": _round(
                    float(box.center[1]) - float(chosen.box.center[1])
                ),
                "compacted_x_m": _round(
                    float(box.center[0]) - float(chosen.box.center[0])
                ),
            },
            container_is_prioritized=model.is_prioritized,
            container_has_shelf=model.has_shelf,
            layer=stack_level(
                box, board.container(container_idx), chosen.role, config, model
            ),
        )
        decision = Decision(
            placement=placement,
            candidate_counts=counts,
            veto_counts=veto_counts,
            considered=len(pool),
            ladder=ladder,
        )
        # first container in routing order that can take the item wins
        best = decision
        break
    return best


def _round(value):
    if isinstance(value, float):
        return round(value, 4)
    if isinstance(value, (np.floating,)):
        return round(float(value), 4)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    return value


def _reason_for(candidate: Candidate, archetype: str, board: Board, config) -> str:
    model = board.model(candidate.container_idx)
    bits = [f"archetype={archetype}", f"class={candidate.profile.cargo_class}"]
    if candidate.role != cls.ROLE_NONE:
        bits.append(f"role={candidate.role}")
    if candidate.surface == "shelf":
        bits.append("shelf preferred for soft cargo; footprint minimised")
    if candidate.features.get("corridor_overlap", 0.0) > 1e-4:
        bits.append("corridor released (board past the early phase)")
    if candidate.features.get("new_interior_hole_area", 0.0) > 1e-4:
        bits.append(
            f"accepts interior hole {candidate.features['new_interior_hole_area']:.3f} m2"
        )
    if candidate.role == cls.ROLE_WALL_FRONT:
        bits.append(
            f"slope wall front at x={float(candidate.box.minimum[0]):.3f} "
            f"(foot {model.x_floor_min:.3f})"
        )
    return "; ".join(bits)


# ---------------------------------------------------------------------------
# Offline ordering (the `optimize` hook)
# ---------------------------------------------------------------------------
def constructive_order(profiles: list[cls.ItemProfile], config,
                       model: ContainerModel | None = None) -> list[int]:
    """Rule-based stream order for Layer 1.

    Wall material first (the slope wall is meant to be backed by the foundation
    that follows it), then the foundation largest-first, then the structural
    oddments, then the constrained cargo whose home is a reserved zone or a
    shelf.  This is a fixed rule, not a search.
    """

    def group(profile: cls.ItemProfile) -> int:
        if profile.cargo_class == cls.NORMAL_HARD:
            if (
                model is not None
                and wall_front_material(profile, model, config)
                and profile.max_height >= config.wall_front_min_height
            ):
                return 0
            return 2 if profile.is_elongated else 1
        if profile.cargo_class == cls.PRIORITY:
            return 3
        if profile.cargo_class == cls.SOFT_PRIORITY:
            return 4
        return 5

    def key(profile: cls.ItemProfile):
        bucket = group(profile)
        if bucket == 0:
            # tallest wall material first
            return (bucket, -round(profile.max_height, 6), profile.index)
        return (
            bucket,
            -round(profile.max_footprint, 6),
            -round(profile.mass, 6),
            profile.index,
        )

    return [p.index for p in sorted(profiles, key=key)]
