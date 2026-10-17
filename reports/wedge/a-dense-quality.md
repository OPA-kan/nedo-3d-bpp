# The dense plan's quality: the priority boxes back in the standing layer, where the count still holds

The question (findings, "v58: the dense plan shipped"): the dense plan
(`reports/wedge/a-dense.md`) crosses the count on the c1x60-c1x80
manifests but leaves the priority hard boxes out -- 4.8 -> 2.1 priority
boxes placed a scene on dense-a, placement -2.0 against +147 on the other
four components -- because it stands them last in the standing layer,
after the normal boxes of their class have filled it.  A priority box
placed is worth about 1.4-1.8 points on a counted episode (placement
.143 x 100 / the priority total), a soft box 0.6-0.7, a hard box's fill
0.4.  Is there a dense plan that keeps the priority hard boxes without
losing the count, and what is it worth on the platform's terms?

Code: `rule_alpha/count_secure.py` (`priority_strip`, the strip, thin-first
and priority-first fill branches of `plan_dense`), the flags
`plan_count_secure_dense_priority_rows`,
`plan_count_secure_dense_soft_thin` and
`plan_count_secure_dense_priority_fill` in `rule_alpha/config.py` (all off
by default); tests `tests/test_count_secure.py::DensePriorityStripTest`.
Scripts, the analytic sweeps and the local physics records in
`reports/wedge/a-dense-quality/`.  Arms `reports/bench/arms/arm_adenseq_a.txt`
/ `arm_adenseq2_a.txt` (the strip on every dense plan: not run on CI, see
section 3) and `arm_adenser_a.txt` (the form: the strip as a token of its
own, ranked); records `reports/bench/adenser30-*`, priced with
`bench.platform_score` against the v58 records `adense30-*`.

## 1. Where the priority boxes go in the v58 plan

x80-s0003 (`dense_probe.py`): 13 priority items -- 4 of the 0.55 x 0.40
x 0.24 class, 5 of 0.75 x 0.56 x 0.27, 1 of 0.65 x 0.45 x 0.25, 3 soft.
The on-edge dense plan (44 planned) holds 3: the three priority soft
boxes in the second soft layer.  The standing layer is eleven 0.55 x 0.40
boxes on edge, all normal: the plan orders the normal boxes of the class
first so that the priority boxes take the front rows (nothing normal may
cover a priority box, and the soft rows go over the back), but the class
has 15 normal boxes and the layer holds 11, so the priority four never
get a turn.  The fill pass after the soft rows stands one more normal
0.55 x 0.40 box at the layer's right edge (step 40) -- a slot a priority
box of the class could take with nothing over it.  The 0.75 x 0.56
priority boxes have no standing pose under the 0.40 m cap (on their
side they are 0.56 or 0.75 m tall) and no flat slot: they are out of
every dense plan.

So three levers, all on the standing layer and its fill:

1. **The priority strip** (`plan_count_secure_dense_priority_rows`): the
   normal standing rows keep off a front strip as deep as the priority
   boxes' shallowest standing pose a row (the 0.55 x 0.40 class on edge:
   0.24 m plus the gap; two a row across the 1.47 m floor), the priority
   boxes stand there after them (the rows behind are loaded first), the
   normal boxes left take what the strip has left, and the normal soft
   rows over the top stop at the priority boxes' back edge (the priority
   soft may still cover them).  One row holds two priority boxes, two
   rows four.
2. **Thin-first soft rows** (`plan_count_secure_dense_soft_thin`): the
   soft rows' count-first layout search sizes a row for its floor layer
   alone, and in the depth left behind the strip it takes a row of the
   0.50 x 0.40 x 0.40 boxes (two on the floor layer against two 0.23 m
   ones) and loses the second layer the dense plan lives on (x80-s0003
   with a one-row strip: 5 soft in the layers against 11).  With the cap
   at 0.25 the 0.45 x 0.30 x 0.20, 0.65 x 0.35 x 0.23 and 0.60 x 0.30 x
   0.25 classes go first in rows of their own, the 0.40 m boxes after
   (9 soft in the layers).
3. **Priority-first fill** (`plan_count_secure_dense_priority_fill`): the
   fill passes after the soft rows (the hard cargo on the rows' lines,
   then the pose search) take the priority hard boxes before the normal
   ones.  Whatever the fill places is never covered by the plan's soft
   rows, which are laid by then, so a priority box there keeps its
   credit; the right-edge slot above is the case.

Every pose still goes through the planner's checks (the validator with
the transport sweep, the cover rule, the support share, the re-plan's
soft cap), so what a plan holds is what the analytic replay places.

## 2. The plan alone (`plan_dense` on the on-edge form, 48 dense scenes)

`sweep.py`, `sw_strip.jsonl`, `tab.py`: one `plan_dense` per scene and
variant, the plans priced by the platform's arithmetic on the plan
itself (the five weights, the count gate at the threshold, the fill from
the planned volume, the cog from the plan's mass-weighted centre, no
topples), relative to the v58 plan per scene.  `fill` is the
priority-first fill alone; `p1t` the one-row strip with the thin-first
rows; `p1tf` both with the fill; `p2tf` a two-row strip.

| items (threshold) | variant | planned | plans over the threshold | soft | priority (hard) | com | price vs v58 |
|---|---|---:|---:|---:|---:|---:|---:|
| 50 (26) | v58 | 36.4 | 12 of 12 | 13.2 | 2.1 (0.6) | 0.423 | - |
| 50 | fill | 35.4 | 12 | 12.2 | 3.3 (1.5) | 0.415 | +2.64 |
| 50 | p1tf | 35.8 | 12 | 12.0 | 4.3 (2.5) | 0.423 | +5.12 |
| 60 (31) | v58 | 39.6 | 12 of 12 | 15.5 | 2.1 (0.3) | 0.439 | - |
| 60 | fill | 39.1 | 12 | 15.2 | 3.2 (1.3) | 0.435 | +2.40 |
| 60 | p1tf | 38.3 | 12 | 14.1 | 4.6 (2.6) | 0.436 | +4.57 |
| 70 (36) | v58 | 40.2 | 12 of 12 | 16.4 | 1.8 (0.3) | 0.445 | - |
| 70 | fill | 39.9 | 12 | 16.1 | 2.8 (1.2) | 0.442 | +1.71 |
| 70 | p1tf | 38.6 | 11 | 14.5 | 5.0 (2.9) | 0.438 | +2.19 |
| 80 (41) | v58 | 41.8 | 10 of 12 | 17.8 | 1.5 (0.0) | 0.454 | - |
| 80 | fill | 41.5 | 10 | 17.5 | 3.0 (1.0) | 0.453 | +2.25 |
| 80 | p1tf | 39.8 | **3** | 15.4 | 5.1 (3.0) | 0.442 | **-14.45** |
| 80 | p2tf | 37.8 | 1 | 13.6 | 6.2 (3.9) | 0.433 | -20.70 |

(The whole table, every variant, in `sw_strip.md`.)  Two readings:

- **The fill alone is free.**  +1.2 priority hard boxes a plan for 0.3-0.5
  items, no plan under the threshold that was over it, 42 of 48 scenes up
  and 2 down: +2.25 over the suite.
- **The strip costs two items a plan, and c1x80 cannot spare them.**  The
  one-row strip with the thin-first rows and the fill holds 2.8 priority
  hard boxes a plan (v58: 0.3) and 1.4 items fewer; on c1x50-c1x70 that
  is +2.2 to +5.1 with the count kept (one x70 plan at 35 against 36),
  but on c1x80, where the v58 plans hold 41-44 against a threshold of 41,
  the strip's plans hold 38-41 and 7 of the 10 crossings are lost
  (-14.45; the two-row strip -20.70).  The thin-first rows alone (`thin`)
  are a loss (-1.9: without the strip the layout search had the whole
  depth, and the pass order only takes the 0.40 m boxes' slots away) and
  the strip without them (`p1f`) loses the second soft layer (-5.8).

So the fixed strip (`arm_adenseq_a.txt`) is wrong on the one layout the
dense plan was built for, and was not run on CI.  The strip has to be
taken where the count still holds -- which is what the re-plan's rank
already does.

## 3. The form: the strip as a ranked token

`arm_adenser_a.txt`: the v58 arm plus `plan_count_secure_dense_priority_fill`
(on every dense plan) and a fourth count-secured token,
`dense@plan_standing_rows_max_height=0.4&plan_count_secure_dense_priority_rows=1&plan_count_secure_dense_soft_thin=0.25`,
beside the three of v58.  `count_secure.secure_count` ranks the plans a
plan over the gate (the threshold plus `plan_value_margin`) first, then
by the plan score (`plan_score_weights=1;0.5;0.5;3`: the fill, half the
soft share, half the priority share, three times the item share), under
the threshold by the count; so the strip's plan wins where it holds the
gate, or where neither it nor the unstripped plan does and the score
prefers its priority boxes, and loses where it drops under the threshold.
The plan score prices a priority box at about 1.3 soft boxes (the
platform: about 2.5), so the rank is conservative.

`rank_sweep.py`, `rank_dense.jsonl`, `picks.py`: the planner alone
(`agent.optimize`, the 30 s offline budget) per scene for the v58 arm
and the form; the plan it ships, and every variant's count.

| items (threshold) | arm | planned | over the threshold | soft | priority (hard) | com | price vs v58 | planner s |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| 50 (26) | v58 | 33.7 | 11 of 12 | 11.2 | 3.3 (1.7) | 0.404 | - | 6.9 |
| 50 | form | 32.7 | 11 | 10.2 | 4.4 (2.6) | 0.397 | +1.60 | 8.4 |
| 60 (31) | v58 | 40.0 | 12 of 12 | 15.5 | 2.1 (0.4) | 0.444 | - | 9.4 |
| 60 | form | 39.2 | 12 | 14.6 | 4.2 (2.2) | 0.440 | +3.89 | 11.2 |
| 70 (36) | v58 | 40.8 | 12 of 12 | 16.1 | 1.7 (0.3) | 0.450 | - | 10.3 |
| 70 | form | 39.9 | 12 | 15.7 | 4.3 (2.2) | 0.444 | +4.98 | 12.3 |
| 80 (41) | v58 | 42.1 | 11 of 12 | 17.6 | 1.2 (0.0) | 0.457 | - | 13.5 |
| 80 | form | 41.7 | 11 | 17.2 | 3.2 (1.0) | 0.456 | +3.21 | 16.1 |
| all | form | 38.4 (v58 39.1) | 46 of 48 (46) | 14.4 (15.1) | 4.0 (2.1) | 0.434 (0.439) | **+3.42**, 40 up / 3 down | |

(`rank_dense.md`, the picks in `picks.txt`, `rank_picks.py`.)  The same
46 of 48 plans over the threshold, the priority boxes planned 2.1 ->
4.0 a scene (the hard ones 0.6 -> 2.0) for 0.7 items and 0.7 soft boxes
fewer.  The strip's plan is picked on 16 of the 48 scenes (x50 2, x60
7, x70 6, x80 1: x80-s0005, where it holds the threshold exactly and
stands 5 of its 13 priority items against 0), the unstripped on-edge
plan with the priority-first fill on 21, the 0.55 m standing plan on 7
and the planner's own plan on 4 (x50, as v58).  On c1x80 the rank falls
back as meant: the strip's plans hold 38-41 against the thresholds and
are out-ranked by the unstripped 41-43 everywhere but s05.  The three
scenes down are x50's, the fill's (-0.6 to -1.5: a priority box placed
first in the fill changes what the pose search finds after it, 1-5 items
on x50-s0002 for one priority box).  The planner's time grows 1.5-2.6 s
a scene here for the fourth plan (4-13 s on the platform's machine); on
the biggest hard-a manifests the start-factor guard skips it as it
skips the on-edge plan today.

## 4. Local physics (`python -m bench run`, physics, policy budget 4.5 s, offline budget 30 s)

`phys/`, `phys_tab.py`: the v58 arm and the form on the same scenes,
priced by `bench.platform_score` (the one-scene score, so the paired
difference is the platform's per-episode price):

| scene | threshold | arm | placed / soft / prio (covered) | pick (planned; flat / ledge / standing / soft) | plan poses replayed | topples | CoM | score | optimize s |
|---|---:|---|---|---|---:|---:|---:|---:|---:|
| a-c1x50-s0006 | 26 | v58 | 40 / 16 / 1 (0) | dense on edge (40; 12 / 5 / 11 / 10) | 40 of 40 | 0 | 0.421 | 67.52 | 7.624 |
| a-c1x50-s0006 | 26 | form | 40 / 16 / 3 (0) | dense on edge (40; 12 / 5 / 11 / 10) | 40 of 40 | 0 | 0.421 | 73.24 (+5.72) | 9.887 |
| a-c1x60-s0006 | 31 | v58 | 42 / 18 / 1 (0) | dense on edge (42; 12 / 5 / 11 / 11) | 42 of 42 | 0 | 0.432 | 67.10 | 9.91 |
| a-c1x60-s0006 | 31 | form | 41 / 17 / 3 (0) | dense on edge + strip (41; 12 / 5 / 11 / 8) | 41 of 41 | 0 | 0.432 | 72.05 (+4.95) | 10.944 |
| a-c1x70-s0001 | 36 | v58 | 43 / 19 / 2 (0) | dense on edge (43; 12 / 5 / 11 / 12) | 43 of 43 | 0 | 0.439 | 65.98 | 10.667 |
| a-c1x70-s0001 | 36 | form | 43 / 19 / 4 (0) | dense on edge (43; 12 / 5 / 11 / 12) | 43 of 43 | 0 | 0.439 | 69.16 (+3.18) | 14.42 |
| a-c1x80-s0003 | 41 | v58 | 44 / 20 / 3 (0) | dense on edge (44; 12 / 5 / 11 / 11) | 43 of 44 | 0 | 0.450 | 66.08 | 10.081 |
| a-c1x80-s0003 | 41 | form | 43 / 19 / 4 (0) | dense on edge (43; 12 / 5 / 11 / 11) | 42 of 43 | 0 | 0.445 | 66.46 (+0.37) | 11.749 |
| a-c1x80-s0005 | 41 | v58 | 42 / 18 / 0 (0) | dense on edge (42; 12 / 6 / 11 / 10) | 42 of 42 | 0 | 0.420 | 61.70 | 15.024 |
| a-c1x80-s0005 | 41 | form | 41 / 17 / 5 (0) | dense on edge + strip (41; 12 / 6 / 11 / 8) | 41 of 41 | 0 | 0.418 | 75.41 (+13.72) | 16.434 |

Every planned pose replayed but the one the v58 plan also misses on
x80-s0003 (the ladder's stack-option pose at the right edge), no box
toppled under the shake, every episode counted.  The strip's priority
boxes stand on edge in the front row at 0.54-0.94 m with the priority
soft over them where it fits (x80-s0005: five of its priority items
against none, +13.7); the fill's priority box at the layer's right edge
stands 0.55 m tall with nothing on it.  The centre of mass is level or
lower (the strip's row carries no second soft layer).  The optimize time
grows 1.5-4 s a scene for the fourth plan.

## 5. CI (physics, policy budget 4.5 s, 6 shards, offline budget 30 s)

`bench.platform_score` against the v58 records `adense30-*`:

Records `reports/bench/adenser30-*` (runs 725-727 of `bench-run.yml`,
fetched with `fetch.sh` and sorted by `sort_records.py`); columns as
`platform_score` prints them: the score, the paired delta with the
bootstrap interval, the counted episodes, episodes up / down, the five
components' deltas, placed, the policy's max step time.

| suite | v58 (`adense30-*`) | form (`adenser30-*`) | delta vs v58 [95 % CI] | counted | up / down | fill | cog | stab. | place. | soft | placed |
|---|---:|---:|---|---:|---|---:|---:|---:|---:|---:|---:|
| dense-a | 66.24 | **69.64** | **+3.40 [+2.46, +4.41]** | 47 (+0) | 40 / 3 | -0.9 | +0.6 | +0.1 | **+28.0** | -3.6 | -0.79 |
| core-a | 67.02 | 67.21 | +0.19 [+0.00, +0.56] | 48 (+0) | 1 / 0 | -0.0 | +0.1 | +0.0 | +1.2 | +0.0 | -0.04 |
| hard-a | 48.56 | 48.38 | -0.18 [-0.49, +0.08] | 33 (+0) | 2 / 4 | -0.4 | +0.3 | -0.1 | -0.7 | -0.1 | -0.15 |

**dense-a** by count (v58 -> form; `ci_tab.py`, `ci_adenser30_densea.md`;
the per-scene prices in `scene_delta.py`):

| items (threshold) | counted | placed | soft | priority | topples | dense picked (the strip) | optimize s (max) |
|---|---|---|---|---|---|---:|---|
| 50 (26) | 12 -> 12 | 34.1 -> 33.1 | 11.2 -> 10.3 | 3.3 -> 4.4 | 1 -> 0 | 8 (2) | 7.5 -> 8.7 (19.1) |
| 60 (31) | 12 -> 12 | 40.2 -> 39.5 | 15.5 -> 14.5 | 2.1 -> 4.2 | 0 -> 0 | 12 (7) | 10.3 -> 12.3 (19.9) |
| 70 (36) | 12 -> 12 | 40.9 -> 39.8 | 16.1 -> 15.6 | 1.7 -> 4.3 | 0 -> 0 | 12 (6) | 11.6 -> 13.7 (19.1) |
| 80 (41) | 11 -> 11 | 42.1 -> 41.7 | 17.6 -> 17.2 | 1.3 -> 3.2 | 0 -> 0 | 12 (1) | 15.5 -> 18.2 (22.9) |

The CI replays the analytic sweep scene for scene: the same 47 counted
(x80-s0007 the one miss, as in v58), the strip picked on 16 scenes, the
priority boxes placed 2.1 -> 4.0 a scene (placement 32.7 -> 60.7) for
0.8 items and 0.7 soft boxes fewer (fill -0.9, soft -3.6), the shake
topples 1 -> 0, no priority box covered.  The 40 scenes up gain +0.4 to
+13.7 (x80-s0005 0 -> 5 of 5 priority, x70-s0005 0 -> 5 of 5 +11.1,
x60-s0005 1 -> 5 +9.6, x70-s0009 1 -> 7 of 10 +9.0, x50-s0011 1 -> 6 of
6 and its topple gone +8.0); the three down are x50's (s0002 -0.6: the
fill's priority box costs five items and four soft boxes, s0003 -1.0 and
s0012 -1.4: one item each, no priority box gained), the cases the
analytic sweep showed.  The optimize time is 1-3 s a scene longer for
the fourth plan, 22.9 s at most, inside the 30.

**core-a**: one scene changes, a-c1s-s0010 (+9.0: the strip's plan, 28 ->
26 placed, priority 2 -> 5 of 5 -- the scene a-dense.md named as the
dense plan's priority cost, -6.4 against v56, recovered); the other 47
identical.

**hard-a**: six scenes change, -0.18 over the suite, no crossing moved.
Two are the strip's: a-hard-s0016 (41 -> 41 placed at its threshold, the
same 5 priority boxes, -0.7 on fill and cog) and a-hard-s0023 (27 -> 25,
priority 1 -> 0 of 4, -4.6: the strip's plan holds 30 against the on-edge
plan's 26 and loses its priority box in the replay).  a-hard-s0024 (-5.2,
priority 9 -> 4) picks the same on-edge plan as v58 from a different
planner run (its plans 44 / 45 planned against v58's 34 / 43: the row
planner's layouts differ run to run on the varied containers).  The
other three are the budget's on the 88-120 item manifests: a-hard-s0013
(-1.1) and s0047 (+1.8) take the plain re-plan where v58 took the dense
one (the planner's own variants ran 0.3-0.9 s longer and the dense plan
was not started), s0030 (+1.3) the 0.55 m dense plan.  The fourth token
costs nothing there: it is never started on those manifests (the
start-factor guard), as the on-edge plan is not in v58.

## 6. Verdict

- **Where the priority boxes went**: the v58 dense plan stands the
  priority 0.55 x 0.40 boxes last in a standing layer the normal boxes
  of their class fill first, so they are left out (x80-s0003: 0 of 4 in
  an 11-box layer), and its fill pass stands a normal box in the one
  slot a priority box could take uncovered.  The 0.75 x 0.56 priority
  boxes have no pose in any dense plan.
- **The strip costs the count where there is none to spare.**  A front
  row of the standing layer reserved for two priority boxes, with the
  flat soft boxes laid first behind it, is worth +2 to +5 on c1x50-c1x70
  on the plan alone but costs two items a plan, and on c1x80 (threshold
  41, the plans 41-44) that loses 7 of 10 crossings (-14).  So the strip
  is not a setting: it is a fourth count-secured token, and the re-plan's
  rank (a plan over the gate first, then the plan score) takes it on 16
  of 48 dense scenes and on c1x80 only where it still holds the count.
- **The priority-first fill is free** (+2.25 on the plan alone, no
  crossing lost) and is on for every dense plan.
- **The physics takes it**: every plan pose replayed, no topple, the
  strip's boxes on edge at 0.54-0.94 m in the front row with the priority
  soft over them.
- **The verdict (`bench.platform_score`, 30 s budget, against v58):**
  dense-a **+3.40 [+2.46, +4.41]**, the same 47 of 48 counted, 40 scenes
  up and 3 down, placement +28.0 (priority placed 2.1 -> 4.0 a scene)
  against fill -0.9 and soft -3.6; core-a +0.19 [+0.00, +0.56] (one
  scene, +9.0); hard-a -0.18 [-0.49, +0.08] (no crossing moved, the
  changes the budget's and the strip's -4.6 on one scene).  Ship
  candidate: `arm_adenser_a.txt` (the v58 form plus
  `plan_count_secure_dense_priority_fill=true` and the strip token
  `dense@plan_standing_rows_max_height=0.4&plan_count_secure_dense_priority_rows=1&plan_count_secure_dense_soft_thin=0.25`
  appended to `plan_count_secure_blocks`).  On the platform's terms the
  four dense A episodes are worth about +3.4 x 4 / 23 = +0.6 of the
  total, less if the slower machine skips the fourth plan.
- **What is left**: the 0.75 x 0.56 x 0.27 priority boxes (5 of 13 on
  x80-s0003), which stand 0.56 m tall on their side and fit nowhere in
  the dense plan's layers; a flat slot for them in the first hard layer,
  with the stack above kept off them, is the next lever (one such box
  is worth about 1.5 points on a counted dense episode).  And the
  strip's pick on a-hard-s0023, which loses a priority box in the
  replay: the rank reads the plan, not the replay.
