# The same-class pair reservation on Task B (`pair_reserve`)

Branch `claude/rl-packing-policy-ftogt3-pair`; arm
`reports/bench/arms/arm_pair_b.txt` (the shipped B form plus
`pair_reserve=true`); records `reports/bench/pair-sample-b`,
`pair-core-b`, `pair-hard2-b`, priced with `bench.platform_score` against
`ship-sample-b`, `ship-core-b`, `ship-hard2-b`.

## 1. What

The piece instrument (findings, "Where the empty volume is made") charged
the flat max-footprint floor pose of the 0.55 x 0.40 x 0.24 box 0.14 of
the container a placement, 59 % of it the column over its own top: 0.40
is 3 cm short of the window of the smallest hard class (0.40 x 0.55 plus
the 3 cm clearance), so a lone one of these carries nothing until a
second top of its height sits beside it, and two side by side are
0.80 x 0.55, a window and more.  `pair_key` (a tie-break towards a top of
the same height within 6 cm) was inert, because the lone box is laid when
nothing of its height is near it yet: the pair needs the *next* box,
which Task C cannot see.  Task B can: its pool holds ten items with
their sizes.

`rule_alpha/pair.py` and the agent's `_pair_reserve` / `_pair_commit` /
`_pair_honour`, behind `config.pair_reserve` (default off):

1. When the ladder's pick for a pool item is a flat floor pose of a box
   whose top alone cannot hold the window (`pair.narrow_top`: derived
   from `pair_key_window` plus the instrument's clearance, so any class
   under 0.43 x 0.58 qualifies, not a hard-coded one) and the pool holds
   another item of the same class and dimensions
   (`pair.same_class_partner`), the pick is taken from the first
   `pair_reserve_k` = 6 survivors of its rung, in the rung's order and
   the pick first, that leave room beside themselves for the partner:
   the same box flush along the side whose pair holds the window
   (`pair.pair_holds_window`; for the 0.55 x 0.40 box the short side,
   since 1.10 x 0.40 holds nothing), the settled clearance 0.026 plus
   `pair_reserve_slack` 0.01 between them, on the floor, inside the
   container and clear of the packed boxes (`layer1.validate`, the full
   analytic validator), and one the ladder's own rules let stand
   (`pair.ladder_refuses`: the spot as a floor candidate of the partner
   through `compute_features` and `apply_vetoes` on the board with the
   first box applied to it, refused when any veto is recorded, the
   reserved typed strips and the corridor among them, and by the cover
   rule).  A survivor other than the pick is compacted through
   `build_placement` like the pick.  The search is bounded by
   `pair_reserve_seconds` 0.3.  After the pose is emitted (the shadow
   gate may replace it with another survivor) the spot is found again
   beside the emitted pose and the reservation is kept for one call.
2. On the next call, before any other stage, when the partner is still
   in the pool and the first box settled flat on the floor where it was
   put, the spot is recomputed beside the box *as it settled* (the
   reserved direction first, the other direction of the same axis after
   it) and validated again, the ladder's vetoes and the cover rule
   included; the partner goes there as archetype `pair-reserve`, through
   the shadow gate like any pose.  Anything else (partner gone, spot
   taken, the box settled off its face, a shadow veto) loses the
   reservation and the call falls through to the normal flow.

The first form (`pair0`, records `reports/bench/pair0-*`) skipped the
ladder's vetoes on the spot: the ladder's pick lays the 0.55 x 0.40 box
0.55 along the back wall in the back-right corner, the only pair that
holds the window is then in front of it, and that spot lies in the
reserved priority strip (the right front, `reserved-zone`), which the
ladder never gives to plain hard cargo.  On sample-b every reservation
went there (16 of 16, 10 of 12 episodes, steps 1-4), the priority boxes
lost their strip, and the platform price was -5.03 [-9.36, -0.61], all
of it placement (-27.1) and soft (-4.2).  With the vetoes the pick
switches (`pair_switched`) to the survivor laid 0.40 along the wall,
whose pair runs along the back wall (0.84 x 0.55), out of every strip.

`Decision` gained `rung_ordered` (the chosen rung's candidates in the
rung's order) so the reservation reads the rung's next few without
re-sorting.  The phase stats carry `pair_eligible` (the trigger held),
`pair_reserved`, `pair_switched` (the pick changed to a later survivor),
`pair_no_room`, `pair_honoured`, `pair_lost` and `pair_lost_<why>`,
written to the record's `metrics.phase` by `bench/episode.py`.

Tests: `tests/test_pair_reserve.py` (the geometry; two 0.55 x 0.40 boxes
on an empty floor: the first pose leaves room, the second lands flush
beside it across 0.036 m along the axis whose pair holds the window, and
their joint extent holds the window; the reservation lost when the
partner has gone or the spot is taken; off by default and with a pool of
one; no reservation for a wide top or a lone class).  The full set
(`tests.test_rule_alpha tests.test_agent tests.test_bench
tests.test_count_secure` plus these) passes: 248 tests.

## 2. The mechanism on a sample episode

On `b-sample-s0001` (the official sample's items reshuffled), the
shipped B arm against the pair arm, the usable-surface ratio read before
each placement (`probe_surface.py`, the worktree copy):

| step | ship arm | pair arm |
|---|---|---|
| 0 | item 1 (0.55 x 0.40 x 0.24) flat at the back-right corner, ratio 1.00 | the same |
| 1 | item 5 (same class) stacked on it (terrace), 1.00 | item 5 **flush in front of it** (`pair-reserve`, gap 0.036 m), 1.00 |
| 2 | item 10 (same class) flat at the back-left, 1.00 | item 10 **bridging the pair's two tops** (plateau-merge at 0.41 m), 1.00 |
| 3 | the 0.65 x 0.45 box as a wedge step on item 10 | the 0.65 x 0.45 box flat at the back-left, 0.95 |

So the pair is made as designed and the third box of the class rests on
the two tops at once: the window the lone box could not offer is used
one step later.  The ratio stays at 1.00 through the pair (the floor's
cells are counted usable through the tops above them).  What follows is
a different layout, and the surface trajectory of the episode as a whole
is the measurement's business (section 4).

Locally (`B:sample:0`, the physics simulator, budget 4.5 s): the trigger
held twice, two reservations, both honoured (steps 1 and 4), 24 items
against the shipped record's 26 on that scene, the pair search 1 ms an
episode.

## 3. How often it fired and was honoured (CI, the physics simulator, budget 4.5 s)

From the records' `metrics.phase` (`pair_*`):

| suite | form | episodes with the trigger | eligible | reserved | pick switched | no room | honoured | lost (spot taken) | pair steps | search time |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|---:|
| sample-b (12) | pair | 10 | 10 | 10 | 10 | 0 | 10 | 0 | all at step 1 | 3 ms |
| sample-b | pair0 | 10 | 16 | 16 | 0 | 0 | 16 | 0 | 1-4, median 1 | 0.5 ms |
| core-b (48) | pair | 40 | 41 | 40 | 40 | 1 | 40 | 0 | all at step 1 | 3 ms |
| core-b | pair0 | 40 | 59 | 56 | 0 | 3 | 46 | 10 | 1-4, median 1 | 0.4 ms |
| hard2-b (96) | pair | 30 | 52 | 22 | 17 | 30 | 19 | 3 | 1-9, median 3 | 3 ms (max 49) |
| hard2-b | pair0 | 29 | 54 | 30 | 2 | 24 | 21 | 9 | 1-64, median 4 | 1 ms |

What the counts say.  The trigger is the first decision of the episode
on every layout that opens with a 0.55 x 0.40 box and holds a second in
the pool: the stream's first item is that class on 10 of 12 sample and
40 of 48 core scenes, the ladder lays it flat on the floor, and the
reservation fires at step 0 and is honoured at step 1.  With the
ladder's vetoes on the spot (`pair`) the pick is switched every time
(the corner pose laid 0.55 along the wall never has a legal pair, the
0.40-along pose always has), and every reservation is honoured: the
first box settles where it was put and the partner is the pool's next
item of the class.  After that the trigger never fires again in the
episode (41 eligible on 40 core episodes): once the pair stands, the
class's next boxes are placed on tops (plateau-merge across the pair,
terraces) rather than by a floor rung, so there is one pair an episode,
whatever the stream holds.  The first form (`pair0`, no vetoes) also
fired a second time on a few episodes (a later floor box of the class
with a partner, 16 / 59 eligible) and lost 10 of 56 core reservations to
a spot no longer free.  The search costs 3 ms an episode (one
`compute_features` with the grid per direction tried) and the max step
time is lower on every suite (the ladder's failing stages are what cost
time, and the pair's call returns at once).

## 4. The usable-surface trajectories (sample B, seeds 0-3)

`probe_surface.py` on the pair arm against the ship arm, the step at
which the usable-surface ratio first falls under 0.5 / 0.4 / 0.3 / 0.2,
the items placed and the threshold (22 of 42):

| seed | arm | placed | under 0.5 | under 0.4 | under 0.3 | under 0.2 | pair steps |
|---|---|---:|---:|---:|---:|---:|---|
| 0 | ship | 26 | 16 | 17 | 17 | 25 | |
| 0 | pair | 24 | 17 | 18 | 18 | never (0.22 to the end) | 1, 4 |
| 1 | ship | 26 | 15 | 16 | 19 | 19 | |
| 1 | pair | 26 | 8 | 12 | 13 | 14 | 1 |
| 2 | ship | 23 | 13 | 14 | 15 | 15 | |
| 2 | pair | 25 | 8 | 11 | 12 | 15 | 1 |
| 3 | ship | 28 | 15 | 16 | 20 | 20 | |
| 3 | pair | 26 | 13 | 13 | 14 | 16 | 1 |

The surface does not hold longer.  On seed 0 the crossings of 0.5, 0.4
and 0.3 come one step later and the ratio never falls under 0.2 (0.22
to the end, against the ship arm's 0.18 from step 25), with the
mid-episode readings mixed (0.95 against 1.00 over steps 3-5, 0.95
against 0.90 over 6-7, 0.63 against 0.71-0.79 over 10-13); on seeds 1-3
it falls earlier: the pair takes the back-right
0.55 x 0.84 as one block, the stream's next boxes go to the shelf and the
left, and the shelf fills by step 8 where the ship arm's layout keeps
the shelf's surface to step 11 (seed 1: the shelf placements 12 and 14
take the ratio 0.94 -> 0.75 -> 0.49 in the pair arm; the ship arm's
layout keeps 0.79 to step 11).  The pair itself costs no surface
(ratio 1.00 after it, the third box on the two tops); the later cliffs
are the other archetypes', in a layout the pair changed.  Items placed:
26 / 26 / 25 / 26 against 26 / 26 / 23 / 28, the same 103 over four
seeds (one up, one down by two).

## 5. The tables (CI)

`python -m bench.platform_score reports/bench/ship-<suite> reports/bench/pair-<suite> reports/bench/pair0-<suite>`:

| suite | base score (counted) | form | score | delta [95 % CI] | counted | up / down | fill | cog | stability | placement | soft | placed | policy max |
|---|---|---|---:|---|---:|---|---:|---:|---:|---:|---:|---:|---:|
| sample-b | 55.44 (11/12) | pair | 52.35 | -3.09 [-7.25, +0.71] | 11 (+0) | 4 / 6 | -1.9 | -1.5 | -0.3 | -17.4 | +2.4 | -0.83 | 5.7 s (base 5.8) |
| sample-b | | pair0 | 50.41 | -5.03 [-9.36, -0.61] | 11 (+0) | 2 / 8 | -0.9 | -1.4 | +0.0 | -27.1 | -4.2 | -0.83 | 5.2 s |
| core-b | 61.58 (47/48) | pair | 60.18 | -1.40 [-4.75, +1.94] | 47 (+0) | 13 / 29 | -1.1 | -0.2 | -1.2 | -2.2 | -3.2 | -1.25 | 7.3 s (base 7.4) |
| core-b | | pair0 | 60.55 | -1.02 [-4.29, +2.31] | 47 (+0) | 15 / 25 | -0.1 | -0.3 | -1.6 | +3.2 | -7.4 | -1.00 | 7.3 s |
| hard2-b | 32.70 (44/96) | pair | 34.89 | +2.19 [-0.67, +5.26] | 47 (+3) | 36 / 23 | +0.4 | +2.4 | +2.7 | +2.0 | +4.9 | -0.02 | 7.1 s (base 7.5) |
| hard2-b | | pair0 | 34.86 | +2.15 [-0.02, +4.57] | 47 (+3) | 39 / 22 | +0.7 | +2.2 | +3.0 | +2.8 | +3.3 | +0.30 | 7.5 s (base 7.5) |

The episodes split by whether the trigger fired (the per-episode
platform price, `pair_split.py`; an episode where it never fired should
reproduce the shipped record, and the ones that do not are the bench's
replicate noise, from the deadline-dependent stages on a shared runner):

| suite | form | fired: n, mean delta, placed, up / down | silent: n, mean delta, placed, identical |
|---|---|---|---|
| sample-b | pair | 10, -3.70, -0.90, 4 / 6 | 2, 0.00, 0, 2 of 2 |
| sample-b | pair0 | 10, -6.03, -1.00, 2 / 8 | 2, 0.00, 0, 2 of 2 |
| core-b | pair | 40, -2.86, -1.68, 12 / 28 | 8, +5.91, +1.00, 6 of 8 |
| core-b | pair0 | 40, -2.54, -1.62, 12 / 24 | 8, +6.54, +2.12, 4 of 8 |
| hard2-b | pair | 30, -1.42, -2.73, 13 / 11 | 66, +3.83, +1.26, 28 of 66 |
| hard2-b | pair0 | 29, +0.69, -2.07, 13 / 10 | 67, +2.79, +1.36, 26 of 67 |

The per-scene sample-b table (the fixed form; `thr` the count
threshold, 22 of 42):

| scene | ship placed | pair placed | ship priority placed | pair priority placed | ship max s | pair max s | pair honoured |
|---|---:|---:|---:|---:|---:|---:|---:|
| b-sample-s0000 | 26 | 23 | 1 | 0 | 4.70 | 5.69 | 1 |
| b-sample-s0001 | 26 | 26 | 2 | 0 | 5.40 | 5.57 | 1 |
| b-sample-s0002 | 23 | 24 (settle end) | 2 | 2 | 4.42 | 2.29 | 1 |
| b-sample-s0003 | 28 | 26 | 3 | 3 | 4.89 | 3.28 | 1 |
| b-sample-s0004 | 25 | 25 | 1 | 1 | 5.18 | 3.70 | 0 |
| b-sample-s0005 | 26 | 25 | 3 | 3 | 4.79 | 3.76 | 1 |
| b-sample-s0006 | 30 | 32 | 0 | 0 | 4.78 | 4.12 | 1 |
| b-sample-s0007 | 28 | 26 | 3 | 3 | 5.18 | 5.40 | 1 |
| b-sample-s0008 | 26 | 26 | 0 | 0 | 4.86 | 2.36 | 1 |
| b-sample-s0009 | 28 | 26 | 1 | 0 | 5.13 | 2.97 | 1 |
| b-sample-s0010 | 21 | 21 | 1 | 1 | 5.81 | 4.46 | 0 |
| b-sample-s0011 | 30 | 28 | 0 | 0 | 4.43 | 2.23 | 1 |

The placement loss of the fixed form on sample-b is not the strip: on
s0000, s0001 and s0009 the shipped run placed its priority boxes at
steps 21-27 by the stack option or the physics resort on raised spots
(0.6-1.3 m) that the pair's layout does not offer, and the pair run
ended with them in the pool.  The platform's placement credit is the
share of the scene's one to three priority boxes, so each such episode
is -33 to -100 placement points, times the weight 0.143.

On hard2-b the trigger holds on 30 of 96 episodes only (the hard
layouts open with other classes), and there the reservation finds room
on 22 of 52 eligible decisions (`no_room` 30: the hard floors are
tighter, and the ladder's vetoes refuse the spot) and 19 are honoured,
at steps 1-9.

## 6. Verdict

Not kept.  The platform's score, the verdict, reads sample-b
**-3.09 [-7.25, +0.71]**, core-b **-1.40 [-4.75, +1.94]**, hard2-b
**+2.19 [-0.67, +5.26]**; no suite clears its interval, and the hard2-b
reading is not the pair's: on the 30 hard2 episodes where the
reservation fired the price is -1.42 a scene with 2.7 fewer items, and
the +3.83 a scene sits on the 66 episodes it never touched (38 of which
differ from the shipped record from step 4-50 on, the deadline-dependent
stages on a shared runner: the same replicate noise, in the same
direction, under the first form, +2.79).  On the episodes the pair
touched it loses on every suite: sample-b -3.70 a scene (4 up, 6 down,
0.9 items fewer), core-b -2.86 (12 up, 28 down, 1.7 fewer), hard2-b
-1.42 (13 up, 11 down, 2.7 fewer).  The counted episodes are unchanged
on sample-b and core-b (11 of 12, 47 of 48) and +3 on hard2-b (44 ->
47, the same +3 as the first form, in the untouched episodes).  The max
step time falls on every suite (the mean of the episode maxima 4.96 ->
3.82 s on sample-b, 5.65 -> 4.59 on core-b, 5.21 -> 4.22 on hard2-b;
the over-budget steps 34 -> 3, 233 -> 113, 344 -> 172), so the pair is
no cost in time; the cost is the layout.

Why.  The mechanism does what it was asked: the pair is made on the
first two decisions of 40 of 48 core episodes, the partner lands flush,
and the third box of the class rests on the two tops at once, so the
lone box's own top -- the one piece the instrument named -- is used.
But the pair fixes the back-right corner as a 0.84 x 0.55 block laid
0.40 along the wall where the ladder would have laid the box 0.55 along
it and stacked the second (a terrace) or laid it beside the first along
the wall; what follows is a different back row, and over the episode
the layout places 1-3 items fewer and offers the stack option and the
resort fewer raised spots at the end, where the shipped run places its
priority boxes (sample-b: three episodes' priority credit lost to boxes
left in the pool at the decline, -17 placement points).  The usable
surface does not hold longer (section 4: later by one step on one seed,
earlier by 5-7 steps on three), because the surface is not closed by
the lone box's top but by the cliffs the other archetypes make later,
and the pair changes which cliffs come.  The piece instrument's charge
against the lone 0.55 x 0.40 box (0.14 of the container a placement, 59
% its own top) was a static reading of the end state; the pair that
removes that piece on step 1 does not keep it removed, since the next
box of the class is stacked on the pair either way and the floor beside
it is spent as before.

What would be worth trying from here, if anything: the reservation
restricted to the lone-box case the instrument charged -- a floor box
of the class laid *beside* nothing of its height late in the episode,
not the opening corner, where the ladder's own terrace makes the second
level the pair would have made; and pricing against a fresh replicate
of the shipped B form on hard2-b before any hard2-b reading is believed
(the silent episodes' +2.8 to +3.8 a scene says the base record is
stale by that much).

Records: `reports/bench/pair-sample-b`, `pair-core-b`, `pair-hard2-b`
(the form with the ladder's vetoes, the shipped `pair_reserve=true`
form), `pair0-*` (the first form); arm `arm_pair_b.txt`; probes in the
session scratchpad (`probe_surface_pair.py`, `probe_surface_detail.py`,
`pair_tables.py`, `pair_split.py`).
