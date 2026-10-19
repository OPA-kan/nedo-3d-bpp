# Tasks B and C under a different SKU mix: the sample-pinned tables read from the stream

Branch `claude/rl-packing-policy-ftogt3-bmix`; module `rule_alpha/seen.py`;
flags `phase_switch_window=seen`, `pocket_mix=seen`,
`online_row_depths=seen` (with `seen_classes_min_hard`,
`seen_classes_lead`, `pocket_mix_prior`, `pocket_mix_min_seen`; all off by
default); arms `arm_bmix_b`, `arm_cmix_c` (`reports/bench/arms/README.md`);
records `reports/bench/bmix-*`, `cmix-*`, and the two baselines the tree
lacked, `nck-hard-b` and `ship-hard`; tests `tests/test_bmix.py`.

## 1. The question

Tasks B and C run online -- a pool of ten in view on B, one item on C --
and the stream is not known ahead.  The shipped forms (`arm_nck_b` = v60
on B, `arm_ship_c` on C) carry the official sample's SKU mix in several
places and never update them from the stream.  The platform's B and C
episodes may draw from a different mix.  Two questions: how much do the
shipped forms lose when the mix differs, and does reading those places
from the boxes seen so far (placed and in view, the sample's mix as the
prior) recover it without changing anything on the sample's mix?

### 1.1 Where the sample's mix is pinned, and what is actually live in the shipped forms

Checked by building both arms' configs (`bench.arms.make_arm`) and reading
the fields:

| place | pinned to | read by | live in `arm_nck_b` / `arm_ship_c`? |
|---|---|---|---|
| `phase_switch_window="0.40x0.55x0.24"` | the smallest hard class's window | the phase switch (`agent._low_phase`, `surface.usable_surface_ratio`), the cliff band | **yes**: `phase_switch=true` in both |
| the pocket guard's class frequencies (`pocket.ClassFrequencies`) | `room.SKU_MIX` as a Dirichlet prior of `pocket_guard_prior` = 4 pseudo-items | `pocket.PocketGuard.classes` | **yes**: `pocket_guard=true` in both -- but see below: it already updates from every item seen |
| `online_row_depths="0.56,0.45,0.4"` | the hard classes' flat depths | the online rows policy (`online_planner="rows"`) | **no**: neither arm sets `online_planner` (the ladder places; the arms' `offline_planner=rows` is Task A's) |
| `pair_key_window="0.40x0.55"` | the smallest hard class's footprint | `pair_key`, `pair_reserve` | no: both off |
| `surface_arbiter_window="0.40x0.55x0.24"` | the same | `surface_arbiter`, `cliff_veto` | no: both off |
| `future_selector_mix="seen"` | (already adaptive) | `future_selector` | no: off |
| `checkmate_guard`'s `_seen_hard_classes` | (already adaptive, counts the pool every call) | `checkmate_guard` | no: off |
| `count_mode_items_per_container=41`, `pocket_guard_items_per_container=41` | the stream's *length*, not its mix | the count threshold, the guard's remainder | yes, out of this report's scope (findings, "The count threshold's estimate on B and C") |

So of the places the question names, two are live in the shipped forms:
the phase switch's window and the pocket guard's frequencies.  And the
pocket guard's frequencies were never fixed: `ClassFrequencies.observe`
adds every pool item (once, by index) to a Dirichlet count whose prior is
4 pseudo-items over the sample's three hard classes, and a class the
sample does not have (the 0.80 x 0.60 x 0.50 box of the big mix) gets a
slot of its own the first time it is seen.  What is pinned there is the
prior's weight and the expected stream length (41 a container), not the
classes.  The online rows' table is pinned but inert.  The one lever
that really changes what the shipped forms do on a different mix is the
phase window.

## 2. What was built

One tracker, `rule_alpha/seen.py` `SeenClasses`, on the agent
(`agent.seen_classes`): every item in the pool and every packed item of
every container, each counted once by its index, updated once a policy
call in `_policy_inner` (only when a "seen" mode is on, so the default
path does not pay for it).  It answers the most frequent hard class
(ties to the smaller footprint), the smallest hard class, the row-depth
table and a sampler's mix.  Three readers, all off by default:

- **`phase_switch_window="seen"`** (`agent._phase_window`, read by
  `_low_phase` and `_cliff_band`): the most frequent seen hard class,
  lying flat (`lxwxh`, the smallest dimension the height), when it leads
  the runner-up by `seen_classes_lead` = 2 items; the sample's window
  while fewer than `seen_classes_min_hard` = 6 hard boxes have been seen
  or no class leads.  `"seen-smallest"`: the smallest seen hard class by
  footprint (not measured here).  Phase stats `seen_window` /
  `seen_window_steps` say when the window left the sample's.
- **`pocket_mix="seen"`** (`pocket.ClassFrequencies.set_seen`): the
  guard's counts from the tracker with the foresight scheme
  (`rule_alpha/foresight.py`): `pocket_mix_prior` = 10 pseudo-items over
  the sample's hard classes, plus the seen hard classes by their counts
  once `pocket_mix_min_seen` = 10 items (soft ones too) have been seen,
  the prior alone before that.  `"fixed"` keeps the guard's own count
  (prior 4 plus every item from the first), byte for byte.
- **`online_row_depths="seen"`** (`agent._seen_row_lines`): the flat
  depths (middle dimension) of the seen hard classes together with the
  sample's three as the prior, distinct, the deepest first, laid back to
  front as the fixed set is (`planner.online_row_lines`, which now takes
  a `y_back` to lay from).  Rows that hold a box, and every row behind
  them, are kept as they were laid; only the rows in front are laid
  again from the table as it stands, less the depths the kept rows took.
  So no row holding a box ever moves, and a container no box has reached
  follows the table entirely.  On the sample's classes the table is the
  fixed one at every call (the seen depths are a subset of the prior's);
  the big mix adds a 0.60 m row, the small mix a 0.25 m one.

Why the lead of 2 and the prior in the row table: on the official sample
streams the A (0.55 x 0.40) and B (0.65 x 0.45) classes run neck and
neck (15 to 14 over the B stream, B ahead once, at the seventh hard box),
and the C class (0.75 x 0.56) first shows at the thirteenth.  A "most
frequent" window without the lead would flip to B's for one call, and a
row table of the seen classes alone would lack the 0.56 m row for twelve
hard boxes and, once a 0.45 and a 0.40 row held boxes, never get it.
With the lead and the prior every "seen" reading on the sample streams
equals the fixed table at every call (`tests/test_bmix.py`,
`test_the_sample_streams_reproduce_the_fixed_tables`), which is what makes
the adaptive form safe to ship blind.

Left alone, and why: `pair_key_window` and `surface_arbiter_window`
serve levers the shipped arms do not set; the existing
`_seen_hard_classes` of the checkmate guard (off) counts the whole pool
every call and was left as it is so that lever's behaviour does not
change.  The unit tests: the tracker's counts over a few calls with
overlapping pools and packed items; the sample streams reproducing the
fixed tables; the big and small mixes moving them; the pocket modes
(fixed counts from the first item, seen waits for ten, the agent feeds
the tracker to the guard); the window through the agent (fixed, seen,
seen-smallest, the sample stream keeping the sample's window); the rows
(the sample classes give the fixed lines; a new class lays a row in
front while the occupied row stays; an untouched container follows the
table).  The full set (`tests.test_rule_alpha tests.test_agent
tests.test_bench tests.test_count_secure tests.test_cliff
tests.test_pair_reserve tests.test_soft_first_restricted
tests.test_b_content tests.test_fastgeom tests.test_bmix`) passes: 331
tests.

## 3. The sample scenes: unchanged

Analytic, budget 4.5, the official sample scenes (`B:sample:0`,
`C:sample:0`), the base arm against the new arm: the placements are
identical step for step (item, container, orientation, position) -- B 28
of 42 placed, C 23 of 42, both ending on a decline at the same item.  No
"seen" reading left the sample's table on either stream (section 2).

## 4. Local sanity (analytic, budget 4.5, hard-b / hard, the first 12 scenes)

The first 12 seeds of the hard suites draw 4 `sample`, 4 `big`, 2
`extra`, 2 `small` mixes (the same containers and stream for B and C;
B's pools 3-20).  Priced with `bench.platform_score`, broken down by the
scene's mix (the generator draws it from the seed):

| task | mix | n | delta [95 % CI] | counted | up / down | placed a scene |
|---|---|---:|---|---|---|---:|
| B (`nck` -> `bmix`) | all | 12 | +0.03 [-0.21, +0.24] | 9 -> 9 | 3 / 1 | +0.25 |
| | big | 3 | 0 (identical placements) | 1 -> 1 | 0 / 0 | 0 |
| | sample | 4 | -0.26 [-0.79, +0.00] | 4 -> 4 | 0 / 1 | +0.25 |
| | extra | 3 | +0.23 [+0.00, +0.70] | 2 -> 2 | 1 / 0 | -1.00 |
| | small | 2 | +0.36 [+0.10, +0.61] | 2 -> 2 | 2 / 0 | +2.50 |
| C (`ship` -> `cmix`) | all | 12 | -0.19 [-1.51, +1.20] | 9 -> 9 | 3 / 5 | +0.58 |
| | big | 3 | +0.13 [-0.75, +1.13] | 1 -> 1 | 1 / 1 | +1.33 |
| | sample | 4 | -2.53 [-3.93, -0.78] | 4 -> 4 | 0 / 3 | +0.75 |
| | extra | 3 | +0.91 [+0.00, +2.73] | 2 -> 2 | 1 / 0 | 0 |
| | small | 2 | +2.35 [-0.28, +4.99] | 2 -> 2 | 1 / 1 | 0 |

What the phase stats say (the same scenes re-run with the agent held):
on the big-mix scenes the window becomes the 0.75 x 0.56 class's (or the
0.80 x 0.60 box's where that leads) for 5-49 steps a scene, and on C
that is what moves the count -- `c-hard-s0001` (120 items of the big
mix, one container) never reached the low phase under the sample's
window (the ratio's minimum 0.21 against the switch at 0.20, 17 placed)
and reaches it 16 steps under the seen window (20 placed);
`c-hard-s0004` 4 low steps -> 45, 52 -> 53 placed.  On B the three big
scenes placed identically under both arms (the pool's smallest-first
order and the rescues reach the same poses).  On the sample-mix scenes
the window stays the sample's on three of four (`c-hard-s0009` reads the
B class's for 32 steps, that stream's B count leading A's by 2), and the
C losses there (`s0002` -3.1, `s0010` -4.4: one priority box covered
more, two to three soft boxes fewer) are on the two scenes whose policy
time is over the budget on both arms (4.5-5.8 s), where the analytic
runs are not repeatable: re-running the new arm on `s0002` placed 71
against the run's 76 and the base's 75.  The physics suites with their
intervals are the measurement; the local pass shows the levers running
without error, the sample scenes unchanged, the big-mix mechanism
working on C, and the policy time at the base's (max 6.2 -> 6.5 s on B,
5.6 -> 5.8 on C; the same scenes over the budget).

## 5. CI (physics, budget 4.5, 6 shards)

Ten runs dispatched together on the branch: the two baselines the tree
lacked (`nck-hard-b`: `arm_nck_b` on hard-b; `ship-hard`: `arm_ship_c`
on hard), and the new arms on every B and C suite.  Priced with
`bench.platform_score` against `nck-{sample-b,core-b,hard2-b}` /
`nck-hard-b` and `ship-{sample-c,core,hard2}` / `ship-hard`.

### 5.1 The suites

| suite | n | base | new | delta [95 % CI] | counted | up / down | fill | cog | stability | placement | soft | placed | policy max (base -> new) |
|---|---:|---:|---:|---|---|---|---:|---:|---:|---:|---:|---:|---|
| sample-b | 12 | 66.47 | 66.44 | -0.03 [-0.09, +0.00] | 12 (+0) | 0 / 1 | +0.2 | -0.4 | +0.0 | +0.0 | +0.0 | +0.17 | 5.6 -> 5.5 s |
| core-b | 48 | 66.15 | 66.06 | -0.09 [-0.33, +0.11] | 48 (+0) | 5 / 4 | -0.1 | +0.0 | +0.1 | -0.7 | +0.1 | -0.17 | 6.6 -> 7.0 s |
| hard-b | 48 | 34.37 | 31.99 | -2.38 [-6.44, +0.05] | 19 (-2) | 5 / 8 | -0.3 | -3.0 | -3.6 | -2.9 | -3.3 | -0.19 | 7.3 -> 7.5 s |
| hard2-b | 96 | 35.39 | 35.30 | -0.09 [-2.06, +1.64] | 47 (+0) | 17 / 11 | +0.4 | -0.2 | +0.0 | -0.4 | -0.5 | +0.04 | 7.4 -> 7.4 s |
| sample-c | 12 | 61.84 | 62.14 | +0.31 [-0.04, +0.96] | 12 (+0) | 2 / 1 | +0.3 | -0.3 | -0.3 | +2.1 | +0.6 | +0.17 | 4.1 -> 2.7 s |
| core | 48 | 62.31 | 62.03 | -0.28 [-1.07, +0.50] | 48 (+0) | 9 / 11 | -0.0 | +0.2 | +0.0 | -2.1 | -0.2 | -0.06 | 6.1 -> 6.3 s |
| hard | 48 | 44.85 | 44.44 | -0.40 [-4.41, +3.18] | 30 (+0) | 13 / 15 | -0.3 | +0.1 | -0.1 | -2.3 | +0.1 | -1.00 | 6.2 -> 6.2 s |
| hard2 | 96 | 34.77 | 36.28 | +1.50 [-1.28, +4.80] | 49 (+2) | 28 / 18 | +0.8 | +1.7 | +2.3 | +0.4 | +2.7 | +0.95 | 6.2 -> 6.2 s |

The B baselines `nck-*` and the C `ship-hard` were run in the same CI
window as the new arms (`nck-hard-b` and `ship-hard` in this batch);
`ship-core`, `ship-hard2` and `ship-sample-c` are the older v50-form
records, against which the shipped C arm's own replicate read -0.19
[-0.89, +0.39] on core (soft-ladder.md), so the hard2 reading carries
that drift as well as the change.  The policy time is the base's on
every suite (max 7.5 s on hard-b against 7.3; the same scenes over the
4.5 s budget, 25 against 26 on hard-b, 51 against 56 on hard2-b).

sample-b: eleven of the twelve scenes are placed identically, the
official scene (`b-sample-s0000`) step for step in physics as in the
analytic pass (25 of 42); `b-sample-s0011` places two more and prices
-0.37 (cog).  core-b: every single-container scene (c1, c1s: 24) is
identical; 9 of the 24 two-container scenes moved, 5 up and 4 down,
within the replicate spread of the shipped arm (b-content.md: the
`shipr` replicates read +1.2 / +2.0 against the older `ship` records).
On these sample-mix streams the window left the sample's on 7 of 12
sample-b scenes and on 4 of 12 core seeds (the B class leading A by 2,
to the 0.45 x 0.65 window) -- and on every single-container core scene
where it did (eight) the placements are the base's, so the sample's and
the B class's windows read the phase alike there; the two-container
moves come from the pocket prior (10 pseudo-items against 4) and the
physics run's own spread.

### 5.2 hard / hard2 by mix

The generator draws each hard scene's SKU mix from its seed
(`bench.scenes.make_hard_scene` / `make_hard2_scene`: `sample` twice in
five, `big`, `small`, `extra`), so the stratum is recomputed per scene
and the paired deltas grouped by it.  The last column is the share of
the stratum's scenes on which the seen window left the sample's at some
step (`metrics.phase.seen_window_steps` in the new run's records).

**hard2-b** (`nck-hard2-b` -> `bmix-hard2-b`):

| mix | n | base | new | delta [95 % CI] | counted | up / down | fill | cog | stability | placement | soft | window left the sample's |
|---|---:|---:|---:|---|---|---|---:|---:|---:|---:|---:|---|
| all | 96 | 35.39 | 35.30 | -0.09 [-2.06, +1.64] | 47 -> 47 | 17 / 11 | +0.4 | -0.2 | +0.0 | -0.4 | -0.5 | 56/96 |
| big | 20 | 46.24 | 46.42 | +0.18 [-0.06, +0.61] | 13 -> 13 | 2 / 1 | +0.6 | +0.3 | +0.2 | -0.3 | -0.3 | 16/20 (12 to the 0.75 x 0.56 window) |
| extra | 20 | 40.77 | 43.46 | +2.69 [-0.00, +7.99] | 12 -> 13 | 5 / 2 | +0.4 | +3.4 | +5.0 | +3.0 | +2.5 | 10/20 |
| sample | 41 | 31.92 | 30.34 | -1.57 [-5.03, +0.26] | 17 -> 16 | 8 / 5 | +0.3 | -2.3 | -2.3 | -2.4 | -2.3 | 19/41 (18 to the B class's) |
| small | 15 | 23.21 | 23.13 | -0.08 [-0.45, +0.24] | 5 -> 5 | 2 / 3 | +0.1 | -0.0 | -0.8 | +0.4 | +0.0 | 11/15 (10 to the 0.35 x 0.25 box's) |

The total is a crossing swap: `b-hard2-s0077` (extra mix, 40 items,
pool 10) goes 18 -> 21 placed and crosses (+52.7), `b-hard2-s0036`
(sample mix, 164 items of which 95 soft, pool 3) goes 96 -> 82, one
short of its threshold, and loses it (-68.0; the new run has 8 shake
topples against 0).  On neither did the window leave the sample's
(`seen_window` unset in both records), so both are the pocket prior and
the run's spread, not the adaptive window.  Every other scene is within
+/-3.8.  The big stratum, where the window changes on 16 of 20 scenes,
reads +0.18 with the same 13 counted: the window moves on B's big-mix
scenes without moving the count.

**hard-b** (`nck-hard-b` -> `bmix-hard-b`; the baseline run in the same
CI window):

| mix | n | base | new | delta [95 % CI] | counted | up / down | fill | cog | stability | placement | soft | window left the sample's |
|---|---:|---:|---:|---|---|---|---:|---:|---:|---:|---:|---|
| all | 48 | 34.37 | 31.99 | -2.38 [-6.44, +0.05] | 21 -> 19 | 5 / 8 | -0.3 | -3.0 | -3.6 | -2.9 | -3.3 | 32/48 |
| big | 12 | 20.06 | 20.06 | 0 (identical) | 2 -> 2 | 0 / 0 | 0 | 0 | 0 | 0 | 0 | 12/12 |
| extra | 9 | 21.01 | 15.73 | -5.28 [-15.65, +0.00] | 2 -> 1 | 0 / 3 | -0.3 | -7.9 | -9.5 | -4.3 | -6.0 | 6/9 |
| sample | 18 | 41.91 | 38.06 | -3.85 [-11.39, +0.08] | 10 -> 9 | 3 / 3 | -0.7 | -4.4 | -5.0 | -5.6 | -6.1 | 10/18 (to the B class's) |
| small | 9 | 51.73 | 52.02 | +0.29 [-0.01, +0.86] | 7 -> 7 | 2 / 2 | -0.0 | +0.5 | +0.4 | +0.0 | +0.6 | 4/9 |

Two crossings lost, both one scene of their stratum: `b-hard-s0017`
(sample mix, 170 items, pool 20) goes 88 -> 79 placed against a
threshold of 86 (-66.3) with the window never leaving the sample's
(the shadow check's vetoes 21 -> 34: the soft placements the pocket
prior changed ran into the settle), and `b-hard-s0047` (extra mix, 97
items, pool 3) goes 49 -> 48, one under its threshold (-46.7), with the
window at the 0.80 x 0.60 box's for 21 steps (3 topples in both runs).
Every other scene is within +/-3.  The twelve big-mix scenes, on every
one of which the window became the 0.75 x 0.56 or 0.80 x 0.60 class's,
are placed identically to the base: on B the pool's order and the
rescue stages reach the same poses whatever the window says, so the
adaptive window is inert where it was meant to help, and the count
swings that remain are the pocket prior's.

**hard2** (C, `ship-hard2` -> `cmix-hard2`):

| mix | n | base | new | delta [95 % CI] | counted | up / down | fill | cog | stability | placement | soft | window left the sample's |
|---|---:|---:|---:|---|---|---|---:|---:|---:|---:|---:|---|
| all | 96 | 34.77 | 36.28 | +1.50 [-1.28, +4.80] | 47 -> 49 | 28 / 18 | +0.8 | +1.7 | +2.3 | +0.4 | +2.7 | 56/96 |
| big | 20 | 42.35 | 45.38 | +3.03 [-0.18, +9.18] | 12 -> 13 | 3 / 3 | +1.1 | +3.4 | +5.2 | +1.8 | +4.4 | 17/20 |
| extra | 20 | 35.74 | 41.43 | +5.69 [-0.72, +14.89] | 10 -> 12 | 6 / 4 | +1.0 | +7.8 | +10.1 | +5.7 | +5.4 | 8/20 |
| sample | 41 | 33.09 | 32.31 | -0.78 [-5.45, +3.49] | 19 -> 18 | 13 / 6 | +0.4 | -1.6 | -2.0 | -2.5 | +1.6 | 20/41 |
| small | 15 | 27.99 | 28.11 | +0.12 [-3.07, +3.22] | 6 -> 6 | 6 / 5 | +1.1 | -0.1 | -0.3 | -0.5 | -0.5 | 11/15 |

Six crossings moved: gained `c-hard2-s0020` (extra, 39 -> 55 of 86),
`s0030` (sample, 76 -> 81 of 156), `s0043` (extra, 80 -> 92 of 168),
`s0044` (big, 28 -> 38 of 70); lost `s0065` (sample, 87 -> 85 of 170)
and `s0069` (sample, 40 -> 33 of 76).  Of the six, the window left the
sample's on two: `s0043` (the 0.35 x 0.25 box's window for 59 steps) and
`s0044` (the B class's for 3 steps); `s0020` and `s0030` were settle
failures (`end settle`) in the base run that the new run's different
course avoided, and `s0065` / `s0069` never left the sample's window.

**hard** (C, `ship-hard` -> `cmix-hard`; the baseline in the same CI window):

| mix | n | base | new | delta [95 % CI] | counted | up / down | fill | cog | stability | placement | soft | window left the sample's |
|---|---:|---:|---:|---|---|---|---:|---:|---:|---:|---:|---|
| all | 48 | 44.85 | 44.44 | -0.40 [-4.41, +3.18] | 30 -> 30 | 13 / 15 | -0.3 | +0.1 | -0.1 | -2.3 | +0.1 | 29/48 |
| big | 12 | 24.75 | 24.98 | +0.23 [+0.00, +0.49] | 3 -> 3 | 3 / 1 | +0.5 | -0.0 | +0.0 | +0.5 | +0.0 | 12/12 |
| extra | 9 | 34.10 | 33.76 | -0.33 [-1.10, +0.36] | 4 -> 4 | 3 / 3 | +0.5 | -0.3 | -1.7 | +0.5 | -0.7 | 6/9 |
| sample | 18 | 56.67 | 52.84 | -3.83 [-11.48, +0.52] | 15 -> 14 | 4 / 7 | -1.0 | -4.2 | -5.2 | -6.1 | -4.8 | 8/18 |
| small | 9 | 58.76 | 64.29 | +5.53 [-2.51, +19.18] | 8 -> 9 | 3 / 4 | -1.0 | +9.0 | +11.6 | -1.0 | +11.1 | 3/9 |

A crossing swap: `c-hard-s0024` (small, 23 -> 33 of 63) gained,
`c-hard-s0017` (sample, 170 items of which 55 soft, 101 -> 84, a settle
failure in the new run) lost; on neither did the window leave the
sample's.  The twelve big-mix scenes, where the window became the 0.75
x 0.56 or 0.80 x 0.60 class's on every one, read +0.23 [+0.00, +0.49]
with 8 of 12 identical: the local pass's `c-hard-s0001` (17 -> 20
placed under the analytic model) places 17 in both physics runs.

### 5.3 Which lever moved what

The new arms carry two live changes -- the window, which fires only
where a class leads, and the pocket prior, which differs on every
stream (10 pseudo-items and a ten-item wait against 4 from the first
item).  Splitting each hard pair by whether the window left the
sample's on the scene (the new run's `seen_window_steps`) separates
them: on the scenes where it did not, the pocket prior is the only
difference.

| pair | window left the sample's | n | delta [95 % CI] | counted | identical | window stayed | n | delta [95 % CI] | counted | identical |
|---|---|---:|---|---|---:|---|---:|---|---|---:|
| hard-b | | 32 | -1.49 [-4.53, +0.18] | 15 -> 14 | 23 | | 16 | -4.16 [-12.46, +0.01] | 6 -> 5 | 12 |
| hard2-b | | 56 | **+0.20 [+0.06, +0.40]** | 26 -> 26 | 42 | | 40 | -0.49 [-5.16, +3.82] | 21 -> 21 | 26 |
| hard (C) | | 29 | -0.09 [-0.66, +0.44] | 16 -> 16 | 12 | | 19 | -0.89 [-10.85, +8.51] | 14 -> 14 | 8 |
| hard2 (C) | | 56 | +1.44 [-1.81, +5.17] | 29 -> 30 | 32 | | 40 | +1.58 [-3.17, +6.51] | 18 -> 19 | 17 |

Where the window fires, the readings are small and mostly identical
placements (B: 65 of 88 scenes identical, hard2-b +0.20 with its
interval above zero; C: 44 of 85 identical, the big and extra strata of
hard2 +3.57 / +7.30 [+0.13, +21.33] with a crossing each).  Where it
does not fire -- the scenes on which only the pocket prior differs --
sit the crossing swings: B's two lost crossings on hard-b (`s0017`:
-8.29 on that stratum's row) and the sample-stratum loss on hard2-b,
C's `s0017` / `s0024` swap on hard and `s0020` / `s0030` / `s0069` on
hard2.  The pocket guard's class frequencies were already adaptive
(section 1.1); what `pocket_mix=seen` changed was the prior's weight,
and that moves the soft placements on soft-heavy streams enough to
swing a count at the threshold either way, with no mix adaptation to
show for it.

## 6. Verdict

**(1) How much the shipped forms lose when the mix differs.**  Less than
the question supposed, because less is pinned than it looks: of the
places named, only the phase window is both fixed and live in the
shipped B and C forms (the pocket guard already updates from every item
seen, the online rows are not shipped, the pair and arbiter windows
serve levers that are off).  The window's cost shows on C's big-mix
scenes -- under the sample's window the agent can miss the low phase
altogether (`c-hard-s0001`: the ratio's minimum 0.21 against the switch
at 0.20) -- but priced on the physics suites it is small: C's big
stratum +0.23 [+0.00, +0.49] on hard and +3.03 n.s. (one crossing) on
hard2, and nothing at all on B, where the twelve big-mix hard scenes
place identically whatever the window reads.

**(2) Does the adaptive form recover it without changing the sample
mix.**  The sample scenes are unchanged: `B:sample:0` and `C:sample:0`
place identically step for step under the new arms, analytic and
physics (25 of 42 each), and sample-b / sample-c read -0.03 [-0.09,
+0.00] / +0.31 [-0.04, +0.96] with 12 of 12 counted; core-b -0.09
[-0.33, +0.11] and core -0.28 [-1.07, +0.50] with 48 of 48 counted and
every single-container core-b scene identical.  No crossing is lost on
core-b, core, sample-b or sample-c.  On the varied suites the combined
arms do not clear the ship rule: B reads hard-b **-2.38 [-6.44, +0.05]**
with two crossings lost and hard2-b -0.09 n.s. (a crossing swap); C
reads hard2 **+1.50 [-1.28, +4.80]** with two crossings gained and hard
-0.40 n.s. (a swap).  The split by lever (5.3) says the window itself
is safe and slightly positive (hard2-b +0.20 [+0.06, +0.40] on the
scenes where it fires, C's big and extra strata up), and that the
swings, B's lost crossings among them, are the pocket prior's -- a
change of weight in a guard that was already adaptive.  The policy time
stays the base's (max 7.5 s, the same scenes over the budget).

**Ship: not kept** as `arm_bmix_b` / `arm_cmix_c`.  The candidate that
follows from the split is the window alone -- `arm_nck_b` /
`arm_ship_c` plus `phase_switch_window=seen` with `pocket_mix` left
fixed -- which on the sample streams is byte for byte the shipped form
on every scene where no class leads by two and was placement-identical
on 65 of 88 B scenes and 44 of 85 C scenes where it fired here; it
needs its own pair of runs on hard-b / hard2-b and hard / hard2 before
it ships (two to four CI runs).  `online_row_depths=seen` is ready for
the day the online rows ship.  What could not be finished: that
window-only measurement (the ten-run budget went on the combined arms
and the two missing baselines), and the `seen-smallest` variant, which
would adapt the small and extra mixes the way `seen` adapts the big.
