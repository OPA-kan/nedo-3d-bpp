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

from dataclasses import dataclass, field

import numpy as np

from . import classify as cls
from . import triangle as tri
from ._reuse import (
    AABB,
    Geometry,
    packed_aabbs_local,
    shelf_aabbs,
    simulator_action_center,
    transport_samples,
    within_euclidean_clearance,
    penetrates_with_lateral_clearance,
)
from .diagnostics import FloorGrid, support_code
from .geometry import ContainerModel, Rect, box_rect


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

    # -- accessors -------------------------------------------------------
    def model(self, idx: int) -> ContainerModel:
        return self.models[idx]

    def container(self, idx: int) -> dict:
        return self.containers[idx]

    def grid(self, idx: int) -> FloorGrid:
        grid = self._grids[idx]
        if grid is None:
            from .diagnostics import build_floor_grid

            grid = build_floor_grid(
                self.models[idx], self.placements[idx], self.config.candidate_grid_cell
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
            from .diagnostics import corridor_report

            grid = self.grid(idx)
            model = self.models[idx]
            corridor = corridor_report(grid, model)
            state = tri.evaluate(
                model,
                self.placements[idx],
                self.triangle_demand[idx],
                grid.coverage(),
                1.0 - float(corridor["corridor_clear_lane_ratio"]),
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
            }
        )
        self.placements[idx].append(placement)
        self._grids[idx] = None
        self._triangle[idx] = None


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

    metrics = Geometry.support_metrics(box, container)
    if metrics.ratio < config.min_support_ratio:
        return False, "insufficient-support"
    if metrics.center_margin < 0.0:
        # centre of mass outside the contact patch: it would topple on settle
        return False, "unstable-centre-of-mass"

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
        if kind == "item":
            # staircase only: the support has to be a step in the strip
            if not tri.in_strip(surface, model, config):
                continue
        for x in xs:
            for y in ys:
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

    if not with_grid or candidate.surface != "floor":
        features.setdefault("new_interior_hole_area", 0.0)
        features.setdefault("open_free_area", 0.0)
        features.setdefault("free_component_count", 0)
        features.setdefault("largest_residual_rect", 0.0)
        features.setdefault("neighbour_height_step", 0.0)
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

    if with_rect:
        from .diagnostics import largest_rectangle_in_mask

        cells, _ = largest_rectangle_in_mask(reached)
        features["largest_residual_rect"] = cells * grid.cell_area
    else:
        features.setdefault("largest_residual_rect", 0.0)


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
def _key_max_footprint(c):
    return (
        -c.features["footprint"],
        -c.features["y_back"],
        -c.features["frontier_contact"],
        c.features["top_z"],
    )


def _key_back_corner(c):
    return (
        -c.features["y_back"],
        -c.features["frontier_contact"],
        -c.features["footprint"],
    )


def _key_min_hole(c):
    return (
        c.features["new_interior_hole_area"],
        c.features["free_component_count"],
        -c.features["y_back"],
    )


def _key_largest_residual(c):
    return (
        -c.features["largest_residual_rect"],
        c.features["new_interior_hole_area"],
        -c.features["y_back"],
    )


def _key_shelf_saving(c):
    # the shelf fills from the back too: a bag left by the opening is a bag in
    # the way of everything that comes after it
    return (
        c.features["footprint"],
        -c.features["y_back"],
        c.orientation.tipping_ratio,
    )


def _key_soft_edge(c):
    return (
        -c.features["soft_zone_fit"],
        -c.features["soft_cluster"],
        -c.features["y_back"],
    )


def _key_priority_edge(c):
    return (
        -c.features["priority_zone_fit"],
        -c.features["priority_cluster"],
        -c.features["y_back"],
    )


def _key_sp_cluster(c):
    return (
        -c.features["sp_cluster"],
        -max(c.features["priority_zone_fit"], c.features["soft_zone_fit"]),
        -c.features["y_back"],
    )


def _key_elongated_wall(c):
    return (
        0 if c.features["has_backing"] else 1,
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


def _key_tall_perimeter(c):
    return (
        0 if c.features["has_backing"] else 1,
        -c.features["top_z"],
        -c.features["frontier_contact"],
        -c.features["y_back"],
    )


def _key_wall_front(c):
    return (
        -c.features["top_z"],
        c.box.minimum[0],
        -c.features["y_back"],
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
}


def eligible_archetypes(candidate: Candidate, config) -> set:
    tags = set()
    if candidate.surface == "shelf":
        tags.add(A_SHELF_SAVING)
        return tags
    if candidate.role == cls.ROLE_SLOPE_INFILL:
        tags.add(A_SLOPE_INFILL)
        return tags
    tags.update({A_MAX_FOOTPRINT, A_BACK_CORNER, A_MIN_HOLE, A_LARGEST_RESIDUAL})
    if candidate.role == cls.ROLE_WALL_FRONT:
        tags.add(A_WALL_FRONT)
    if candidate.role == cls.ROLE_TALL_PERIMETER:
        tags.add(A_TALL_PERIMETER)
    if candidate.role == cls.ROLE_WEDGE_STEP:
        tags.add(A_WEDGE_CAP if candidate.profile.is_soft else A_WEDGE_STEP)
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
    if klass == cls.NORMAL_HARD:
        if wall_ratio < config.wall_front_target_ratio:
            ladder.append(A_WALL_FRONT)
        if profile.is_elongated:
            ladder.extend([A_ELONGATED_WALL, A_BACK_CORNER, A_MIN_HOLE])
        else:
            ladder.extend([
                A_TALL_PERIMETER, A_MAX_FOOTPRINT, A_BACK_CORNER,
                A_MIN_HOLE, A_LARGEST_RESIDUAL,
            ])
    elif klass == cls.SOFT:
        ladder.append(A_SHELF_SAVING)
        ladder.append(A_SOFT_EDGE)
        if profile.is_elongated:
            ladder.append(A_ELONGATED_WALL)
        ladder.extend([A_MIN_HOLE, A_BACK_CORNER])
    elif klass == cls.PRIORITY:
        if model.is_prioritized:
            ladder.extend([A_MAX_FOOTPRINT, A_BACK_CORNER, A_MIN_HOLE])
        else:
            ladder.extend([A_PRIORITY_EDGE, A_MIN_HOLE, A_BACK_CORNER])
    else:  # soft + priority
        ladder.append(A_SHELF_SAVING)
        ladder.extend([A_SP_CLUSTER, A_PRIORITY_EDGE, A_MIN_HOLE, A_BACK_CORNER])
    ladder.append(A_MAX_FOOTPRINT)
    seen, out = set(), []
    for name in ladder:
        if name not in seen:
            seen.add(name)
            out.append(name)
    return out


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

    # 1. transport corridor: while the board is young the opening is off
    #    limits; once the rest of the floor is spent the corridor is released,
    #    and even then a non-corridor candidate always wins (see the ladder
    #    tie-break).
    if coverage < config.corridor_release_fill:
        kept = []
        for candidate in survivors:
            if (
                candidate.surface == "floor"
                and candidate.features["corridor_overlap"] > 1e-4
            ):
                drop(candidate, "corridor")
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
            and candidate.role != cls.ROLE_WALL_FRONT
        ):
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

    return survivors, counts


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
    wants_shelf = profile.is_soft and model.shelves
    if wants_shelf:
        out.append((("shelf",), "shelf"))
    out.append((("floor",), "floor"))
    if config.allow_slope_infill_on_items:
        out.append((("item",), "wedge"))
    return out


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
            if surface_kinds == ("shelf",) and pool:
                break  # shelf is strongly preferred for soft cargo
        if not pool:
            continue

        # cheap features first, then the expensive grid features on a
        # shortlist.  The shortlist is taken per orientation so that a pose
        # with a big footprint is never starved by a pose that happens to
        # reach one centimetre deeper.
        for candidate in pool:
            compute_features(candidate, board, config, with_grid=False)
        by_orientation: dict[int, list[Candidate]] = {}
        for candidate in pool:
            by_orientation.setdefault(candidate.orientation.index, []).append(candidate)
        per_orientation = max(
            8, config.shortlist_size // max(1, len(by_orientation))
        )
        shortlist = []
        for group in by_orientation.values():
            group.sort(key=lambda c: (-c.features["y_back"], -c.features["wall_contact"]))
            shortlist.extend(group[:per_orientation])
        shortlist.sort(key=lambda c: (-c.features["y_back"], -c.features["wall_contact"]))
        for position, candidate in enumerate(shortlist):
            compute_features(
                candidate, board, config, with_grid=True,
                with_rect=position < config.residual_rect_shortlist,
            )
            candidate.archetypes = eligible_archetypes(candidate, config)

        survivors, veto_counts = apply_vetoes(shortlist, board, container_idx, config)
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
            pool_for_archetype.sort(
                key=lambda c: (
                    c.features.get("corridor_overlap", 0.0) > 1e-4,
                    *ARCHETYPE_KEYS[name](c),
                )
            )
            chosen = pool_for_archetype[0]
            chosen_archetype = name
            break
        if chosen is None:
            chosen = survivors[0]
            chosen_archetype = "fallback"

        placement = Placement(
            profile=profile,
            orientation=chosen.orientation,
            container_idx=container_idx,
            box=chosen.box,
            surface=chosen.surface,
            surface_name=chosen.surface_name,
            role=chosen.role,
            archetype=chosen_archetype,
            reason=_reason_for(chosen, chosen_archetype, board, config),
            features={k: _round(v) for k, v in chosen.features.items()},
            container_is_prioritized=model.is_prioritized,
            container_has_shelf=model.has_shelf,
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
