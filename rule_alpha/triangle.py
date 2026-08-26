"""The slope triangle as a three-state resource: RESERVE -> INFILL -> CLOSE.

Why a state machine at all
--------------------------
Placing ordinary hard cargo against the chamfer foot is **irreversible**: the
pocket above the wedge is gone for the rest of the episode.  Leaving the strip
empty costs only the volume it holds right now.  Under an unknown arrival
order the asymmetry is the whole argument — so rather than predicting which
items are coming, rule-alpha puts a price on the *option* an action destroys.

    RESERVE   keep the strip for a bridge; ordinary hard cargo stays out
    INFILL    a bridge is standing; its top is a restricted-support zone
    CLOSE     the reservation is not worth its cost any more; release it

The geometry that forces the design
-----------------------------------
The wedge is bounded by the chamfer, and the binding constraint on a
floor-resting box is its **bottom** corner, so no floor placement can overhang
the wedge at any height.  The only way to get support over it is a box whose
*top* clears the point where the chamfer meets the wall — ``z_chamfer_top``.
On the shipped ULD that is 0.378 m above the floor.

That is why a bridge does **not** obey the ordinary wall-front height cap.
The cap exists to stop cargo being stood up for no reason; a bridge is stood
up for a specific reason, and half the floor-to-shelf gap (0.383 m) leaves it
a 5 mm band to live in.  A bridge instead gets the transport limit as its cap,
and ``z_chamfer_top`` as its floor.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import classify as cls
from .geometry import ContainerModel, Rect


STATE_RESERVE = "reserve"
STATE_INFILL = "infill"
STATE_CLOSED = "closed"

# who may stand on a bridge top, best first.  A bridge is built for soft cargo,
# but committing to soft alone over-specialises: if none arrives the structure
# is wasted, so the zone degrades through the other constrained classes before
# it is released to plain cargo.
POCKET_LADDER = (cls.SOFT, cls.SOFT_PRIORITY, cls.PRIORITY, cls.NORMAL_HARD)


@dataclass
class TriangleDemand:
    """Arrival mix used to price the reservation."""

    p_pocket: float = 0.0
    """Share of the stream that could actually *use* a bridge top."""
    p_soft: float = 0.0
    p_bridge: float = 0.0
    """Share that could *be* a bridge — feasibility, not demand."""
    source: str = "unknown"

    def as_dict(self) -> dict:
        return {
            "p_pocket_customers": round(self.p_pocket, 4),
            "p_soft": round(self.p_soft, 4),
            "p_bridge_capable": round(self.p_bridge, 4),
            "source": self.source,
        }


@dataclass
class TriangleState:
    state: str
    score: float
    terms: dict = field(default_factory=dict)
    bridge_item: int | None = None
    bridge_top_z: float | None = None
    reason: str = ""

    def as_dict(self) -> dict:
        return {
            "state": self.state,
            "reserve_score": round(self.score, 4),
            "terms": self.terms,
            "bridge_item": self.bridge_item,
            "bridge_top_z": (
                round(self.bridge_top_z, 4) if self.bridge_top_z is not None else None
            ),
            "reason": self.reason,
        }


# ---------------------------------------------------------------------------
# Geometry of the bridge
# ---------------------------------------------------------------------------
def bridge_min_height(model: ContainerModel) -> float:
    """A bridge top has to clear the point where the chamfer meets the wall.

    Below that the box is just a short wall-front piece: nothing placed on it
    can reach out over the wedge, because the chamfer still cuts the space at
    that height.
    """
    return max(0.0, model.z_chamfer_top - model.z_floor)


def bridge_max_height(model: ContainerModel, config) -> float:
    """What can still be carried in past the shelf above the strip."""
    gap = max(0.0, model.shelf_bottom_z - model.z_floor)
    return max(0.0, gap - (config.floor_action_lift + config.settled_clearance))


def bridge_capable(profile: cls.ItemProfile, model: ContainerModel, config) -> bool:
    """Does this item have a pose that could serve as a bridge?"""
    if profile.is_soft or profile.is_prioritized:
        return False
    low, high = bridge_min_height(model), bridge_max_height(model, config)
    if low > high:
        return False
    budget = config.wall_front_max_footprint_fraction * model.usable_floor_area
    return any(
        low <= orientation.dz <= high and orientation.footprint <= budget + 1e-9
        for orientation in profile.orientations
    )


def is_bridge(box, model: ContainerModel, config) -> bool:
    """A settled box that actually opens the pocket over the wedge."""
    from .geometry import box_rect

    rect = box_rect(box)
    at_foot = rect.x_min <= model.x_floor_min + config.wall_front_band
    tall_enough = float(box.maximum[2]) >= model.z_chamfer_top - 1e-6
    low_enough = (
        float(box.maximum[2]) - model.z_floor <= bridge_max_height(model, config) + 1e-6
    )
    return bool(at_foot and tall_enough and low_enough)


def pocket_rect(model: ContainerModel) -> Rect:
    """Footprint of the wedge a bridge makes reachable."""
    return Rect(
        model.x_wall_min,
        model.x_floor_min,
        model.floor_rect.y_min,
        model.floor_rect.y_max,
    )


def potential_support_area(model: ContainerModel) -> float:
    """Support area a bridge would create that cannot exist otherwise."""
    return pocket_rect(model).area


# ---------------------------------------------------------------------------
# Demand
# ---------------------------------------------------------------------------
def measure_demand(profiles, model: ContainerModel, config,
                   source: str = "declared-manifest") -> TriangleDemand:
    """Share of the stream that would make the reservation pay off.

    The environment hands the whole manifest to ``optimize()``, so this reads a
    list it was given.  With no manifest, pass whatever has been observed so
    far and the same arithmetic applies to the sample instead.
    """
    if not profiles:
        return TriangleDemand(source="empty-stream")
    total = float(len(profiles))
    allowed = set(POCKET_LADDER[: config.triangle_pocket_ladder_depth + 1])
    customers = sum(1 for p in profiles if p.cargo_class in allowed)
    soft = sum(1 for p in profiles if p.is_soft)
    bridges = sum(1 for p in profiles if bridge_capable(p, model, config))
    return TriangleDemand(
        p_pocket=customers / total,
        p_soft=soft / total,
        p_bridge=bridges / total,
        source=source,
    )


# ---------------------------------------------------------------------------
# The state machine
# ---------------------------------------------------------------------------
def reserve_score(model: ContainerModel, demand: TriangleDemand, floor_fill: float,
                  bottleneck: float, config) -> tuple[float, dict]:
    """R = w1 p_pocket + w2 p_bridge + w3 A_potential - w4 F - w5 B.

    ``p_pocket`` is demand and ``p_bridge`` is feasibility, and the benefit
    terms are gated on both: a pocket nobody can fill is worth nothing, and so
    is a pocket nobody wants.  Without that gate a stream of plain hard cargo
    scores high on feasibility alone and reserves a strip for a customer that
    never comes.
    """
    area_term = potential_support_area(model) / max(1e-9, model.usable_floor_area)
    if demand.p_pocket <= 0.0 or demand.p_bridge <= 0.0:
        area_term = 0.0
    terms = {
        "p_pocket_customers": round(demand.p_pocket, 4),
        "p_soft": round(demand.p_soft, 4),
        "p_bridge_capable": round(demand.p_bridge, 4),
        "potential_support_ratio": round(area_term, 4),
        "floor_fill": round(floor_fill, 4),
        "transport_bottleneck": round(bottleneck, 4),
    }
    if demand.p_pocket <= 0.0 or demand.p_bridge <= 0.0:
        return -1.0, terms
    score = (
        config.triangle_weight_soft * demand.p_pocket
        + config.triangle_weight_bridge * demand.p_bridge
        + config.triangle_weight_area * area_term
        - config.triangle_weight_fill * floor_fill
        - config.triangle_weight_bottleneck * bottleneck
    )
    return score, terms


def evaluate(model: ContainerModel, placements, demand: TriangleDemand,
             floor_fill: float, bottleneck: float, config) -> TriangleState:
    """Current state of one container's triangle zone."""
    bridge = next(
        (p for p in placements
         if p.surface != "shelf" and is_bridge(p.box, model, config)),
        None,
    )
    score, terms = reserve_score(model, demand, floor_fill, bottleneck, config)

    if bridge is not None and (
        score <= config.triangle_reserve_threshold or demand.p_pocket <= 0.0
    ):
        # a bridge went up anyway (the wall-front rule reached that height on
        # its own) but the reservation is not worth keeping, so the pocket is
        # open to whatever fits rather than held for a customer that is not
        # coming
        return TriangleState(
            state=STATE_CLOSED, score=score, terms=terms,
            bridge_item=bridge.profile.index, bridge_top_z=bridge.top_z,
            reason=(
                f"item {bridge.profile.index} happens to bridge the wedge, but "
                f"the reservation scores {score:.3f}: the pocket is released to "
                "ordinary cargo"
            ),
        )

    if bridge is not None:
        return TriangleState(
            state=STATE_INFILL,
            score=score,
            terms=terms,
            bridge_item=bridge.profile.index,
            bridge_top_z=bridge.top_z,
            reason=(
                f"item {bridge.profile.index} bridges the wedge at "
                f"z={bridge.top_z:.3f} (chamfer top {model.z_chamfer_top:.3f}); "
                "its top is a restricted-support zone"
            ),
        )

    if bridge_min_height(model) > bridge_max_height(model, config):
        return TriangleState(
            state=STATE_CLOSED, score=score, terms=terms,
            reason="no bridge height is both tall enough to clear the chamfer "
                   "and low enough to be carried past the shelf",
        )

    if demand.p_pocket <= 0.0:
        return TriangleState(
            state=STATE_CLOSED, score=score, terms=terms,
            reason="no soft, soft+priority or priority cargo in the stream: a "
                   "bridge would open a pocket with no customer",
        )
    if demand.p_bridge <= 0.0:
        return TriangleState(
            state=STATE_CLOSED, score=score, terms=terms,
            reason="nothing in the stream can serve as a bridge",
        )

    if score > config.triangle_reserve_threshold:
        return TriangleState(
            state=STATE_RESERVE, score=score, terms=terms,
            reason=(
                f"reserve score {score:.3f} > {config.triangle_reserve_threshold}: "
                "the option is worth more than the volume it withholds"
            ),
        )
    return TriangleState(
        state=STATE_CLOSED, score=score, terms=terms,
        reason=(
            f"reserve score {score:.3f} <= {config.triangle_reserve_threshold}: "
            "released to ordinary cargo"
        ),
    )


def pocket_allows(profile: cls.ItemProfile, state: TriangleState, config) -> bool:
    """May this item stand on the bridge top?

    Restricted-support zone: the pocket is built for soft cargo, but holding
    out for soft alone over-specialises.  The ladder degrades through the other
    constrained classes, and only a CLOSED zone takes plain cargo.
    """
    if state.state == STATE_CLOSED:
        return True
    if state.state != STATE_INFILL:
        return False
    rank = POCKET_LADDER.index(profile.cargo_class)
    return rank <= config.triangle_pocket_ladder_depth
