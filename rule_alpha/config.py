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
    """Kept for diagnostics and for the wedge's own reach arithmetic.  It is
    *not* an official rule -- the competition has no support-ratio test -- and
    it is no longer what accepts or refuses a placement.  See ``com_margin``."""

    com_margin: float = 0.030
    """How far inside the support polygon the centre of mass must project.

    A rigid body topples exactly when its centre of mass leaves the convex hull
    of its contact patches, so that -- not a contact-area fraction -- is the
    criterion.  It predicts both measured shapes: a cantilever is stable to
    ``o = w/2`` (measured: clean at 0.50, tips at 0.60) and a bridge is stable
    however small each individual contact is (measured: accepted at a single
    contact of 0.24).  The margin is the allowance for the release drop and the
    settle transient, which the static criterion does not model."""
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

    # ------------------------------------------------------------------
    # Layer 2: grow hard support from hard support
    # ------------------------------------------------------------------
    layer2_enabled: bool = True
    """Allow placements on normal-hard item tops."""

    layer2_family_quota: int = 12
    """How many candidates each proposal family keeps *before* the families are
    unioned.  Layer 1's single shortlist sorts everything by depth and truncates,
    which is how five separate rules there ended up no-ops -- they were written
    downstream of a decision the shortlist had already made.  A bridge must not
    have to out-depth a floor candidate to be considered at all."""

    max_orientations_layer2: int = 3
    """How many poses a Layer 2 proposal may try.  Its own ordering, because a
    bridge wants the widest flattest pose and the floor policy would not have
    offered it."""

    layer2_max_level_step: float = 0.45
    """A terrace or bridge may sit at most this far above the support it grows
    from.  Higher than that is not growth, it is a new tower."""

    # ------------------------------------------------------------------
    # Typed cargo: the shelf first, and the right front when it overflows
    # ------------------------------------------------------------------
    shelf_own_anchors: bool = True
    """Offer a shelf placement anchors measured from the shelf itself.

    The anchor set was built from the floor rect and shared with every surface,
    so a shelf candidate was never offered the shelf's own back corner, nor a
    position flush beside something already up there.  That is why shelf cargo
    sat at the front and used a fifth of the area."""

    shelf_residual_key: bool = True
    """Rank shelf candidates by what they leave behind, not just by footprint.

    Back-most feasible, then the largest free rectangle remaining, then least
    fragmentation.  A shelf is scarce in area: landing in the middle of an
    empty one can consume a fifth of it and destroy all of it."""

    shelf_depth_bucket: float = 0.05
    """"Back-most" to within this much is not a real preference.  Comparing
    depth exactly means the residual-area term never decides anything."""

    typed_floor_right_front: bool = True
    """Soft and priority that reach the floor go to the right front.

    Hard grows from the back and especially the back right, so typed cargo
    wants the opposite corner -- the last place hard wants, and the first place
    a person reaching in can get to.  The left band is not an option: it is the
    chamfer's, and the wall front is already there."""

    hard_avoids_front: bool = True
    """Keep normal-hard off the front band while it has anywhere else to go.

    The right front is where typed cargo goes when the shelf overflows, and the
    front centre is the way in.  Hard is the class with somewhere else to be --
    it grows from the back -- so it is the one that should yield."""

    hard_front_band: float = 0.35
    """How much of the depth, measured from the opening, counts as the front
    band hard should yield."""

    layer2_max_layers: int = 2
    """How many layers of cargo may be stacked, floor included.

    Two means: the floor layer, and one layer on top of it.  The wedge
    staircase is exempt -- it is not a stack, it is a ramp, and each step rests
    on the one below by construction."""

    typed_front_right_slack: float = 0.25
    """How far off the best right-front placement a typed floor candidate may
    still sit.  In units of the normalised corner distance, so 0.25 is a
    quarter of the way back across the container."""

    wedge_approach_band: float = 0.30
    """How far in from the chamfer foot counts as the *approach* to the wedge.

    The chamfer runs the full depth, and the validator sweeps straight in along
    ``y`` at the target ``x``, so everything a wedge step or an upper terrace on
    that side will ever be reached through shares this band of ``x``.  Whatever
    stands here decides what can still be delivered behind it."""

    wedge_approach_max_height: float = 0.45
    """How tall an ordinary placement in that band may be.

    Standing cargo up here is the single worst thing to do on this board: it
    buys one item's volume and pays for it with access to the whole wedge side
    behind and above it.  Laid flat, the same item gives a low top that a
    terrace can grow from.  This does *not* apply anywhere else -- tall cargo
    on the right perimeter or the back wall is still wanted, because nothing is
    delivered through those columns afterwards."""

    wedge_top_must_advance: bool = True
    """While the wedge is growing, a box resting on the strip has to climb it.

    A terrace is proposed flush with a hard top and knows nothing about the
    chamfer to its left, so it kept landing on the top step and sitting back
    from the reach that step had won -- capping the staircase with a box that
    gained no ground.  The cap ladder is exempt: taking the top is what soft
    cargo is being held for."""

    wedge_bottleneck_is_local: bool = True
    """Price the wedge reservation by *its own* lane, not the central corridor.

    Delivery is a straight sweep in y at the target's own x, so what stops a box
    reaching the chamfer strip is what stands in the strip's columns.  Charging
    it for the central corridor made the reservation self-defeating: the more
    Layer 1 packed the middle, the sooner the wedge closed, and on the shipped
    boards it closed with the strip still empty and 0.16 m of reach unspent."""

    wedge_bridge_strip: float = 0.25
    """How far in from the chamfer foot a hard top still counts as wedge-side,
    and so as something a wedge bridge can reach out from."""

    hole_fill_enabled: bool = True
    """Aim candidates at the gaps one layer could not close.

    Every Layer 1 anchor is derived from the edge of something already packed,
    and the pose offered there is whichever the orientation policy ranked first.
    Neither of those knows the *shape* of the gap, so a 0.55 x 0.30 slot never
    sees the 0.55 x 0.30 pose of a 0.30 x 0.55 box: no rule refused it, nothing
    proposed it.  This family finds the pocket first and picks the pose to
    match, which is where the 90-degree yaw comes from.
    """

    hole_fill_min_area: float = 0.05
    """Smallest pocket worth aiming at, in m^2.  Below this nothing in a real
    manifest fits anyway and the candidates are pure cost."""

    hole_fill_min_enclosure: float = 0.50
    """How much of a pocket's rim must be wall or higher ground before it counts
    as a hole rather than as ordinary open floor.

    The opening deliberately does not count as rim: a slot that runs out to the
    door is still a slot, but the whole front of an empty container is not."""

    hole_fill_max_rect_share: float = 0.20
    """Largest pocket, as a share of the usable floor, that still counts as a
    hole rather than as open floor.

    Without it the criterion collapses: an empty container's floor is walled on
    three sides, so it scores as fully enclosed.  What actually distinguishes a
    hole is that the edge-derived anchors keep missing it, and they only miss
    small ones -- a large clearing is what they are good at."""

    hole_fill_min_coverage: float = 0.55
    """How much of the pocket the box has to take for the placement to earn the
    hole-fill archetype.

    This is what stops the family from degenerating into "anywhere there is
    room": a small box in a large clearing covers little of it and is judged as
    ordinary floor cargo, while the same box in a slot its own size is exactly
    the placement this family exists to find."""

    hole_fill_min_headroom: float = 0.10
    """A pocket with less than this much space above it can hold nothing."""

    hole_fill_rects_per_region: int = 5
    """How many rectangles to peel off one free region before moving on.

    The first is usually the open middle and is thrown away as room; the pockets
    are the lobes left behind it, so stopping at one finds nothing."""

    hole_fill_max_holes: int = 8
    """Pockets offered per decision, largest first."""

    hole_fill_tier_tolerance: float = 0.01
    """How close two poses' heights have to be to count as equally flat.

    Poses are offered a pocket in tiers of equal height, flattest tier first, so
    a box is stood on end only where nothing lying down would go in."""

    layer2_bridge_level_tolerance: float = 0.06
    """How far apart two hard tops may be and still be offered as a pair to
    bridge across.

    A rigid box with a flat underside only *touches* the higher of two supports,
    so grouping strictly by contact tolerance finds almost nothing: cargo heights
    do not coincide to within 6 mm, and 12 of 13 levels on a real board are
    singletons.  Spanning the lower one anyway is still worth proposing, because
    the merge Layer 2 wants is of the resulting *tops* -- what it can build on
    next -- not of the supports.  Whether it stands up is then decided by the
    support polygon rather than by this number.
    """

    plateau_merge_min_gain: float = 0.02
    """Minimum growth in the largest connected hard plateau for a bridge to be
    worth the item.  Below this it is an ordinary placement wearing a costume."""

    corridor_release_fill: float = 0.62
    """Floor coverage below which the corridor is a hard veto.  Kept alongside
    the reachability price rather than replaced by it: the price is evaluated
    on a shortlist that is already back-biased, so it almost never charges
    anybody, while this crude threshold is what actually keeps the opening
    clear early.  Set it to 0.0 to run on the price alone."""

    # ------------------------------------------------------------------
    # Back-first foundation, and reachability priced above coverage
    # ------------------------------------------------------------------
    back_first_slack: float = 0.10
    """How far in front of the deepest *good* placement an ordinary foundation
    candidate may still sit.  The principle is not "prefer the back" as a
    tie-break but "do not advance without a reason": while a good legal
    placement remains further in, a candidate this much closer to the opening
    is refused outright."""

    back_first_hole_tolerance: float = 0.012
    """A back placement only counts as *good*, and so only holds the frontier
    back, if it opens no more interior hole than this.  Otherwise "deepest"
    would be satisfied by wedging something into a corner and leaving a hole in
    front of it."""

    stranded_veto_area: float = 0.12
    """A floor placement that strands more than this much still-reachable free
    floor is refused while any alternative exists.  This replaces the old
    coverage-triggered corridor release: the corridor is protected early
    because blocking it is expensive *in reachability*, and released late for
    the same reason, without a threshold having to name the moment."""

    reach_probe_heights: tuple = (0.0, 0.20, 0.40)
    """Working heights at which the approach is priced.  Asking only at a
    candidate's own top is vacuous -- a box travelling at 0.40 clears a wall
    whose top is 0.40, so a wall never seals anything at its own height.  What
    a wall actually costs is delivery to the *lower* ground behind it, so the
    question has to be asked at the heights a later item might arrive at."""

    sealed_veto_area: float = 0.30
    """The same question as ``stranded_veto_area`` asked across
    ``reach_probe_heights`` and taking the worst: how much ground that was
    still usable *at some working height* does standing this tall here seal
    off?  A tall box with lower, still-open ground behind
    it is a wall across the approach, because the validator sweeps straight in.
    A tall box with ground behind it that is already built on above its top
    seals nothing and is not charged -- which is the difference between pricing
    a wall and merely punishing height."""

    # ------------------------------------------------------------------
    # Large sets the frontier, small follows it
    # ------------------------------------------------------------------
    foundation_large_quantile: float = 0.60
    """Hard cargo at or above this quantile of the manifest's hard footprints
    is *frontier material*: it is placed back-first and densely, and is not
    spent standing up.  Measured against the manifest rather than an absolute
    area because a stream of uniformly small boxes still has a largest box, and
    that box is still the one that should set the frontier."""

    foundation_small_quantile: float = 0.40
    """Below this quantile hard cargo is a *follower*: it fills gaps, clusters
    at the back, and is refused a placement that would break the free rectangle
    the outstanding large cargo still needs."""

    compaction_min_gain: float = 0.008
    """Do not bother sliding a chosen box less than this."""

    compaction_iterations: int = 7
    """Bisection steps when searching the furthest legal travel.  Seven gets
    within a millimetre of the limit over the container depth."""

    perimeter_prefers_depth: bool = True
    """Whether a tall perimeter item is chosen by how far back it can stand
    rather than by how tall it is."""

    frontier_prefers_lying: bool = True
    """Whether frontier material is stopped from standing up while a foundation
    placement exists.  The tall-perimeter *role* already has its own footprint
    cap, so this is a second, blunter filter and worth being able to switch
    off."""

    small_hard_fit_guard: bool = True
    """Whether a follower may destroy the last free rectangle that still admits
    the largest outstanding frontier item."""

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
    wedge_overhang_fraction: float = 0.40
    """How far a staircase step may reach past the support under it, as a share
    of its own width.  There is no official support floor -- that was
    rule-alpha's own rule -- and the measured limit is ``o = w/2``, where the
    centre of mass leaves the support polygon.  This stays under it: a step
    lands on the step below, whose own top is not perfectly flat once settled,
    so the static criterion is optimistic here in a way it is not on the
    floor."""

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

    wedge_min_step_count: int = 3
    """...or simply this many step-capable items, whatever their share.

    A staircase needs a number of steps, not a proportion of the manifest.  On
    two of the shipped boards three step-capable items out of 34 scored 0.088
    against a 0.10 share gate and the zone closed before the first placement --
    with three perfectly good steps waiting in the stream."""

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
