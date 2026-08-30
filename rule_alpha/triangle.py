"""The chamfer wedge as a staircase, not a wall.

The wedge is not a small notch.  On the shipped ULD the chamfer top is 0.378 m
above the floor while the usable height under the shelf is 0.765 m, so nearly
the lower half of the cross section is cut away.  Writing that off as dead
volume is expensive.

The obvious answer — stand one box tall enough to bridge straight to the
chamfer top — is the wrong shape.  It demands a single 0.378 m piece, that
piece still has to be delivered past the shelf, and it recovers nothing below
its own top.  The cheaper structure grows instead:

    wedge  ->  small-hard staircase  ->  soft cap

    shelf
    ────────────────────────────
              soft  soft            <- upper wedge: soft disposal zone
            ████████
              █████                 <- small cargo; each top is a new support
            ████████
          ██████████                <- first step: an ordinary low box on the floor
        ╱
       ╱   wedge
      ╱________________________

Each box sits on the flat top of the one below and reaches a little further
towards the wall.  No single item has to be tall, so the wall front can stay
low and keep the transport lane open, and the volume is recovered by small
cargo that is awkward to place anywhere else.

How far a step may reach
------------------------
Two limits, whichever is tighter:

* the chamfer, ``x_limit_at_height(bottom_z)``;
* stability.  A step overhanging its support by ``o`` out of width ``w`` has
  support ratio ``(w - o) / w``, so the official 0.6 floor gives ``o <= 0.4w``.
  rule-alpha uses ``wedge_overhang_fraction`` (0.25) because the centre of mass
  and the settle step are not modelled exactly.

From the second step on it is *stability* that binds, not the chamfer — which
is why the staircase keeps climbing at a steady rate instead of stalling when
it reaches the chamfer top.

States
------
    RAW         nothing at the foot yet; the first step is a low floor box
    STAIRCASE   steps are growing; small hard cargo is wanted here
    SOFT_READY  the remainder is short and awkward: soft cargo is pushed in
    CLOSED      released to whatever fits

Leaving the strip is priced rather than scheduled: committing it to ordinary
cargo is irreversible, while withholding it costs only the volume it holds now.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import classify as cls
from .geometry import ContainerModel, Rect, box_rect


STATE_RAW = "raw-wedge"
STATE_STAIRCASE = "staircase"
STATE_SOFT_READY = "soft-ready"
STATE_CLOSED = "closed"

# who may take the top of the staircase, best first.  Holding out for soft
# alone over-specialises, so the zone degrades through the other constrained
# classes before it is released.
CAP_LADDER = (cls.SOFT, cls.SOFT_PRIORITY, cls.PRIORITY, cls.NORMAL_HARD)


@dataclass
class WedgeDemand:
    """Arrival mix used to price the reservation."""

    p_step: float = 0.0
    """Share of the stream small enough to be a staircase step."""
    n_step: int = 0
    """...and how many items that is.

    The share is the right unit for pricing -- a stream that is mostly steps is
    a stream that wants a staircase -- but the wrong one for the go/no-go gate,
    because a staircase needs a *number* of steps, not a proportion.  Three
    step-capable items out of 34 is 0.088 and builds a perfectly good three-step
    climb; the share gate refused it on two of the shipped boards before a
    single item had been placed."""
    p_cap: float = 0.0
    """Share that could take the cap once the staircase is up."""
    p_soft: float = 0.0
    source: str = "unknown"

    def as_dict(self) -> dict:
        return {
            "p_step_capable": round(self.p_step, 4),
            "n_step_capable": self.n_step,
            "p_cap_customers": round(self.p_cap, 4),
            "p_soft": round(self.p_soft, 4),
            "source": self.source,
        }


@dataclass
class WedgeState:
    state: str
    score: float
    terms: dict = field(default_factory=dict)
    steps: int = 0
    top_z: float = 0.0
    left_reach: float = 0.0
    next_gain: float = 0.0
    recovered_area: float = 0.0
    reason: str = ""

    def as_dict(self) -> dict:
        return {
            "state": self.state,
            "reserve_score": round(self.score, 4),
            "terms": self.terms,
            "staircase_steps": self.steps,
            "staircase_top_z": round(self.top_z, 4),
            "left_reach_x": round(self.left_reach, 4),
            "next_step_gain_m": round(self.next_gain, 4),
            "wedge_recovered_area_m2": round(self.recovered_area, 5),
            "reason": self.reason,
        }


# ---------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------
def strip_rect(model: ContainerModel) -> Rect:
    """Floor footprint the staircase is built in."""
    return model.wall_front_strip


def in_strip(box, model: ContainerModel, config) -> bool:
    """Is this box part of the chamfer structure?

    Both tests matter.  Asking only about ``x`` made the strip a column running
    to the roof, so cargo on the small shelf at 0.845 and every Layer 2 terrace
    above it counted as staircase -- setting the staircase's reach and top from
    boxes with nothing to do with the bevel, and putting them under a rule that
    refuses anything not reaching further into a chamfer that ended a metre
    below them.  The wedge is the chamfer's structure, and the chamfer ends at
    ``wedge_ceiling``.
    """
    if float(box.minimum[2]) >= wedge_ceiling(model, config):
        return False
    return box_rect(box).x_min <= model.x_floor_min + config.wall_front_band


def wedge_ceiling(model: ContainerModel, config) -> float:
    """The staircase has to stay under the shelf above the strip."""
    return model.shelf_bottom_z - config.settled_clearance


def max_overhang(model: ContainerModel, support_left_x: float, bottom_z: float,
                 width: float, config) -> float:
    """How far a step resting at ``bottom_z`` may reach past its support."""
    geometric = support_left_x - model.x_limit_at_height(bottom_z)
    stability = config.wedge_overhang_fraction * width
    return max(0.0, min(geometric, stability))


def step_capable(profile: cls.ItemProfile, model: ContainerModel, config) -> bool:
    """Small hard cargo that could serve as a staircase step."""
    if profile.is_soft:
        return False
    budget = config.wedge_step_max_footprint_fraction * model.usable_floor_area
    return any(
        orientation.footprint <= budget + 1e-9
        and orientation.dz <= config.wedge_step_max_height
        for orientation in profile.orientations
    )


def staircase(model: ContainerModel, placements, config):
    """Placements forming the staircase, lowest first."""
    return sorted(
        (p for p in placements
         if p.surface != "shelf" and in_strip(p.box, model, config)),
        key=lambda p: p.top_z,
    )


def staircase_profile(model: ContainerModel, placements, config):
    """``(top_z, left_reach, recovered_cross_section)`` of the staircase."""
    steps = staircase(model, placements, config)
    if not steps:
        return model.z_floor, model.x_floor_min, 0.0
    top = max(p.top_z for p in steps)
    left = min(p.rect.x_min for p in steps)
    recovered = sum(wedge_overlap_area(model, p.box) for p in steps)
    return top, left, recovered


def wedge_overlap_area(model: ContainerModel, box, slices: int = 24) -> float:
    """Cross-section of the wedge triangle this box actually occupies.

    Only the part left of the floor limit, below the chamfer top and above the
    chamfer line counts.  Summing "everything left of the floor limit" would
    also count the space above the chamfer top, which is ordinary container
    volume that was never wedge.
    """
    rect = box_rect(box)
    z0 = max(float(box.minimum[2]), model.z_floor)
    z1 = min(float(box.maximum[2]), model.z_chamfer_top)
    if z1 <= z0:
        return 0.0
    step = (z1 - z0) / slices
    area = 0.0
    for index in range(slices):
        z = z0 + (index + 0.5) * step
        right = min(rect.x_max, model.x_floor_min)
        leftmost = max(rect.x_min, model.x_limit_at_height(z))
        area += max(0.0, right - leftmost) * step
    return area


def next_step_gain(model: ContainerModel, placements, config,
                   width: float | None = None) -> float:
    """Leftward reach the staircase can still win.  Zero means the climb is over.

    With no steps yet the answer is not "zero": the *first* step cannot
    overhang at all, because at floor height the chamfer limit is exactly the
    floor limit.  What matters is what the step after it would unlock, so an
    empty strip is probed with a nominal first step.
    """
    steps = staircase(model, placements, config)
    probe = config.wedge_step_probe_width if width is None else width
    if not steps:
        nominal_top = model.z_floor + config.wedge_step_probe_height
        return max_overhang(model, model.x_floor_min, nominal_top, probe, config)
    top, left, _ = staircase_profile(model, placements, config)
    if top >= wedge_ceiling(model, config):
        return 0.0
    return max_overhang(model, left, top, probe, config)


def is_wedge_step(box, support_rect: Rect, model: ContainerModel, config) -> bool:
    """A legal staircase step: in the strip, reaching left, within the limits."""
    rect = box_rect(box)
    if not in_strip(box, model, config):
        return False
    if float(box.maximum[2]) > wedge_ceiling(model, config) + 1e-9:
        return False
    overhang = support_rect.x_min - rect.x_min
    if overhang < -1e-9:
        return False
    allowed = max_overhang(
        model, support_rect.x_min, float(box.minimum[2]),
        float(box.size[0]), config,
    )
    return overhang <= allowed + 1e-9


# ---------------------------------------------------------------------------
# Demand
# ---------------------------------------------------------------------------
def measure_demand(profiles, model: ContainerModel, config,
                   source: str = "declared-manifest") -> WedgeDemand:
    """Shares of the declared stream that make the reservation pay off.

    The environment hands the whole manifest to ``optimize()``, so this reads a
    list it was given.  With no manifest, pass what has been observed so far and
    the same arithmetic applies to the sample.
    """
    if not profiles:
        return WedgeDemand(source="empty-stream")
    total = float(len(profiles))
    allowed = set(CAP_LADDER[: config.wedge_cap_ladder_depth + 1])
    n_step = sum(1 for p in profiles if step_capable(p, model, config))
    return WedgeDemand(
        p_step=n_step / total,
        n_step=n_step,
        p_cap=sum(1 for p in profiles if p.cargo_class in allowed) / total,
        p_soft=sum(1 for p in profiles if p.is_soft) / total,
        source=source,
    )


# ---------------------------------------------------------------------------
# State machine
# ---------------------------------------------------------------------------
def reserve_score(model: ContainerModel, demand: WedgeDemand, floor_fill: float,
                  bottleneck: float, remaining: float, config):
    """R = w_step p_step + w_cap p_cap + w_area A_remaining - w_fill F - w_bn B.

    ``A_remaining`` is the share of the wedge still worth chasing, so the score
    decays on its own as the staircase runs out of room — no step counter.
    Nothing in the stream that can be a step means the reservation is worthless
    regardless of the other terms.
    """
    terms = {
        "p_step_capable": round(demand.p_step, 4),
        "p_cap_customers": round(demand.p_cap, 4),
        "remaining_wedge_share": round(remaining, 4),
        "floor_fill": round(floor_fill, 4),
        "transport_bottleneck": round(bottleneck, 4),
    }
    terms["n_step_capable"] = demand.n_step
    if (
        demand.p_step < config.wedge_min_step_share
        and demand.n_step < config.wedge_min_step_count
    ):
        # cap customers are worth nothing without something to build the
        # staircase out of: holding the strip for soft cargo that has no way to
        # get up there is the waste this score exists to prevent.  Enough
        # *items* settles it either way, though -- a long manifest with three
        # step-capable boxes can still build a three-step climb, and judging it
        # by share alone shut the zone before anything was placed.
        return -1.0, terms
    score = (
        config.wedge_weight_step * demand.p_step
        + config.wedge_weight_cap * demand.p_cap
        + config.wedge_weight_area * remaining
        - config.wedge_weight_fill * floor_fill
        - config.wedge_weight_bottleneck * bottleneck
    )
    return score, terms


def evaluate(model: ContainerModel, placements, demand: WedgeDemand,
             floor_fill: float, bottleneck: float, config) -> WedgeState:
    steps = staircase(model, placements, config)
    top, left, recovered = staircase_profile(model, placements, config)
    gain = next_step_gain(model, placements, config)
    remaining = max(0.0, 1.0 - recovered / max(1e-9, model.slope_wedge_area))
    score, terms = reserve_score(
        model, demand, floor_fill, bottleneck, remaining, config
    )
    common = dict(
        score=score, terms=terms, steps=len(steps), top_z=top,
        left_reach=left, next_gain=gain, recovered_area=recovered,
    )

    if gain <= config.wedge_min_step_gain:
        # nothing more to win by climbing.  What is left is short and awkward,
        # which is exactly what soft cargo absorbs well.
        if demand.p_cap > 0.0 and steps and recovered > 0.0:
            return WedgeState(
                state=STATE_SOFT_READY,
                reason=(
                    f"staircase tops out at z={top:.3f} and the next step would "
                    f"gain only {gain:.3f} m: the remainder is a soft disposal "
                    "zone"
                ),
                **common,
            )
        return WedgeState(
            state=STATE_CLOSED,
            reason="no further step is worth taking and no cap customer is coming",
            **common,
        )

    if score <= config.wedge_reserve_threshold:
        return WedgeState(
            state=STATE_CLOSED,
            reason=(
                f"reserve score {score:.3f} <= {config.wedge_reserve_threshold}: "
                "the strip is released to ordinary cargo"
            ),
            **common,
        )

    if steps:
        return WedgeState(
            state=STATE_STAIRCASE,
            reason=(
                f"{len(steps)} step(s) to z={top:.3f}, reach x={left:.3f}; the "
                f"next could add {gain:.3f} m"
            ),
            **common,
        )
    return WedgeState(
        state=STATE_RAW,
        reason=(
            "no step yet: the first is an ordinary low box on the floor at the "
            "chamfer foot"
        ),
        **common,
    )


# ---------------------------------------------------------------------------
# Who may use the zone
# ---------------------------------------------------------------------------
def cap_allows(profile: cls.ItemProfile, state: WedgeState, config) -> bool:
    """May this item take the top of the staircase?"""
    if state.state == STATE_CLOSED:
        return True
    if state.state != STATE_SOFT_READY:
        return False
    return CAP_LADDER.index(profile.cargo_class) <= config.wedge_cap_ladder_depth


def strip_reserved_for(profile: cls.ItemProfile, state: WedgeState,
                       model: ContainerModel, config) -> bool:
    """May this item occupy the strip at all?

    While the staircase is growing the strip belongs to cargo that can be a
    step; once it is soft-ready it belongs to the cap ladder.  Ordinary cargo
    gets in only when the zone is CLOSED.
    """
    if state.state == STATE_CLOSED:
        return True
    if state.state in (STATE_RAW, STATE_STAIRCASE):
        return step_capable(profile, model, config)
    return cap_allows(profile, state, config)
