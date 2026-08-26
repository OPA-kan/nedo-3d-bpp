"""Tunable constants for the rule-alpha Layer 1 prototype.

Everything a rule depends on lives here so that a scenario run can dump the
exact thresholds it used into its diagnostics.  No value in this file is tuned
against a competition score; they are starting points chosen so that the
resulting board is easy to look at and argue about.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class RuleAlphaConfig:
    # ------------------------------------------------------------------
    # Clearances.  Mirrors of the official validator margins, kept local so
    # rule-alpha never has to import the production policy just for numbers.
    # ------------------------------------------------------------------
    inclusion_clearance: float = 0.016
    """Distance every box corner keeps from every container plane when the
    *action* pose is tested.  The official ``check_inclusion`` uses a margin of
    -0.005, so a box resting exactly on the floor plane would be refused."""

    floor_action_lift: float = 0.020
    """How far above the floor a floor placement is *commanded*.  It falls this
    far and settles; the recorded pose is the settled one.  Must exceed the
    official 5 mm inclusion margin, and stay under the validator's 0.05 m
    "direct rest" window so the transport sweep stays low."""

    settled_wall_clearance: float = 0.006
    """Margin the *settled* pose keeps from the walls and the chamfer."""

    transport_clearance: float = 0.016
    """Official 15 mm safety margin plus a float32 guard."""

    settled_clearance: float = 0.026
    """Lateral gap kept from already-settled items (transport + settle drift)."""

    contact_tolerance: float = 0.006
    """Vertical slack that still counts as "resting on"."""

    min_support_ratio: float = 0.60
    """Minimum share of a footprint that must sit on a real support surface."""

    # ------------------------------------------------------------------
    # Item classification
    # ------------------------------------------------------------------
    elongation_tau: float = 1.80
    """rho = max(l,w,h) / median(l,w,h).  rho >= tau  =>  elongated item."""

    tipping_normal: float = 1.5
    """R = dz / min(dx,dy).  Below this an orientation is treated as normal."""

    tipping_wall_preferred: float = 2.0
    tipping_wall_strong: float = 3.0
    """R bands from the spec: [1.5,2) wall preferred, [2,3) strongly preferred,
    >=3 corner/wall + backing required (never free-standing)."""

    max_freestanding_ratio: float = 2.0
    """An orientation with R above this may only be used against a wall or a
    backing item."""

    min_floor_footprint_fraction: float = 0.60
    """A plain floor placement must use a pose worth at least this share of the
    item's best footprint.  This is what stops "whatever still fits" from
    standing boxes on end in the middle of the foundation.  Elongated items and
    wall-front / slope roles are exempt: for them height is the point."""

    max_shelf_tipping_ratio: float = 2.2
    """Shelves are shallow and get bumped: cap how tall a shelf item may stand."""

    # ------------------------------------------------------------------
    # Zone layout of a normal container (fractions of the usable floor)
    # ------------------------------------------------------------------
    back_band_fraction: float = 0.42
    """Depth of the "big hard foundation" band measured from the back wall."""

    edge_band_fraction: float = 0.26
    """Width of the left (soft) and right (priority) edge bands."""

    corridor_width_fraction: float = 0.46
    """Width of the central transport corridor near the opening."""

    corridor_depth_fraction: float = 0.34
    """How far the corridor reaches in from the opening."""

    corridor_release_fill: float = 0.62
    """Floor coverage above which the corridor stops being protected.  Below
    this the corridor is a hard veto; above it, only a soft penalty."""

    # ------------------------------------------------------------------
    # Slope / wall-front
    # ------------------------------------------------------------------
    wall_front_band: float = 0.10
    """A hard item whose left face lands this close to the chamfer foot counts
    as slope wall-front."""

    wall_front_target_ratio: float = 0.5
    """Diagnostic target from the spec: build the slope wall to about half the
    container height, then stop pushing it higher."""

    wall_front_min_height: float = 0.25
    """Below this an item is not worth spending on the wall front."""

    wall_front_max_height_shelf_fraction: float = 0.5
    """Cap on wall-front height, as a share of the gap between the floor and
    the shelf above the slope strip.  A taller piece has nowhere to go: it
    cannot be carried past the small shelf, and it spends a large item on
    structure.  Above this cap the item is ordinary tall cargo and belongs on
    the perimeter instead."""

    tall_perimeter_max_footprint_fraction: float = 0.18
    """An item whose best footprint exceeds this share of the usable floor is
    prime foundation material and lies flat, however tall it could stand.  The
    perimeter is for cargo that is awkward to lay down, not for the big flat
    boxes the foundation is made of — without this cap a stream of large hard
    cargo stands every item on end and Layer 1 has no flat surface left."""

    tall_perimeter_min_height: float = 0.30
    """A standing pose at least this tall may go against the left/right
    perimeter or the back wall instead of lying flat.  This is the fallback for
    cargo that is too tall to be wall-front material but not slender enough to
    be classified elongated: without it such an item is simply laid down, which
    spends floor area to store air above it."""

    wall_front_strip_fraction: float = 0.22
    """Share of the usable floor length reserved for the slope wall front.  The
    soft edge zone starts just inside it, because on this ULD the chamfer and
    the spec's soft edge both want the -X side."""

    wall_front_max_footprint_fraction: float = 0.13
    """An item whose best footprint exceeds this share of the usable floor is
    foundation material and is never spent on the wall front."""

    wall_front_depth_target: float = 0.85
    """Stop pushing wall-front placements once they span this share of the
    container depth: the wall is a wall, not a second foundation."""

    # ------------------------------------------------------------------
    # Chamfer wedge: RAW -> STAIRCASE -> SOFT_READY -> CLOSED
    # ------------------------------------------------------------------
    wedge_overhang_fraction: float = 0.25
    """How far a staircase step may reach past the support under it, as a share
    of its own width.  The official 0.6 support floor allows 0.4w; this is
    deliberately under that, because the centre of mass and the settle step are
    not modelled exactly."""

    wedge_step_max_footprint_fraction: float = 0.10
    """Only small cargo climbs the staircase.  A big box spent here is a big
    box missing from the foundation."""

    wedge_step_max_height: float = 0.35
    """Each step stays low.  The point of a staircase is that no single item
    has to be tall enough to bridge the wedge on its own, which is what lets
    the wall front stay low and keep the transport lane open."""

    wedge_min_step_gain: float = 0.03
    """Below this much extra leftward reach a further step is not worth its
    volume; the remainder becomes the soft disposal zone."""

    wedge_step_probe_width: float = 0.40
    """Nominal step width used to estimate the next step's gain before an item
    is in hand."""

    wedge_step_probe_height: float = 0.20
    """Nominal first-step height used to ask what the *second* step would win,
    since the first can never overhang."""

    wedge_cap_ladder_depth: int = 1
    """How far down CAP_LADDER (soft, soft+priority, priority, plain) the top of
    the staircase will serve while the zone is still reserved."""

    wedge_weight_step: float = 1.0
    wedge_weight_cap: float = 0.6
    wedge_weight_area: float = 0.6
    wedge_weight_fill: float = 0.9
    wedge_weight_bottleneck: float = 0.6
    """R = w_step p_step + w_cap p_cap + w_area A_remaining - w_fill F - w_bn B.
    Committing the strip to ordinary cargo is irreversible while withholding it
    costs only the volume held now, so the score prices the option an action
    would destroy rather than predicting arrivals."""

    wedge_min_step_share: float = 0.10
    """Below this share of step-capable cargo the strip is not worth holding:
    cap customers cannot use a staircase that nothing can build."""

    wedge_reserve_threshold: float = 0.25
    """Keep the strip reserved while R exceeds this."""

    slope_pocket_margin: float = 0.004
    """Extra clearance demanded inside the reserved slope pocket."""

    slope_pocket_min_penetration: float = 0.06
    """How far left of the floor limit a box must reach to count as a genuine
    slope-pocket filler rather than a box that happens to overhang."""

    slope_pocket_min_share: float = 0.50
    """...and how much of its width has to be inside the wedge."""

    # ------------------------------------------------------------------
    # Hole / flatness heuristics
    # ------------------------------------------------------------------
    grid_cell: float = 0.02
    """Diagnostic heightmap resolution."""

    candidate_grid_cell: float = 0.04
    """Coarser grid used while scoring candidates (speed)."""

    max_new_interior_hole: float = 0.06
    """m^2.  A candidate that opens an interior hole bigger than this is vetoed
    while any alternative survives."""

    plateau_height_tolerance: float = 0.03
    """Cells within this height of each other belong to the same plateau."""

    # ------------------------------------------------------------------
    # Priority container policy
    # ------------------------------------------------------------------
    priority_container_hard_budget: float = 0.45
    """Share of a priority container's usable floor that plain hard cargo may
    occupy as foundation before it is refused (so priority cargo keeps room)."""

    # ------------------------------------------------------------------
    # Search limits
    # ------------------------------------------------------------------
    max_candidates_per_orientation: int = 220
    max_anchor_x: int = 26
    max_anchor_y: int = 22

    shortlist_size: int = 60
    """How many candidates get the expensive free-space features."""

    residual_rect_shortlist: int = 24
    """How many get the largest-residual-rectangle measurement on top."""

    zone_guard_fraction: float = 0.15
    """A plain hard item may not cover more than this share of its footprint
    with a reserved soft / priority edge strip.  Low on purpose: several items
    each nicking a corner of a strip add up to a strip that is gone."""

    frontier_item_contact_weight: float = 2.0
    """How much more a candidate that packs against already-settled cargo is
    worth than one that hugs a far wall.  Extending the packed frontier is what
    keeps the leftover space in one piece at an edge, instead of a strip up the
    middle of the container."""

    zone_reference_share: float = 0.25
    """Share of the declared stream (by footprint) at which a reserved edge
    strip reaches full width.  Below that it shrinks proportionally; a class
    that is absent from the manifest gets no strip at all."""

    # ------------------------------------------------------------------
    # Layer 1 scope
    # ------------------------------------------------------------------
    layer1_only: bool = True
    """Restrict supports to the floor and the shelves.  The single exception is
    a slope-infill candidate, which may rest on a hard item inside the pocket."""

    allow_slope_infill_on_items: bool = True

    def to_dict(self) -> dict:
        return asdict(self)


DEFAULT_CONFIG = RuleAlphaConfig()
