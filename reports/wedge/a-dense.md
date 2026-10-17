# The dense plan: what the c1x70 / c1x80 manifests need, what stands in physics, and what it is worth

The question (findings, "The platform's composition from the three
diagnostics"): the platform's four uncounted Task A episodes are dense
single-container manifests of the bench's c1x70 / c1x80 kind (70-80 items
in the c1 container, the threshold 36 / 41), each worth about 2.7 of the
total; the shipped form (v57, `arm_acsfix_a` with the dry-run off) places
29-36 there and counts 2/12 at 70 and 0/12 at 80 on the bench
(`reports/bench/acsfix30-dense-a`, the 30 s offline budget that stands for
the platform's 140 s).  Is there a plan that holds the threshold on these
manifests, in physics, without losing c1x50 / c1x60, core-a or hard-a?

Code: `rule_alpha/count_secure.py` (`plan_dense`, the `dense` token of
`plan_count_secure_blocks`; `_plan_soft_cap`), `rule_alpha/planner.py`
(`replay` lifts the cap for the plan's capped poses), the flags
`plan_count_secure_soft_cap`, `plan_count_secure_dense_ledge`,
`plan_count_secure_dense_when_short` in `rule_alpha/config.py`; tests
`tests/test_count_secure.py::DensePlanTest`.  Scripts, the analytic sweeps
and the local physics records in `reports/wedge/a-dense/`.  Arms
`reports/bench/arms/arm_adense_a.txt` (the form) and `arm_acap_a.txt` (the
soft cap alone); records `reports/bench/adense30-*` (the dense plans
ranked like any re-plan), `adenses30-*` (the dense plans only while the
count is short, the default) and `acap30-dense-a`, priced with
`bench.platform_score` against the v56/v57 records `acsfix30-*` and the
shipped race `ship30-*`.

## 1. What the x70 / x80 plan needs

The v57 plan on x80-s0003 (`acsfix30-dense-a`: 35 placed of 80, 7 soft, 7
priority, fill 51.9) is two flat layers of six 0.65 x 0.45 x 0.25 boxes
(tops 0.29 and 0.54 m), fifteen 0.55 x 0.40 x 0.24 boxes standing on
their 0.24 x 0.40 face (top 1.09 m; a flat third layer's top would land
in the mid-height transport band) and seven soft boxes flat on the
standing tops, one layer deep.  The count frame -- the 41 smallest items,
every priority item among them -- is 20 soft, 15 hard 0.55 x 0.40, 4
priority 0.55 x 0.40 and 2 hard 0.65 x 0.45; its volume is 0.45 of the
container, so volume is not the limit.  Three things are:

1. **The soft gallery is one layer deep.**  Soft carries soft only under
   `soft_structure_max_top` (0.7 m, the ladder's cap: it keeps the
   ladder's soft columns to the two or three layers the soft carpet
   needs), and the plan's soft cargo rides on the hard rows at 0.94-1.09
   m.  The 1.4 x 1.37 m of standing tops hold 7-8 flat soft boxes, and
   the 0.25-0.45 m under the ceiling above them hold nothing else.
   Lifting the cap for the plan alone (`plan_count_secure_soft_cap`,
   sweep `sw2`) adds 2-4 items on the shipped standing layer: a second
   layer of the 0.20 m boxes to 1.52 m (the 0.23 m ones would reach 1.55,
   over the validator's ceiling at about 1.536 m).  x70-s0005's plain
   re-plan reaches its threshold (36) that way; nothing else does.
2. **The standing layer is too tall for two soft layers.**  The 0.55 m
   standing boxes top at 1.09 m; on edge (0.40 m tall, 0.55 x 0.24
   footprint) they top at 0.94 m, where two flat soft layers fit (1.17,
   1.40 m).  The row planner's count-first layout search takes the 0.55 m
   pose (15 boxes against 11-12 on edge) because it does not know about
   the soft layers above; capping the standing rows at 0.40 m
   (`plan_standing_rows_max_height`) alone *loses* 2-6 items (`sw1`,
   `sw4`): the priority 0.55 x 0.40 boxes land in the back rows of the
   on-edge layer under the size-mixed order the shipped token plans in,
   and normal soft may not cover priority cargo, so the soft rows over
   them are refused.
3. **The chamfer ledge is never used.**  The c1 container's small shelf
   over the chamfer pocket (x -0.96..-0.52, top 0.845 m, the whole 1.37 m
   depth) takes five 0.65 x 0.35 x 0.23 boxes standing on their 0.35 x
   0.23 face (tops 1.50 m); the row planner never rests cargo there
   because a box dropped over the ledge fits under it and lands in the
   chamfer (`a-soft-frame.md`).  A ledge pose's bottom is at the
   mid-height level, so the simulator slides it in at its own height
   (`transport.transport_lifts`), across the standing layer's left
   column: the ledge must be loaded *before* the standing layer, and the
   planner's sweep enforces that order by refusing the pose afterwards.

Together: 12 flat + 5 on the ledge + 11-12 standing + 2 x 7-8 soft = 42-44
slots on x80-s0003 against the 41 the count asks.  That is the whole
margin; every layer has to replay.

## 2. What was built (all off by default)

`plan_count_secure_blocks` token `dense` (`count_secure.plan_dense`),
planned like the other count-secured re-plans and ranked with them:

1. the hard cargo's flat layers (`pack_rows` with the standing rows off:
   the row planner's two layers of the boxes that tile the floor);
2. `plan_count_secure_dense_ledge` (on): the frame's normal soft boxes
   standing on the ledge, from the back (`pack_typed_gallery` mode
   `column` with no rows, the soft frame block's 4 cm replay nudge on
   the entries);
3. the standing layer (`pack_rows` with `plan_standing_rows`, the poses
   up to `plan_standing_rows_max_height`), the normal hard boxes first
   and the priority ones last, so the priority boxes take the front rows
   and the soft rows over the back are not kept off them;
4. the soft cargo in flat rows over the standing tops, its own row lines,
   layer upon layer while the re-plan's cap lets soft carry soft: the
   frame's normal soft boxes first, the priority soft last (they may
   cover the priority hard boxes in front);
5. the rest for fill: the bigger hard cargo on the rows' lines, the pose
   search.

`plan_count_secure_soft_cap` (-1: off): the soft-structure cap every
count-secured re-plan is planned under, the soft floor share waived with
it (`_plan_soft_cap`, the same device as the `soft_structure` variant's).
The plan's soft poses off the floor carry it (`soft_cap`) and
`planner.replay` validates them under it; the ladder's own placements
keep the online cap.  The `plain` re-plan gains its second soft layer
from it too.

`plan_count_secure_dense_when_short` (on): the dense tokens are skipped
while a plan so far holds the threshold plus `plan_value_margin`.  On the
c1x50 manifests the plain re-plan's 27-33 already count, and the dense
plan's 36-40 would win the rank on the plan score's count weight (3)
while leaving the priority hard boxes out of the standing layer, which
the platform's placement component prices once the episode counts.

The form (`arm_adense_a.txt`): the v57 arm plus
`plan_count_secure_soft_cap=1.6,
plan_count_secure_blocks=plain;dense;dense@plan_standing_rows_max_height=0.4`
-- the dense plan with the shipped standing layer and with the on-edge
one, the higher-ranked taken.  Every pose goes through the planner's
validator (the transport sweep with the simulator's lift rules, the cover
rule, the support share), so the plan is feasible on the analytic model;
the tests check the layers' order, the ledge poses on the shelf's top,
the priority boxes last in the standing layer, the two soft layers above
the online cap, the plan legal step by step under its cap, and the replay
lifting the cap for a capped pose only.  248 tests in
`tests.test_rule_alpha tests.test_agent tests.test_bench
tests.test_count_secure` pass.

## 3. Analytic plans (the planner alone, 30 s budget, the dense plans ranked like any re-plan)

`sweep.py`, `sw_dense_all.jsonl`, `tab.py`; per count over 12 seeds: the
plan the re-plan started from, the plain re-plan's, the plan with the
dense plans among the candidates; the plans at or over the threshold;
the soft and priority boxes planned; the planner's seconds (every
re-plan included).

| items | base plan | plain re-plan | with the dense plans | plans over the threshold: base / plain / with dense | dense chosen | soft planned: plain / with dense | priority planned: plain / with dense | planner s |
|---|---:|---:|---:|---|---:|---|---|---:|
| c1x50 (26) | 24.1 | 27.2 | 33.7 | 4 / 10 / 11 of 12 | 8 | 7.0 / 11.2 | 4.4 / 3.3 | 5.9 |
| c1x60 (31) | 25.2 | 31.4 | 40.0 | 0 / 7 / 12 of 12 | 12 | 7.3 / 15.5 | 5.0 / 2.1 | 8.4 |
| c1x70 (36) | 25.1 | 31.8 | 40.8 | 0 / 3 / 12 of 12 | 12 | 7.5 / 16.1 | 5.2 / 1.7 | 9.4 |
| c1x80 (41) | 25.2 | 32.4 | 42.1 | 0 / 0 / 11 of 12 | 12 | 8.1 / 17.6 | 5.3 / 1.2 | 12.4 |

(Per scene in `sw_dense_all.md`.)  The dense plans hold 38-44 items on
every c1x60-c1x80 manifest (x80-s0007 40, one under its threshold); the
on-edge form is chosen on 36 of the 44 scenes where a dense plan is, the
0.55 m one where the manifest has few 0.55 x 0.40 boxes.  The price is
the priority cargo: the dense plan holds 0-3 of the 5-10 priority items
(the priority hard boxes come last in the standing layer and the
0.75 x 0.56 x 0.27 priority boxes nowhere), against plain's 4-9.  The
three re-plans take 5-9 s here (plain 2-3 s, each dense plan 2-4 s),
12-30 s on the platform's machine; the planner's total 6-14 s at the 30 s
budget.

The ablations that led here (`sw1`-`sw4`, x70 seeds 1, 3, 5 and x80 seeds
3, 5, 9; planned items): the shipped form 33-34 / 34-35; the on-edge cap
alone 23-30 (the priority boxes block the soft rows); the soft cap alone
31-37 (one at the threshold); both 26-32; the dense token 40-44 on all
six.

## 4. Local physics (`python -m bench run`, physics, policy budget 4.5 s, offline budget 30 s)

`phys/`, `phys_tab.py`; against the v56 records at the same budget
(`acsfix30-dense-a`; the v57 form differs by the dry-run only, which
loses every race here):

| scene | threshold | v56 placed / soft / prio | dense placed / soft / prio | pick | plan (plain / dense / edge) | plan poses replayed | topples | CoM | optimize s v56 -> dense |
|---|---:|---|---|---|---|---:|---:|---:|---|
| a-c1x70-s0001 | 36 | 29 / 6 / 6 | **43** / 19 / 2 (counted) | dense on edge | 32 / 41 / 43 | 43 of 43 | 0 | 0.439 | 20.0 -> 10.0 |
| a-c1x70-s0003 | 36 | 34 / 6 / 6 | **40** / 16 / 2 (counted) | dense on edge | 34 / 40 / 40 | 40 of 40 | 0 | 0.424 | 25.1 -> 8.4 |
| a-c1x80-s0003 | 41 | 35 / 7 / 7 | **44** / 20 / 3 (counted) | dense on edge | 35 / 41 / 44 | 43 of 44 | 0 | 0.450 | 26.9 -> 9.5 |
| a-c1x80-s0009 | 41 | 30 / 5 / 8 | **41** / 14 / 1 (counted) | dense | 31 / 41 / 39 | 41 of 41 | 0 | 0.426 | 27.9 -> 14.1 |

**What stands.**  Every planned pose replayed (x80-s0003: 43 of 44, the
last a stack-option pose of the ladder for a standing 0.60 x 0.30 x 0.25
box the plan had on the flat tops at the right edge), and no box toppled
under the shake in any of the four episodes:

- the ledge: four 0.65 x 0.35 x 0.23 boxes and one 0.45 x 0.30 x 0.20
  standing on the shelf's top at 0.845 m (tops 1.50 and 1.30 m), the
  shadow's settle drift 6 cm (the drop onto the shelf), no lateral
  drift, no tilt;
- the on-edge layer: eleven 0.55 x 0.40 x 0.24 boxes on their 0.55 x
  0.24 face at 0.54 m (top 0.94), drift under a millimetre;
- the soft layers: six 0.65 x 0.35 x 0.23 flat at 0.94 m (drift 2-4 mm,
  tilt under 0.3 degrees) and eight soft boxes on them at 1.17 m (drift
  0.9-2.5 cm, tilt 0.5-1.1 degrees: the soft support compresses, and
  `plan_replay_drop` 3 cm absorbs it), the 0.60 x 0.30 x 0.25 boxes flat
  among them;
- a 0.60 x 0.30 x 0.25 box standing (0.60 m tall on 0.25 x 0.30) on the
  flat hard tops at the right edge, and a 0.55 x 0.40 x 0.24 standing
  0.55 m tall beside it with a soft box on top.

The episodes end on a decline once the plan is out (the 0.75 x 0.56 x
0.27 boxes and the rest of the 0.65 x 0.45 ones have no legal pose), 4-9
items over the threshold.  The load is higher (centre-of-mass ratio 0.42-
0.45 against 0.39-0.42) and the fill +5 to +10 points.

## 5. CI (physics, policy budget 4.5 s, 6 shards, offline budget 30 s)

`bench.platform_score` against the v56 form at the same budget
(`acsfix30-*`: the dry-run on, which the shipped v57 turned off; on
core-a four scenes change for that alone, see below) and against the
shipped race (`ship30-*`).  Forms: `adense` = the arm above (the dense
plans ranked like any re-plan); `adenses` = the same with
`plan_count_secure_dense_when_short`; `acap` = the v57 form with the
plan-only soft cap alone.  Columns as `platform_score` prints them: the
score, the paired delta with the bootstrap interval, the counted
episodes, episodes up / down, the five components' deltas, placed, the
policy's max step time.

**dense-a** (base `ship30-dense-a`: 22.27, counted 10 of 48; v56
`acsfix30-dense-a`: 38.27, counted 23)

| form | record | score | delta vs shipped [95 % CI] | delta vs v56 [95 % CI] | counted | up / down vs v56 | fill | cog | stab. | place. | soft | placed |
|---|---|---:|---|---|---:|---|---:|---:|---:|---:|---:|---:|
| v56 | `acsfix30-dense-a` | 38.27 | +16.00 [+9.52, +23.28] | base | 23 | - | +2.1 | +20.3 | +26.5 | +23.8 | +14.0 | +2.88 |
| dense | `adense30-dense-a` | **66.24** | +43.97 [+38.07, +49.39] | **+27.97 [+20.81, +35.34]** | **47** (+24) | 40 / 4 | +11.5 | +30.5 | +48.4 | -2.0 | +57.5 | +8.33 |
| dense, when short | `adenses30-dense-a` | 64.07 | +41.80 [+36.05, +47.22] | +25.80 [+18.64, +33.06] | 47 (+24) | 37 / 5 | +9.4 | +31.7 | +48.3 | +0.6 | +42.0 | +6.42 |
| the cap alone | `acap30-dense-a` | 38.94 | +16.67 [+10.06, +23.76] | +0.67 [+0.09, +1.41] | 23 (+0) | 25 / 4 | +1.0 | -0.3 | -0.4 | +1.6 | +2.0 | +0.69 |

By count (v56 -> dense; counted of 12, placed, soft placed, priority
placed, shake topples, the dense plan picked, the optimize seconds with
the maximum; `ci_tab.py`, `ci_adense30_dense.md`):

| items (threshold) | counted | placed | soft | priority | topples | dense picked | optimize s (max) |
|---|---|---|---|---|---|---:|---|
| 50 (26) | 12 -> 12 | 27.7 -> 34.1 | 7.0 -> 11.2 | 4.1 -> 3.3 | 0 -> 1 | 8 | 14.4 -> 7.5 (10.9) |
| 60 (31) | 9 -> **12** | 31.4 -> 40.2 | 6.8 -> 15.5 | 4.8 -> 2.1 | 0 -> 0 | 12 | 17.2 -> 10.3 (12.3) |
| 70 (36) | 2 -> **12** | 31.8 -> 40.9 | 6.8 -> 16.1 | 5.3 -> 1.7 | 0 -> 0 | 12 | 20.5 -> 11.6 (13.8) |
| 80 (41) | 0 -> **11** | 33.0 -> 42.1 | 7.0 -> 17.6 | 5.1 -> 1.3 | 0 -> 0 | 12 | 23.8 -> 15.5 (19.8) |

Every c1x60, c1x70 and c1x80 episode but one counts: the dense plan was
picked on 44 of 48 scenes (the on-edge form on 34, the 0.55 m standing
form on 10) and placed 32-44 items: the plan exactly on 37 scenes and
one over it on 7 (a box of the ladder's), never under it.  The one miss is a-c1x80-s0007 (40 of
41: its plans are 40 and 39, the standing layer fifteen 0.55 m boxes
with one soft layer, or eleven on edge with two; the 0.75 x 0.56 x 0.27
boxes are a quarter of that manifest).  The four scenes down against
v56 are counted scenes whose priority cargo the dense plan dropped
(a-c1x50-s0006 4 -> 1 of 5, -0.9; a-c1x60-s0005 4 -> 1, -1.9;
a-c1x60-s0006 5 -> 1, -3.1; a-c1x70-s0005 3 -> 0, -1.8); the one topple
is a-c1x50-s0011's.  The placement component is the only one down (-2.0:
priority placed 4.8 -> 2.1 a scene), against fill +11.5, soft +57.5
(soft placed 6.9 -> 15.1), cog +30.5 and stability +48.4 from the 24
crossings.

The when-short guard keeps the priority boxes where the plain re-plan
already holds the gate (placement +0.6 against -2.0) and forgoes the
dense plan's soft and fill there (soft +42.0 against +57.5, fill +9.4
against +11.5): 2.2 points under the unguarded form over the suite, the
same 47 counted.  So the guard is off by default and the form above is
the candidate.

The cap alone (the second soft layer on the shipped 1.09 m standing
tops, 1.32 -> 1.52 m, the 0.20 m boxes only) gains +0.67 and no
crossing, and adds eight shake topples in five episodes (a-c1x50-s0003,
s0006, s0011, a-c1x70-s0012, a-c1x80-s0010: 0.60 x 0.30 x 0.25 and
0.45 x 0.30 x 0.20 boxes on soft at 1.22-1.41 m); the dense plan's second
layer sits at 1.17-1.40 m on the 0.94 m on-edge tops and toppled once in
48 episodes.

**core-a** (base `ship30-core-a`: 66.19, all 48 counted; v56
`acsfix30-core-a`: 66.47; the planner alone on the shipped form,
`aplan30-core-a`: 66.67)

| form | record | score | delta vs shipped [95 % CI] | delta vs v56 [95 % CI] | delta vs planner alone [95 % CI] | counted | up / down vs v56 | fill | cog | stab. | place. | soft | placed |
|---|---|---:|---|---|---|---:|---|---:|---:|---:|---:|---:|---:|
| dense | `adense30-core-a` | 67.02 | +0.83 [-0.01, +1.97] | +0.55 [-0.20, +1.65] | +0.35 [-0.15, +0.92] | 48 | 4 / 1 | -0.2 | +0.5 | +0.0 | +0.8 | +2.6 | +0.04 |
| dense, when short | `adenses30-core-a` | 66.86 | +0.67 [-0.11, +1.78] | +0.39 [-0.27, +1.40] | +0.19 [-0.23, +0.68] | 48 | 3 / 1 | -0.3 | +0.5 | +0.0 | +0.8 | +1.8 | -0.04 |

Against v56, five scenes change.  Three are the dry-run's (the v57 form
plans without it; no re-plan ran): a-c1-s0001 +1.7, a-c1-s0005 +2.7,
a-c1s-s0001 +20.7 (the v56 race took a dry-run plan with no soft and one
priority box; the planner's holds 10 and 5).  Two are the dense plan's:
a-c1-s0012 26 -> 30 placed, soft 5 -> 8, +7.7 (the plain re-plan 24, the
dense 30, the threshold 21); a-c1s-s0010 23 -> 28 placed, priority 4 ->
2 of 5, -6.4 (plain 22, dense 27, threshold 21: the two priority boxes
it drops cost more than the five items it adds, the case the guard was
written for; the guard does not catch it, since the plain re-plan's 22
is under the gate of 23).  The other 43 are identical in count, soft and
priority.  No topple added (4 -> 4).

**hard-a** (base `ship30-hard-a`: 39.93, counted 26 of 48; v56
`acsfix30-hard-a`: 45.95, counted 31)

| form | record | score | delta vs shipped [95 % CI] | delta vs v56 [95 % CI] | counted | up / down vs v56 | fill | cog | stab. | place. | soft | placed | topples |
|---|---|---:|---|---|---:|---|---:|---:|---:|---:|---:|---:|---:|
| v56 | `acsfix30-hard-a` | 45.95 | +6.01 [+1.18, +11.88] | base | 31 | - | +0.0 | +7.9 | +10.1 | +9.9 | +5.3 | +1.77 | 20 |
| dense | `adense30-hard-a` | 48.56 | +8.63 [+3.25, +14.82] | **+2.61 [-0.22, +6.61]** | **33** (+2) | 13 / 10 | +0.2 | +3.5 | +4.3 | +1.3 | +5.1 | +0.73 | **14** |

Crossings in: a-hard-s0016 (39 -> 41, the threshold 41) and a-hard-s0019
(62 -> 71 against 64; the plain re-plan under the plan cap, 78 planned);
none out.  The dense plan was picked on 10 of 48 scenes (hard-a's varied
containers: on s0038 32 -> 38 planned and 42 -> 49 placed, s0024 34 ->
43 planned, s0044 22 -> 28, s0047 50 -> 61 planned and 49 -> 54 placed
with 9 priority boxes fewer, -3.4; s0023 is the plain re-plan's 30 ->
27, -10.9, a counted scene losing three priority boxes).  On the biggest
manifests (s0013, s0019, s0030, s0036, s0047: 88-120 items) the
on-edge dense plan was not started for want of budget (the record's
`skipped` with the seconds left), and on s0030 / s0036 neither dense
plan; the planner's time there is 24-30 s of the 30, the maximum of the
suite.  Shake topples 20 -> 14 (s0024 3 -> 0, s0030 3 -> 0, s0023 1 ->
0), every episode ending on a decline.

## 6. Verdict

- **What the x70 / x80 plan needs** is three things the row pipeline did
  not have: a second soft layer (the plan's own soft-structure cap, with
  the replay validating under it), a standing layer low enough for two
  soft layers to fit under the ceiling (the 0.55 x 0.40 boxes on edge,
  top 0.94 m, with the priority boxes last so the soft rows over the back
  are not kept off them), and the chamfer ledge (five standing soft
  boxes, loaded before the standing layer because a ledge pose slides in
  at its own height).  Each alone loses or gains two items; together
  they plan 38-44 on every c1x60-c1x80 manifest.
- **The physics takes it.**  Soft on soft at 1.17-1.40 m over the on-edge
  tops stands and does not topple under the shake (one topple in 48
  dense-a episodes, 14 against 20 on hard-a); the ledge boxes stand at
  0.845-1.50 m; the plans replay pose for pose (never under the plan on
  dense-a).  The cap alone, with the second layer at 1.32-1.52 m on the
  1.09 m standing tops, topples eight times in five episodes: the height
  matters, not the soft support.
- **The verdict (`bench.platform_score`, 30 s budget):** dense-a **+27.97
  [+20.81, +35.34]** over the v56 form (+43.97 over the shipped race),
  counted 23 -> **47 of 48** (c1x50 12/12, c1x60 12/12, c1x70 12/12,
  c1x80 11/12 against 12 / 9 / 2 / 0); core-a +0.55 [-0.20, +1.65], 48 of
  48, two scenes the dense plan touched (+7.7, -6.4); hard-a +2.61
  [-0.22, +6.61], counted 31 -> 33, none out, topples 20 -> 14.  Ship
  candidate: `arm_adense_a.txt` (the v57 form plus
  `plan_count_secure_soft_cap=1.6` and
  `plan_count_secure_blocks=plain;dense;dense@plan_standing_rows_max_height=0.4`).
  On the platform's terms the four uncounted A episodes are of the kind
  this crosses 23 of 24 times on the bench, about 2.7 points each.
- **The price** is the priority cargo on the dense manifests: 4.8 -> 2.1
  priority boxes placed a scene on dense-a (placement -2.0 against the
  other four components +147), and two of hard-a's counted scenes lose
  priority boxes (-3.4, -10.9).  The when-short guard, which keeps the
  priority boxes where the plain re-plan already holds the gate, is
  worth -2.2 on dense-a (soft and fill forgone) and is off.  A dense
  plan that stands the priority hard boxes in the soft layers' front
  strip, where the count still holds, is the next lever (one priority
  box is worth about three soft boxes on a counted episode).
- **Time.** The planner's seconds a dense-a episode 4.6-9.8 -> 1.3-19.8
  (the three re-plans 2-4 s each here); the optimize time is under v56's
  on every suite because the dry-run is off (v57), 9.8 s mean and 29.9 s
  maximum on hard-a.  On the platform's machine (2.4-5 times slower) the
  biggest hard-a manifests would skip the dense plans as the bench did;
  the dense manifests' 10-20 s here are 25-100 s there, inside the 140.
