# The soft ladder: soft cargo on soft tops in the online ladder (Tasks B and C)

The platform's soft component (weight 0.141) credits the share of the soft
cargo placed and not covered by another attribute; soft on soft is not
charged. Per counted platform episode the credit is about 51 on B and 64 on
C (`reports/wedge/findings.md`, the Task B and C diagnostics), and the bench's
shipped-form records read the same (`bench.platform_score`: soft 51.5 on
core-b, 59.0 on core). This round asked whether the online ladder leaves soft
credit on the table by where it puts the soft boxes and by what the shadow
world vetoes, built three flag groups behind defaults that keep the shipped
behaviour, and priced them with `python -m bench.platform_score` against the
shipped-form bases `reports/bench/ship-core` (C) and `ship-core-b` (B).

## 1. What was built (commit 31a878c9; tests 422c3add)

**The typed-column rung** (`soft_tops_for_soft`, `priority_tops_for_priority`,
`soft_tops_rung` = first, `typed_column_min_support` = 0.7;
`layer2.typed_tops`, `layer1.generate_typed_column_candidates`). The ladder
offers a soft item the tops of the soft cargo already packed as supports: a
flat pose flush with a soft top's edges or centred on it, built and validated
like every Layer 2 proposal, the soft top carrying only where the stability
model says it does (`soft_is_structure` under `soft_structure_max_top` and
`soft_structure_floor_share`), with at least 0.7 of the footprint in contact.
The rung stands after the shelf and ahead of every floor rung, so a soft item
takes a column over a floor pose whenever a column exists and the soft carpet
stops spreading. The shipped ladder's soft rungs offered the floor, the shelf
and hard tops only; every soft-on-soft placement of the shipped form came
from the rescues (the physics resort, the stack option, the count pass, the
pocket guard's override). The same rung for priority items on priority tops
is `priority_tops_for_priority`.

**Four pocket-guard fixes** (`pocket_guard_deadline_share` = 0.5,
`pocket_guard_all_rooms`, `pocket_guard_tie_soft_top`,
`pocket_guard_phase_prior` with `pocket_guard_phase_items` = 10;
`rule_alpha/pocket.py`). The guard's fixed 0.8 s window had timed out on 91 of
228 soft floor decisions of the soft-carpet boards before it had scored the
poses it generated; the deadline-aware window runs to half the policy budget
from the call's start. Poses in other containers were scored by their own
container's slots alone, so a roomier container won or lost on its size; with
`all_rooms` every container's slots count, the home container searched first.
Ties among the guard's poses went to the lowest pose (the floor); with
`tie_soft_top` a pose on a soft top wins the tie and replaces the ladder's
floor pose without the margin when it keeps at least that pose's room. The
guard's count prior (after `pocket_guard_items_per_container` items nothing
is expected and the guard stands down) yields to the phase switch's reading
while every container is still in the high phase.

**The shadow's soft-on-soft thresholds and pre-settle**
(`shadow_soft_on_soft_drift_xy` = 0.08, `shadow_soft_on_soft_angle_deg` = 12,
`shadow_presettle_steps` = 60; `rule_alpha/agent.py` `_shadow_verdict`,
`rule_alpha/shadow.py`). The shadow world's soft veto fires at 0.02 m of
drift or 5 degrees of tilt after the settle. A soft box settling on a soft
top sinks and leans by a few centimetres and degrees in the official world
too, which accepts up to 0.3 m and 45 degrees; the soft-on-soft thresholds
replace the shipped ones for a soft item whose settled pose rests on a soft
top (the hard limits 0.10 m / 15 degrees still apply). The pre-settle steps
the synced shadow world 60 times before the first check, because the
official world's soft stacks are still sinking when the observation is taken
and the shadow rebuilt them at rest.

The probe scripts (`reports/wedge/soft-ladder/shadow_probe2.py`,
`shadow_log_run.py`), the probe cases (`probe_sos.jsonl`, `targets_sos.txt`)
and the readers (`softl_stats.py`, `softl_vetoes.py`) are in
`reports/wedge/soft-ladder/`.

## 2. The arms and the records

Each arm is the shipped arm (`arm_ship_c.txt` / `arm_ship_b.txt`) plus the
group's fields, checked field for field with `bench.arms.make_arm`
(`arm_softl-base_*` builds a config identical to the ship arm's). Physics,
budget 4.5 s, 48 scenes a suite, three CI shards.

| arm | fields over the ship arm | records |
|---|---|---|
| softl-base | none (the ship arm run again: the replicate spread) | `softl-base-core`, `softl-base-core-b` |
| softl-col | `soft_tops_for_soft` | `softl-col-core`, `softl-col-core-b` |
| softl-pg | the four pocket-guard fields | `softl-pg-core`, `softl-pg-core-b` |
| softl-sos | the three shadow fields | `softl-sos-core`, `softl-sos-core-b` |
| softl-colsos | the column rung and the shadow fields | `softl-colsos-core`, `softl-colsos-core-b` |
| softl-all | every field above and `priority_tops_for_priority` | `softl-all-core`, `softl-all-core-b` |

The second round's CI runs (01:48 UTC 2026-10-16, head 422c3add), read off
each run's shard artifacts (`summary.json` `arm`, the scene file names):
38837079468 = `softl-base-core`, 38837089716 = `softl-base-core-b`,
38837099934 = `softl-colsos-core`, 38837109553 = `softl-colsos-core-b`,
38837119685 = `softl-col-hard2`, 38837129778 = `softl-all-hard2` (the two
hard2 runs on four shards, 96 scenes, priced against `ship-hard2` in
section 8).

## 3. platform_score, Task C (base `ship-core`: 62.31, 48 of 48 counted, soft 59.0, placement 53.0)

Paired by scene, the bootstrap 95 % interval of the mean delta; the
components are the platform's shares (soft and placement in points of 100).
No crossing changed on C.

| arm | score | delta [95 % CI] | up / down | fill | cog | stability | placement | soft | placed |
|---|---:|---|---|---:|---:|---:|---:|---:|---:|
| softl-base (replicate) | 62.12 | -0.19 [-0.89, +0.39] | 5 / 6 | -0.2 | +0.2 | -0.1 | -0.9 | -0.3 | -0.33 |
| softl-col | 62.45 | +0.14 [-0.33, +0.62] | 17 / 12 | +0.6 | -0.2 | -0.4 | -0.7 | +1.3 | +0.35 |
| softl-pg | 62.55 | +0.24 [-0.29, +0.84] | 14 / 11 | +0.6 | +0.0 | -0.2 | +0.7 | +0.0 | +0.15 |
| softl-sos | 62.09 | -0.22 [-0.90, +0.54] | 9 / 16 | -0.2 | +0.2 | +0.0 | -1.1 | -0.3 | -0.40 |
| softl-colsos | 62.18 | -0.13 [-0.83, +0.58] | 17 / 15 | +0.7 | -0.3 | -0.2 | -3.3 | +1.8 | +0.62 |
| softl-all | 62.83 | +0.53 [-0.22, +1.32] | 22 / 15 | +1.3 | -0.2 | -0.2 | +0.4 | +1.2 | +0.83 |

The slowest call is 6.0-6.2 s on every arm (the ship's 6.1 s). The replicate
of the ship arm moves 11 episodes and reads -0.19 with a 1.3-point interval:
that is the spread any C reading here carries. The soft share moves by at
most +1.8 points (colsos), +1.2 on all, which at the weight 0.141 is +0.17 to
+0.25 of score; the column arms pay in placement (col -0.7, colsos -3.3:
priority boxes covered 0.88 -> 1.00 / 1.19 an episode). `softl-all` is the
best C reading, +0.53, inside its interval and inside the replicate's.

## 4. platform_score, Task B (base `ship-core-b`: 61.58, 47 of 48 counted, soft 51.5, placement 58.0)

| arm | score | delta [95 % CI] | counted | up / down | fill | cog | stability | placement | soft | placed |
|---|---:|---|---:|---|---:|---:|---:|---:|---:|---:|
| softl-base (replicate) | 61.48 | -0.09 [-0.81, +0.68] | 47 (+0) | 8 / 11 | -0.2 | +0.0 | +0.3 | +0.2 | -1.0 | -0.27 |
| softl-col | 60.36 | -1.21 [-5.11, +2.52] | 46 (-1) | 14 / 11 | -0.3 | -1.4 | -2.2 | -0.8 | -1.8 | -0.21 |
| softl-pg | 62.31 | +0.73 [-0.92, +3.56] | 48 (+1) | 11 / 15 | +0.2 | +1.8 | +1.4 | -0.1 | -0.1 | +0.23 |
| softl-sos | 62.84 | +1.27 [-0.30, +3.95] | 48 (+1) | 17 / 9 | +0.4 | +1.4 | +1.8 | +2.7 | +0.6 | +0.58 |
| softl-colsos | 61.61 | +0.04 [-3.28, +3.34] | 47 (+0) | 16 / 14 | +0.5 | -0.2 | -0.6 | +2.6 | -2.2 | +0.35 |
| softl-all | 61.96 | +0.38 [-2.85, +3.64] | 47 (+0) | 16 / 21 | +0.5 | -0.3 | -1.0 | +3.9 | -0.5 | +0.60 |

The B intervals are three to seven points wide because they are made of
crossing swaps at the count threshold (42 of 82 on the two-container
boards), each worth about 51 points on its episode. The shipped form places
41 on `b-c2-s0002` (one short, as the ship record and its replicate both do)
and every arm but the replicate crosses it (col 42, pg 45, sos 53, colsos
51, all 45 items); the
column arms lose `b-c2-s0006` (50 -> 41: a stack-option pose at step 41 the
shadow hard-vetoed at 0.30 m / 54 degrees, played as the fallback when
nothing else was found, refused by the official settle, which ends the
episode) and softl-col also `b-c2-s0003` (47 -> 35). The Task B diagnostic
(`findings.md`) found every platform B episode already counted, so a bench
B crossing buys nothing there; the reading that matters is over the episodes
counted in both runs:

| arm | n | delta [95 % CI], crossing swaps excluded | fill | cog | stability | placement | soft |
|---|---:|---|---:|---:|---:|---:|---:|
| softl-base (replicate) | 48 | -0.09 [-0.80, +0.62] | -0.2 | +0.0 | +0.3 | +0.2 | -1.0 |
| softl-col | 45 | +0.01 [-0.76, +0.78] | -0.2 | +0.2 | -0.2 | +0.5 | -0.1 |
| softl-pg | 47 | -0.36 [-1.10, +0.41] | +0.1 | +0.3 | -0.6 | -1.3 | -1.1 |
| softl-sos | 47 | +0.21 [-0.46, +0.89] | +0.2 | -0.0 | +0.1 | +1.6 | -0.6 |
| softl-colsos | 46 | +0.03 [-0.70, +0.79] | +0.3 | -0.0 | -0.6 | +2.7 | -2.2 |
| softl-all | 46 | +0.46 [-0.52, +1.49] | +0.4 | -0.1 | -1.0 | +4.0 | +0.0 |

Nothing on B moves the soft share up: the column arms move it down (-0.1 to
-2.2), the shadow thresholds -0.6. The slowest call stays at 7.2-7.4 s.

## 5. Where the soft boxes go (`softl_stats.py`)

Soft placements over the 48 episodes by what they rest on, the soft-on-soft
placements the typed-column rung made, and the soft credit an episode
(placed minus covered; the suites hold 18.2 soft items an episode, so the
shipped C form credits 60 % of them, B 55 %).

| record | floor | shelf | hard top | priority top | soft top | by typed-column | soft placed / covered / credited an episode |
|---|---:|---:|---:|---:|---:|---:|---|
| ship-core | 122 | 170 | 140 | 12 | 103 | - | 11.54 / 0.58 / 10.96 |
| softl-base-core | 119 | 172 | 139 | 11 | 98 | - | 11.38 / 0.46 / 10.92 |
| softl-col-core | 111 | 167 | 144 | 13 | 109 | 40 | 11.56 / 0.31 / 11.25 |
| softl-pg-core | 82 | 177 | 181 | 11 | 94 | - | 11.54 / 0.62 / 10.92 |
| softl-sos-core | 122 | 171 | 132 | 15 | 100 | - | 11.35 / 0.50 / 10.85 |
| softl-colsos-core | 111 | 168 | 140 | 12 | 119 | 34 | 11.65 / 0.40 / 11.25 |
| softl-all-core | 76 | 181 | 177 | 6 | 108 | 29 | 11.65 / 0.50 / 11.15 |
| ship-core-b | 86 | 41 | 126 | 59 | 139 | - | 9.98 / 0.04 / 9.94 |
| softl-base-core-b | 97 | 42 | 125 | 55 | 137 | - | 9.90 / 0.08 / 9.81 |
| softl-col-core-b | 102 | 42 | 115 | 56 | 135 | 25 | 9.90 / 0.15 / 9.75 |
| softl-pg-core-b | 78 | 43 | 135 | 65 | 136 | - | 10.08 / 0.23 / 9.85 |
| softl-sos-core-b | 88 | 41 | 124 | 55 | 156 | - | 10.25 / 0.21 / 10.04 |
| softl-colsos-core-b | 85 | 39 | 116 | 61 | 149 | 25 | 9.88 / 0.25 / 9.62 |
| softl-all-core-b | 85 | 46 | 135 | 54 | 141 | 25 | 10.25 / 0.33 / 9.92 |

On C the column rung makes 29-40 of the soft-on-soft placements, but the
total on soft tops rises by 6 to 16 boxes in 48 episodes because the rescues
that made them before (the stack option 30 -> 12, the pocket guard's soft
pose 29 -> 20) now find the column already taken; the floor loses 11 boxes.
The credit moves from 10.96 to 11.25 an episode (+0.3 boxes), which is the
+1.3 to +1.8 soft points of section 3. The pocket-guard fixes move 40 soft
boxes from the floor to hard tops and credit nothing more. On B the column
rung's 25 placements displace the stack option's and the count pass's one
for one and the credit falls (9.94 -> 9.75 / 9.62).

The soft lever is not where the boxes rest: of 18.2 soft items an episode
the shipped form places 11.5 on C and 10.0 on B and covers 0.6 / 0.04, so
the uncredited soft cargo is the 6.7 to 8.2 soft boxes an episode the stream
still holds when the episode ends (38.6 of 61.5 items placed). Soft credit
rises with the item count, the channel the earlier rounds found exhausted
(`findings.md`, the platform refit), and a rung that relocates 0.3 boxes an
episode cannot move it.

## 6. What vetoes them (`softl_vetoes.py`, the records' `shadow` stats)

The shadow stats summed over the 48 episodes, and from the step logs the
soft-on-soft poses the shadow vetoed and the ladder kept (the official
simulator accepted every one) and the soft poses the physics resort
replaced after a wobble veto.

| record | checks | vetoes | soft-on-soft checks | replaced | kept after a soft veto | shadow s | soft-on-soft kept after veto | soft replaced by the resort after a wobble veto |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| ship-core | 3223 | 1263 | - | 49 | 19 | 627 | 17 | 14 |
| softl-base-core | 3407 | 1372 | - | 53 | 15 | 583 | - | - |
| softl-col-core | 3232 | 1281 | - | 55 | 14 | 626 | 13 | 15 |
| softl-pg-core | 3184 | 1244 | - | 47 | 15 | 616 | - | - |
| softl-sos-core | 3478 | 1373 | 163 | 47 | 1 | 522 | 0 | 3 |
| softl-colsos-core | 3454 | 1310 | 219 | 55 | 1 | 535 | 0 | 5 |
| softl-all-core | 3191 | 1184 | 203 | 49 | 4 | 499 | 0 | 2 |
| ship-core-b | 2043 | 38 | - | 1 | 21 | 320 | 12 | 32 |
| softl-base-core-b | 1959 | 26 | - | 1 | 16 | 394 | - | - |
| softl-col-core-b | 1989 | 25 | - | 1 | 17 | 415 | 11 | 33 |
| softl-pg-core-b | 2033 | 49 | - | 1 | 27 | 409 | - | - |
| softl-sos-core-b | 2147 | 38 | 262 | 0 | 7 | 308 | 0 | 9 |
| softl-colsos-core-b | 2104 | 21 | 272 | 0 | 6 | 324 | 0 | 6 |
| softl-all-core-b | 2119 | 41 | 253 | 1 | 7 | 427 | 0 | 9 |

(The C vetoes are almost all the sweep-shade veto, 1,175-1,349 a record; the
drift / tilt vetoes are the rest.) The shadow thresholds do what they were
built to do: the soft-on-soft poses kept after a veto go from 17 / 12 to 0,
the soft poses the resort replaced after a wobble veto from 14 / 32 to 2-9,
and the shadow's time falls by a sixth on C. The score does not follow
(section 3, 4): the vetoed poses were played anyway (a soft veto replaces a
pose only when the resort finds one it prefers), and the resort's
replacements were as good as the poses they replaced.

## 7. The shadow probe: does the shadow reject official-legal soft on soft?

`shadow_probe2.py` replays 29 target steps of the shipped records
(`targets_sos.txt`: the soft-on-soft poses the shadow had vetoed and the
ladder kept) in the official simulator and asks the shadow world about the
same action as shipped, after a pre-settle of 60 and 300 steps, and with
the packed items' poses re-imposed after 60 steps. Three targets replayed
as hard items the official world did not place and are left out; the 26
soft-on-soft cases (`probe_sos.jsonl`):

| | shipped thresholds 0.02 m / 5 deg | soft-on-soft thresholds 0.08 m / 12 deg |
|---|---:|---:|
| the shadow as shipped would veto | 25 of 26 | 3 of 26 |
| ... of which the official simulator accepted | 25 | 3 |
| after a 60-step pre-settle | 23 of 26 | 4 of 26 |
| the official settled pose itself over the thresholds | 18 of 26 | 4 of 26 |

The official simulator accepted all 26 (`is_placed_safe`), and its own
settle moved 18 of them past the shipped thresholds (up to 0.147 m / 23
degrees on `b-c2p-s0003`, accepted; its limits are 0.3 m / 45 degrees). So
the shadow's soft veto falsely rejected 25 of 26 official-legal
soft-on-soft placements, 96 %; at the soft-on-soft thresholds 3 of 26
(`c-c2-s0002` 0.099 m, `c-c2-s0010` 14.9 degrees, `b-c2p-s0003` 0.102 m /
11.4 degrees), each of which the official world also moved past them and
accepted. The shadow's disagreement with the official settle is small: the
median |drift error| is 1.2 cm as shipped, 0.3 cm after a 60-step
pre-settle, 0.4 cm after 300, 0.5 cm warm-started; the median |tilt error|
1.0 degree -> 0.6. The pre-settle is a correct fix for a disagreement that
was never the veto's problem: the shadow's drift is the official world's
drift, and the thresholds were set for hard boxes on hard tops.

## 8. The hard2 suite, Task C (base `ship-hard2`: 34.77, 47 of 96 counted, soft 23.3, placement 30.7)

The column rung and the full set on the 96-scene hard2 suite, whose boards
are 30-170 items and where half the episodes end under the count threshold.

| arm | score | delta [95 % CI] | counted | up / down | fill | cog | stability | placement | soft | placed |
|---|---:|---|---:|---|---:|---:|---:|---:|---:|---:|
| softl-col | 33.93 | -0.85 [-4.13, +2.34] | 45 (-2) | 36 / 24 | +0.5 | -1.3 | -1.9 | -2.6 | +0.6 | -0.32 |
| softl-all | 34.94 | +0.16 [-4.23, +4.64] | 47 (+0) | 43 / 35 | +0.9 | -0.2 | +0.4 | -0.7 | -0.3 | +0.76 |

Crossing swaps again make the intervals: softl-col crosses s0006, s0020 and
s0030 and loses s0021, s0056, s0059, s0065 and s0069 (eight swaps, -2 net);
softl-all swaps fourteen boards for a net of zero (the ship record's own
hard2 replicate swapped two, `findings.md`, "The shipped form on the
bench"). Over the episodes counted in both runs: softl-col +0.05 [-0.55,
+0.56] (n 88; soft +0.7, placement -1.1), softl-all +0.09 [-0.36, +0.50]
(n 82; soft +0.1, placement -0.8). The soft credit an episode is 14.75 on
the ship record, 14.61 on softl-col (the rung makes 233 of its 469
soft-on-soft placements and the floor loses 39 boxes, but the shelf loses
22 and the credit does not rise) and 15.15 on softl-all (+0.4 boxes, with
the pocket-guard fixes moving 37 boxes onto hard tops), for soft shares of
+0.6 and -0.3 points. The shadow's soft-on-soft thresholds take the soft
poses kept after a veto from 61 to 4. The slowest call 6.0-6.4 s against
the ship's 6.2 s. hard2 reads as core did: nothing clears its interval,
the soft share moves by less than a point, and the column rung costs
placement.

## 9. Reading

- The column rung is the only change that raises the soft credit, by 0.3
  boxes an episode on C (+1.3 to +1.8 soft points, +0.2 of score) and
  nothing on B, and it costs placement on C (priority boxes covered) and a
  settle-ended board on B. The soft cargo left uncredited is soft cargo the
  episode never reaches, not soft cargo put in the wrong place.
- The pocket-guard fixes move soft boxes off the floor onto hard tops and
  credit nothing; +0.24 on C and -0.36 on B ex-crossing, both inside their
  intervals.
- The shadow's soft-on-soft thresholds remove a 96 % false-veto rate on
  soft-on-soft poses, confirmed against the official simulator, and the
  score does not move because the vetoed poses were played anyway and the
  replacements were as good. They are correct and worthless on the bench's
  terms; the pre-settle shortens the shadow's time by a sixth on C.
- `softl-all` is the best reading on every suite (+0.53 C, +0.46 B
  ex-crossing, +0.09 hard2 ex-crossing), inside every interval, with the
  replicate of the ship arm reading -0.19 and -0.09: the sum of three
  neutral changes. The column rung alone reads -0.85 on hard2 with two
  crossings lost.

## 10. Recommendation

**None of the flags ships, on B or on C.** No arm's platform_score delta
clears its 95 % interval on any suite (core, core-b, hard2); the C readings lie inside the
spread of the ship arm's own replicate (-0.19 [-0.89, +0.39]), and the B
readings are crossing swaps at the 42-item threshold the platform does not
pay (its B episodes are all counted), with the ex-crossing deltas inside
+/-0.5. The soft share, the component this round was built for, moves by at
most +1.8 points on C and down on B. The flags stay off at their defaults.

What would be worth keeping on other grounds: the shadow's soft-on-soft
thresholds and pre-settle are a measured correction (the probe) with no
bench cost, and would matter if a later change made the ladder's soft
placements depend on the shadow's verdict; they are not shipped now because
they buy nothing now. The column rung should not be re-tried as a soft
lever; the soft lever on B and C is the item count.
