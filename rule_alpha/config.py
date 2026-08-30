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

    ground_before_growth: bool = False
    """Finish the floor before growing upward.

    The Layer 2 rungs sit above every floor archetype, so from the moment a
    terrace is possible the item goes up rather than completing the ground
    layer -- and the official boards show five to seven items on a 2.03 m^2
    floor.  Switchable so the two orders can be compared rather than argued
    about."""

    prefilter_dead_candidates: bool = True
    """Drop candidates a cheap veto will certainly refuse before the shortlist
    truncates, not after.

    The shortlist keeps the deepest few floor candidates.  Once the back is
    full the deepest remaining positions are exactly the ones the corridor and
    low-footprint vetoes refuse, so the shortlist hands the vetoes a pool that
    is entirely dead: on task 000 from the eighth decision onward, 321 floor
    candidates generated, 40 shortlisted, none surviving -- with 1.31 m^2 of
    floor still empty.  This is the sixth time in this branch that a rule
    downstream of the truncation could not undo it; the answer is always to
    move the decision upstream, and both of these tests read only cheap
    features, so they can move."""

    layer2_anchor_clamp: float = 0.005
    """How far out of bounds a Layer 2 anchor may be and still be pulled back.

    Settle-scale: the whole displacement budget measured over both official
    tasks is 0.1 mm median and 2.9 mm at worst.  Swept, and it makes no
    difference -- 2 mm, 5 mm, 10 mm and 30 mm all give the same board, so every
    anchor the clamp rescues is within 2 mm and the bound is a guard rather than
    a tuning knob."""

    back_reachability_guard: bool = True
    """Refuse a placement that would rise above the terrain behind it.

    Delivery is a straight y-sweep at the target's own x, so a box taller than
    what stands behind it seals that column at every height between them.  The
    only rule that asked this was scoped to floor surfaces, normal-hard cargo, a
    0.35 m band at the opening, and only while the front was unreleased -- which
    is none of the cases that matter by the time the board is half built.

    Measured on task 000's finished board: the largest free rectangle above the
    shelf is 0.744 x 0.434 m at z 0.850, at the back, and two of the refused
    item's poses fit it.  Every approach dies `transport-hits-packed-item`,
    against a tower at y[-0.171, +0.229] built to 1.43 m in the same x column
    while the back of that column stops at 0.850.

    Swept over the band and the slack::

        band   task 000        task 001        items   fill sum
        off    24 / 28.157     25 / 27.184      49      55.341
        0.35   24 / 28.157     25 / 27.184      49      55.341
        0.55   24 / 28.157     24 / 25.880      48      54.037
        0.70   24 / 28.157     27 / 29.793      51      57.949
        0.90   24 / 28.157     27 / 29.793      51      57.949

        slack  (at band 0.70)                   items   fill sum
        0.00                                     51      57.949
        0.05                                     51      57.949
        0.10                                     51      57.949
        0.20                                     50      56.645

    Two items and 2.6 fill, and nothing lost anywhere: task 000 does not change
    at all, so the guard pays entirely on task 001.  0.70 and 0.90 agree, so the
    front half is the whole of it; the slack sits on a plateau three values
    wide."""

    back_guard_band: float = 0.70
    """How far in from the opening the guard applies, in metres.

    The container is about 1.38 m deep, so 0.70 is the front half.  At 0.35 it
    is the same band 4g uses; larger values push it toward strict back-to-front
    building."""

    back_guard_slack: float = 0.05
    """How far above the terrain behind it a placement may still rise, in m."""

    layer2_clamps_anchors: bool = True
    """Pull a Layer 2 anchor back inside the container instead of losing it.

    Anchors are generated flush with the edge of the box they stand on, and a
    box that settled a fraction of a millimetre outward carries every anchor on
    it out of bounds.  At step 2 of task 000 item 3 rests 0.45 mm further +x
    than commanded, its top's +x edge lands at 0.9445 against a usable limit of
    0.9440, and all nine Layer 2 proposals fail `outside-container` -- the rung
    that decides most placements generates nothing at all.  The replay never
    sees it, because the replay never settles anything.

    On its own the repair splits the two tasks -- 23/25.521 against 23/29.484 on
    task 000, 25/27.184 against 23/25.880 on task 001 -- because Layer 2 coming
    back pushes task 000 off the floor and shelf rungs that were, by luck, doing
    better there.  Part of that 29.484 was earned by the bug.  It looked like a
    change not worth shipping until the landscape underneath it was re-examined:
    with the shelf veto's fallback turned off as well it is 24/28.157 and
    25/27.184, three more items than the shipped board at the same total fill.

    It also decides whether the analytic replay is worth anything.  Reproduced
    placements go from 5% to 29% on task 000 and 5% to 19% on task 001, and rank
    correlation with the official score from +0.42 to +0.79 and +0.27 to +0.55.
    The replay was mostly measuring a planner whose Layer 2 rung was silently
    dead."""

    grid_always_from_packed: bool = False
    """Build the height map from packed items even when placements exist.

    The replay and the live agent were building it two different ways from the
    same board state -- `build_floor_grid` off the planner's own placement
    records, `grid_from_packed` off the observation -- which is a candidate for
    why the replay stops diverging from physics only when the pool is a single
    item.  A switch so the question can be measured rather than argued."""

    pool_order_demotes_elongated: bool = False
    """Try elongated hard cargo after the rest of the hard cargo.

    One of the three points on which the replay's pool order disagreed with the
    agent's.  Defaults to the agent's answer (no demotion) so that unifying them
    leaves the shipped board untouched and only the replay changes."""

    pool_order_breaks_on_mass: bool = False
    """Break pool-order ties on mass before falling back to pool position.

    The second of the three.  Same default and same reason."""

    shelf_skip_needs_column: bool = True
    """Exclude an item from the floor map only if it stands over a shelf.

    The test was height alone -- underside at or above the shelf plane -- which
    is right for shelf cargo and wrong for anything else that tall.  task 000's
    only shelf is the small one, 0.44 m of a 1.92 m length at the chamfer end,
    so the height test erased floor-stacked boxes at the opposite end and blinded
    every grid-derived rule above 0.785 m.  `free_rectangles` then offered a
    0.464 x 0.674 rectangle at z 0.82 that was solid cargo (item 22 occupies
    0.810-1.060 there), the last resort proposed six anchors inside it, all six
    came back `overlaps-packed-item`, and the episode ended with an empty pool."""

    shelf_column_fraction: float = 0.5
    """How much of a box's footprint must stand over a shelf to count as its."""

    last_resort_all_poses: bool = False
    """Let the last resort escalate to standing poses when nothing flat fits.

    Its own docstring promises "whatever pose that takes", but the tier filter
    cut four fitting poses down to one, and when that one failed validation the
    rectangle was abandoned with the other three never tried -- which is how
    task 000 ended with an empty pool while three rectangles held poses that fit.

    Escalation is a second sweep of the whole board rather than a wider search
    within each rectangle.  Deciding per rectangle takes a standing pose here
    when a flat one fits the next one along, which measured +2 items on task 000
    and -3 on task 001; deciding over the board keeps the gain without the
    loss."""

    floor_prefers_flat: bool = False
    """Refuse a floor placement by a box taller than the manifest can pave with.

    The official scorer requires every corner to clear every plane by
    `inclusion_margin` (-0.005), and the container floor is one of those planes,
    so an item settled on the floor -- lowest corner exactly on it -- counts
    zero towards the fill score.  Verified per item against `evaluate()` on both
    tasks and under both agents: the dropped items are exactly the ones touching
    the floor (6/6 and 7/7 for rule-alpha, 3/3 and 4/4 for the incumbent), worth
    28-36% of everything placed.  So a square metre of floor costs the height of
    whatever paves it, and paving with a tall box wastes the difference.

    A preference with a fallback: with `max_space: 1`, a forfeited box still
    beats the unplaced one that would end the episode.

    Off, because measured it does not pay -- and the fallback is why.  On task
    000 the veto is a *no-op at every tolerance including zero*: at each floor
    decision there is no other surface to send the box to, so the fallback fires
    and the tall box paves anyway.  On task 001 it fires and costs items::

        tolerance  task 000        task 001
        off        23 / 29.484     23 / 25.880
        0.000      23 / 29.484     19 / 25.270
        0.005      23 / 29.484     19 / 25.270
        0.020      23 / 29.484     18 / 22.662
        0.040      23 / 29.484     20 / 22.469

    The tax is real; avoiding it is not worth what it costs.  Cutting the
    forfeit does cut the counted volume by more: on task 000 the paving order
    takes the forfeit from 0.458 to 0.357 m^3 and the counted volume from 1.181
    to 0.788.  The flat boxes are also the best stacking and gap-filling
    material, and the big ones are what build a plateau wide enough to stack on
    at all, so spending the flat ones on the floor costs the structure more than
    the tax it saves."""

    floor_paving_tolerance: float = 0.02
    """How much taller than the cheapest paving a floor box may still be, in m.

    task 000's hard classes lie 0.24, 0.25 and 0.27 m flat, so this decides
    whether the rule separates all three or only the extremes."""

    floor_paving_order: bool = False
    """Order the hard cargo flattest-first rather than largest-footprint-first.

    The companion to `floor_prefers_flat`: the veto can only send a tall box
    upstairs if something has already built the stairs, so the cheap paving has
    to arrive while the floor is still the only surface there is.

    Off, measured::

        arm            task 000        task 001
        neither        23 / 29.484     23 / 25.880
        veto only      23 / 29.484     18 / 22.662
        order only     19 / 19.666     22 / 23.572
        both           19 / 18.349     22 / 22.075"""

    wall_front_order_quota: int = 0
    """How many items the wall-front group may claim at the head of the stream.

    The group is a reservation for the staircase, but its test is a footprint
    budget, so on task 000 it captured twelve of the twenty-five normal-hard
    items -- every 0.55 x 0.40 box, footprint 0.220 against a 0.2638 m^2 budget
    -- and put all twelve ahead of the four 0.75 x 0.56 boxes (footprint 0.420)
    that are the foundation the design wants down first.

    Swept, and the answer is that it should claim none::

        quota  task 000        task 001
        off    20 / 23.502     23 / 26.373
        0      23 / 29.484     23 / 25.880
        2      16 / 21.070     20 / 20.161
        3      14 / 20.758     19 / 18.857
        4      13 / 16.600     19 / 20.161
        6      16 / 20.563     14 / 13.940
        8      12 / 10.931     21 / 22.769   (and one invalid placement)

    Every intermediate size is worse than both ends, which is the shape of a
    reservation that is not paying for itself at any size rather than one that
    is merely mistuned.  The reading: which items make good steps is a
    *placement* question, and the placement rules already answer it from the
    board.  Front-loading them in the stream only guarantees that the
    foundation cargo arrives after the floor is already fragmented.  So the
    stream is plain foundation order -- largest footprint first -- and the
    staircase is built by the wedge rules out of whatever is in hand.

    Negative disables the quota and restores the old grouping."""

    plateau_veto_has_fallback: bool = True
    """Let the plateau *shape* test yield when it would refuse the item entirely.

    Measured on the step that ends task 000: ten candidates reached the veto
    ladder and all ten died on `no-plateau-to-build-on`, so one hand-set
    threshold ended the episode.  Task 001 closes the same way -- seventeen in,
    zero out, twelve to `overhangs-the-shelf` and five to this.  With
    `max_space: 1` a veto with no fallback is not a guard on a bad placement, it
    is the end of the run, and these two were the only vetoes in the ladder that
    had none.

    The layer *cap* keeps its absolute form: a third layer is a third layer.
    Only the shape condition yields, and only to the closest near miss, ranked
    by support area times coverage."""

    shelf_veto_has_fallback: bool = False
    """Let the shelf-overhang test yield rather than refuse the item entirely.

    Shipped on when it was measured against a board whose Layer 2 rung was dead
    for anything standing on a settled box.  With `layer2_clamps_anchors` there
    are real alternatives again, and taking a 60%-supported shelf place ahead of
    them costs more than the item it saves::

        arm                    task 000        task 001     items   fill
        clamp off (was)        23 / 29.484     23 / 25.880    46    55.364
        clamp                  23 / 25.521     25 / 27.184    48    52.705
        clamp, no shelf fb     24 / 28.157     25 / 27.184    49    55.341

    The plateau veto keeps its fallback: turning that off under the clamp is
    20/22.886 and 23/24.576, worse on both."""

    shelf_fallback_min_fraction: float = 0.60
    """How much of the underside still has to be on the shelf for the fallback.

    A fallback that accepts any overhang would drop cargo off the shelf edge, so
    the yield has its own floor, well under `shelf_min_support_fraction` (0.90)
    but well over nothing."""

    terrace_keeps_level: bool = False
    """Break terrace ties by the room the box leaves at its own level.

    ``terrace-extension`` chooses nine of the nineteen placements on task 000 --
    it is the rung that actually decides -- and its key asked only for plateau
    area.  Nothing in it noticed whether the level the box lands on is still a
    shape anything can use afterwards, which is the same defect the floor
    row-tiling term was written for, on a rung that is never reached.

    Off, because measured it does not pay.  The term is live (the boards differ,
    which is more than the previous five changes managed) and it discriminates
    as designed -- on task 000's item 4 the surviving poses leave 0.064, 0.090,
    0.064, 0.032 and 0.0 m^2 -- but ranking by it costs more than it returns::

        bucket   task 000            task 001
        off      19 / 21.677         21 / 20.461
        0.005    19 / 21.677 (same)  21 / 20.461, different board
        0.010    19 / 21.677 (same)  21 / 20.461, different board
        0.020    19 / 21.677, moved  19 / 17.350
        0.050    19 / 21.677, moved  20 / 18.655
        0.100    19 / 21.677, moved  18 / 17.350

    So "leave the widest rectangle beside you" is not what a terrace should be
    choosing on these manifests: task 000 is indifferent to it and task 001
    loses two items to it.  Kept, off, with its tests, because the finding is
    worth more than the code -- and because the reason it read as a no-op for
    five runs was a wiring bug, not this result.

    Off, ``level_residual`` is left at 0.0 for every candidate and the key
    reduces to the plateau ordering, which is what makes the A/B a fair one."""

    plateau_gain_bucket: float = 0.02
    """How close two plateaus have to be to count as equally good, in m^2.

    Compared exactly, the plateau settles almost every terrace by itself and no
    later term is ever consulted -- which is how the key came to have no
    opinion about the space it leaves behind.  Measured on task 000, a terrace
    decision offers between 2 and 7 surviving poses whose plateaus differ by as
    little as 0.0032 m^2, so the step has to be coarse enough for those to fall
    through."""

    row_tiling: bool = True
    """Price the floor a placement strands in its own row.

    A row is a fixed width and what tiles it is a sequence of poses.  The floor
    is 1.472 m across: two 0.55 m boxes leave 0.346 m, too narrow for anything
    in the manifest, while 0.55 + 0.40 + 0.40 leaves 0.070.  Those poses have
    identical footprints, so every footprint-ranked key scored them equal and
    the tie fell to depth -- to a term that cannot see which row tiles."""

    row_min_useful_width: float = 0.35
    """Fallback for the narrowest run of free floor still worth having.

    Replaced by the real figure -- the narrowest orientation among the hard
    cargo still to come -- as soon as the manifest is read."""

    min_floor_footprint_fraction: float = 0.60
    """A plain floor placement must use a pose worth at least this share of the
    item's best footprint.  This is what stops "whatever still fits" from
    standing boxes on end in the middle of the foundation.  Elongated items and
    wall-front / slope roles are exempt: for them height is the point."""

    shelf_min_support_fraction: float = 0.90
    """How much of a shelf placement's footprint must actually be on a shelf.

    The support polygon alone permits an overhang of half the box's width, and
    on the small shelf -- 0.44 m wide, narrower than most of the cargo -- that
    is what happened: 15 of 52 shelf placements hung over the edge, one by
    0.486 m.  They stay up, but they cap the open floor below at shelf height,
    and that floor is where tall cargo has to go, because the main shelf
    already caps the back half of the container at 0.765 m of headroom."""

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
    shelf_takes_hard: bool = True
    """Offer the shelf to normal-hard cargo as well, not only to soft.

    The shelf is a second floor: 1.87 m^2 against the floor's 2.03, with
    0.725 m of headroom above it against the floor's 0.765.  Offering it only
    to soft cargo made its use a side effect of how much soft cargo happened to
    arrive -- measured across the scenarios, utilisation tracked the soft count
    one for one and was exactly 0.00 on all five manifests with no soft cargo,
    including one that placed eighteen hard items under an empty shelf.  Soft
    still gets first refusal on it; this only stops hard from being unable to
    ask."""

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

    front_shortlist_quota: int = 4
    """Shortlist slots reserved for front-band hard candidates, ranked lowest
    first.  Zero turns the reservation off.

    Hard floor candidates are shortlisted by depth, so the front ones were cut
    before any veto saw them -- which is why the band rule meant to govern the
    front was measurably inert: removing it altogether moved one placement in
    thirteen scenarios.  A rule downstream of a truncation cannot undo the
    truncation, so opening the front means giving it slots, not permission."""

    front_stays_low: bool = True
    """The front is open to hard cargo, provided it stays lower than the
    terrain behind it in its own columns.

    Yielding the whole front band was the wrong shape of rule.  The opening is
    wide, so the front is not scarce as *space*; what is scarce is the sight
    line down each column, and only a box standing taller than what is behind
    it spends any.  A low box at the front blocks nothing and is ordinary
    support.  On a column with nothing behind it the terrain is the floor, so
    the same rule still says "not first" -- back-first needs no second rule."""

    front_release_back_share_of_headroom: float = 0.45
    """Release the front once the back band has used this share of the height
    available to it.

    Stated as a share, not a height, because the height available to the back
    band depends on whether there is a shelf over it: 0.76 m with one against
    the container's 1.53 without.  The absolute form this replaces was
    calibrated while the height map counted shelf-borne cargo as floor terrain
    and so read the back as 1.43 m in a container whose back band cannot
    exceed 0.76.  Zero disables the release, leaving the per-column rule in
    force for the whole episode."""

    front_release_back_height: float = 0.60
    """Unused; kept for the record of what the share above replaces.

    ``front_stays_low`` is a per-column rule and it is the right one while the
    back is still the cheaper place to build.  It is the wrong one once the
    back is full: then every remaining place requires reaching over something,
    and holding the front flat buys a sight line to ground that is already
    spent.  Zero disables the release, leaving the per-column rule in force for
    the whole episode."""

    front_release_back_share: float = 0.50
    """...measured as the height that this share of the back band has reached.

    A single tall box at the back is not a built-up back, so the test is a
    quantile rather than a maximum.  0.50 is the median height of the band."""

    front_height_slack: float = 0.05
    """How far above the terrain behind it a front box may still reach.

    Cargo heights do not line up to the millimetre, and refusing a box that
    overtops its backing by a centimetre would forbid a flush front row for no
    gain in reachability."""

    hard_avoids_front: bool = False
    """Superseded by ``front_stays_low``; kept so the two can be compared.

    Keeps normal-hard off the front band entirely while it has anywhere else to
    go -- a no-go area rather than a height limit."""

    hard_front_band: float = 0.35
    """How much of the depth, measured from the opening, counts as the front
    band hard should yield."""

    typed_cap_enabled: bool = False
    """Let soft and priority rest on hard cargo, capping the terrain.

    Layer 2 was normal-hard only, so typed cargo could not rest on cargo at
    all, which is backwards at the top of a container: the last usable space is
    a lid, and soft is exactly the class that can take one, because it has to
    support nothing above it.

    Measured, it loses: 228 -> 226 placed, 0.275 -> 0.273 fill, and it fires
    three times in thirteen scenarios.  The reason is that the premise is not
    met yet -- a hard top above ``typed_cap_min_height`` is rare on boards whose
    second layer holds thirty-one items, so "the space near the ceiling" mostly
    does not exist to be capped.  Off by default, kept because the argument
    holds and the situation it needs is one the terraces are still working
    towards."""

    typed_cap_min_height: float = 0.30
    """How high a hard top has to be before typed cargo is offered it.

    Low down there is still floor and shelf to use, and putting soft there
    buries hard support under something nothing can build on."""

    layer2_free_depth: int = 2
    """How deep cargo may stack with no justification at all.

    Two is the floor layer and one on top of it: ordinary Layer 2, which needs
    no argument.  Everything above this has to earn it by landing on a plateau
    -- see ``plateau_support_min_area``."""

    plateau_support_min_area: float = 0.25
    """How large, in m^2, the connected hard plateau under a deeper placement
    must be: same height to within ``plateau_height_tolerance``, hard, and
    4-connected on the height map.

    This is the condition that replaces counting storeys.  A depth counter
    cannot tell a terrace from a tower -- both are "three boxes up" -- and
    raising the count from two to three bought twenty placements while the
    second layer stayed at thirty-one and a tall box ended up standing free on
    a stack of its own making.  What separates the two is the shape of what is
    being built on, which the height map already knows: a terrace's top is a
    wide connected plateau, a tower's is one box lid.

    Read this number against the cargo, not against the container.  A single
    box's lid is already a plateau of that box's own footprint, and the
    normal-hard footprints in these scenarios run 0.073 - 0.464 m^2 with a
    median of 0.260, so an absolute threshold is really a statement about how
    many boxes have to be under you: at 0.35 only 19% of hard boxes qualify
    alone, at 0.25 it is 54%, at 0.20 it is 75%.  Which is why
    ``plateau_support_footprint_multiple`` exists -- it asks the question in
    the scale-free way."""

    plateau_support_footprint_multiple: float = 0.0
    """Require the plateau to be this many times the box's *own* footprint,
    on top of the absolute floor above.  Zero turns it off.

    An absolute area cannot say "more than one box under you" without knowing
    how big the boxes are, and it silently means different things for a
    0.07 m^2 box and a 0.46 m^2 one.  A multiple above 1.0 says it directly and
    at any scale."""

    support_coverage_at_any_depth: bool = False
    """Refuse to perch a box on a support much narrower than itself, at any
    depth.

    Depth is not the whole question.  Task 000 balanced a 0.55 m wide terrace
    on a 0.24 m wide upright column, overhanging both sides, at depth 2 where
    nothing is asked -- what is wrong there is the width of what it stands on,
    not the height.  The rule works: it forbids exactly that placement.  It
    also costs, and the cost lands on the task that matters:

        threshold   task 000            task 001
        off         19 / 21.677         20 / 20.452
        0.50        17 / 20.544         21 / 18.153
        0.70        17 / 20.544         21 / 21.765

    As a hard refusal it was worse still (task 001 fell to 17 / 15.544 at 0.70,
    with the front ending up taller than the back).  As the preference it is
    now, it pays on task 001 and does not on task 000, so it ships off while
    task 000 is the priority -- with the mechanism and the numbers kept, since
    the placement it objects to is genuinely bad."""

    perch_min_coverage: float = 0.50
    """How much of a box's underside must be on its support, at any depth.

    Separate from ``plateau_support_coverage``, which guards the deeper
    storeys, because this one runs everywhere and 0.70 there proved far too
    strict: it cost task 000 two placements and task 001 three, and on task 001
    it made the front *taller* than the back rather than flatter.  The case it
    has to forbid is concrete -- a 0.55 m box on a 0.24 m column is 0.44
    covered -- so the threshold only has to sit above that."""

    plateau_support_coverage: float = 0.70
    """...and how much of the box's underside has to sit on that plateau.

    Area alone is not enough: a box perched on the corner of a large terrace,
    mostly overhanging, is a tower with a good view."""

    layer2_max_layers: int = 5
    """How many layers of cargo may be stacked, floor included.

    Three means: the floor layer and two on top of it.  The wedge staircase is
    exempt -- it is not a stack, it is a ramp, and each step rests on the one
    below by construction.

    Measured across thirteen scenarios, raising the cap does buy placements --
    2: 201 at 0.228 fill, 3: 213 at 0.247, 4: 224 at 0.268 -- but read the
    layer histogram before reading the total.  The second layer barely grows
    (29 -> 31 -> 33) while each new cap adds a nearly full storey of its own,
    so what the cap buys is height in a few columns rather than a wider
    terrace.  The depth counter cannot tell a terrace from a tower; only a
    condition on the *shape* of the support below could."""

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

    front_wedge_enabled: bool = True
    """Build a staircase down to the opening once the back is up.

    ``front_stays_low`` says what the front may not do; this says what it
    should.  A box on the ground in front of the frontier whose own top stays
    under the terrain behind it continues a descent instead of starting a wall,
    and everything behind it stays reachable over it.  It is the chamfer
    staircase turned around: there the container's shape forces a climb away
    from the wall, here the access forces a descent towards the door."""

    front_wedge_band: float = 0.55
    """How far in from the opening the descent is built."""

    front_wedge_min_drop: float = 0.08
    """How much lower than the terrain behind it a step has to stay.

    Below this it is not a step down, it is the same level continued -- which
    ordinary terracing already handles."""

    front_wedge_max_steps: int = 6
    """Places offered per decision, highest ground first."""

    front_wedge_poses: int = 2
    """Poses tried per step, tallest that still fits under the step behind
    first: a tread should spend the headroom it has, not sit as low as it can."""

    last_resort_enabled: bool = True
    """When every ordinary generator comes back empty, look for somewhere the
    box simply fits before giving it up.

    Not a nicety.  The official stream shows one item at a time
    (``max_space: 1``), so an item with no candidate does not get skipped --
    it ends the episode.  Task 000 stopped at 15 of 41 with 0.968 m^2 of bare
    floor and a clear 1.16 x 0.56 rectangle at the front that two of the item's
    six poses fitted.  Nothing proposed them, because every anchor is derived
    from the edge of something already packed and the hole finder refuses
    rectangles that large by design."""

    last_resort_max_rects: int = 8
    """Empty rectangles offered to the last resort, largest first."""

    last_resort_rects_per_region: int = 4
    """How many rectangles to peel off one empty region before moving on."""

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

    bridge_keeps_floor: bool = True
    """A bridge may not seal floor that is still worth having.

    On task 000 the fifth placement bridged the 0.371 m gap between the first
    and the third, 0.28 m above bare floor, and from then on that floor could
    not be reached.  Merging two supports is worth doing over ground that is
    already spent; over ground a later box could still use, a bridge is a
    lid."""

    bridge_max_sealed_floor: float = 0.06
    """How much bare floor a bridge may pass over, in m^2.  Enough for the
    clearance gaps between neighbours, not enough for a box."""

    compact_raised: bool = True
    """Compact placements that rest on cargo, not only floor ones.

    A terrace on task 000 stopped 0.104 m short of the chamfer strip because
    no anchor sat there and nothing pushed it in.  A step that reaches the
    strip recovers wedge area; the slack is worth nothing to anyone."""

    compact_sideways_always: bool = True
    """Slide sideways for every role, not only the wall and perimeter ones.

    The restriction existed so that ordinary foundation would not be pressed
    against a wall and hollow out the centre.  Compaction is bounded by the
    stranding test either way, and the roles it excluded are exactly the ones
    that stop short of the chamfer."""

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

    wedge_step_max_footprint_fraction: float = 0.13
    """Only small cargo climbs the staircase.  A big box spent here is a big
    box missing from the foundation.

    Both this and ``wedge_step_max_height`` have to be satisfied by the *same*
    orientation, and on the official manifests neither was: the flat pose of a
    0.55 x 0.40 box is 0.22 m^2 against a 0.203 m^2 budget, and the poses small
    enough are the upright ones, which are too tall.  So `n_step_capable` was
    zero and the wedge closed before the first placement, on both tasks.  At
    0.13 the flat pose qualifies.  Measured: task 000 keeps its score and gains
    a two-step staircase recovering 0.0282 of 0.0785 m^2; task 001 gains a
    placement.  0.16 admits more steps and wins three placements on task 001,
    but costs task 000 1.5 points of fill, which is the wrong trade while
    task 000 is the priority.
    """

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

    count_all_shelves_as_relief: bool = True
    """Every shelf relieves the soft strip, not only the main one.

    Task 000 declares no main shelf and still carries the 0.60 m^2 chamfer
    shelf, which cargo does use -- so the soft strip was sized as though soft
    had nowhere to go but the floor."""

    zones_shrink_with_demand: bool = False
    """Re-size the reserved strips each step from the typed cargo still to
    come, rather than once from the whole manifest.

    Sized once and reapplied unchanged, the strips held the front-right
    quadrant of task 000 -- 0.61 m^2 -- against hard cargo for the whole
    episode, including long after every soft item had been housed.  What a
    reservation is for is the cargo that has not arrived yet.

    Measured, it does not pay.  Alone it changes nothing on either task, and
    combined with the shelf-relief fix it costs task 001 1.8 points of fill --
    the two together shrink the strip so far that typed cargo loses the floor
    it does need.  Off by default; the argument still stands and the mechanism
    is here for a manifest where the strips genuinely outlive their demand."""

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
