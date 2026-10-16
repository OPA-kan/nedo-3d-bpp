# Count-secured planning for Task A

Built against the findings section "Why Task A episodes fall under the
count" and `stability-lattice.md` sections 6-7. On dense manifests (one
container, 50-110 items, the manifest 0.7-1.1 of the container) the row
planner places the hard cargo smallest first, then the priority cargo,
then the soft cargo, and stops at 25-30 items whatever the threshold asks.
This adds a re-plan for manifests whose plan does not hold the count,
behind config flags, and measures it on the analytic planner, on local
physics and on the physics bench (CI).

Scripts and the analytic and local physics outputs are in
`reports/wedge/a-count-secure/`; the physics records in
`reports/bench/acount-*` (re-plan under the threshold plus 2) and
`reports/bench/acount0-*` (re-plan under the threshold). Baselines:
`reports/bench/ship-core-a`, `ship-hard-a`, `ship-dense-a` (the shipped A
arm, `reports/bench/arms/arm_ship_a.txt`).

## Summary

1. **What was built** (all off by default; with `plan_count_secure` unset
   the planner and the race are the shipped code path, and the tests pass
   unchanged: 203 in `tests.test_rule_alpha tests.test_agent
   tests.test_bench`, plus 14 new ones in `tests/test_count_secure.py`).
   The code is in its own module, `rule_alpha/count_secure.py`, with a
   five-line hook at the end of `planner.plan_packing` and one helper
   (`_count_secure_race`) plus a three-line change in the race in
   `rule_alpha/agent.py`'s `optimize`.
   - `plan_count_secure`: when the planner's best plan holds fewer than the
     trigger (the count threshold `total // 2 + 1` plus
     `plan_count_secure_margin`), the manifest is planned again, one plan
     per token of `plan_count_secure_blocks`, while the budget allows one
     more plan as long as the longest so far. The plans are ranked first by
     whether they hold the threshold plus `plan_value_margin`, then by the
     plan score; under the threshold by the count. The ordinary plan stands
     whenever it holds the trigger.
   - `plan_count_secure_blocks` ("plain"): `plain` is the row planner
     itself under the count-secured overrides; `left` / `right` / `back`
     are the count-frame plans with the frame's soft cargo as a block on a
     floor strip; `top` is the count frame without a block. A token may
     carry fields of its own (`plain@field=value&field=value`).
   - `plan_count_secure_standing_rows` (on): the count-secured plans run
     with `plan_standing_rows` and `plan_soft_own_rows`.
     `plan_count_secure_overrides`: further fields, "f=v;f=v".
   - `plan_count_secure_margin` (-1: `plan_value_margin`): the trigger.
     0 re-plans only plans under the threshold itself.
   - `plan_count_secure_choice`: the race of the planner's plan against the
     ladder's dry-run plan is decided first by which holds the threshold
     plus `plan_value_margin`. `plan_count_secure_race_replanned`: only in
     episodes where the re-plan ran.
   - `plan_count_secure_block_layers` (2), `plan_count_secure_block_share`
     (0.6), `plan_count_secure_block_rows` (on: the block as rows inside
     the strip; off: a greedy lowest / deepest / wall-side packer),
     `plan_count_secure_extra` (0): the count frame's knobs.
2. **The soft block does not pay.** Every frame plan holds fewer items
   than the plain re-plan on every dense manifest (15-30 against 26-34;
   section 2), and the best block (the left strip) about as many as the
   ordinary plan (266 against 265 over ten scenes). Soft cargo carries soft cargo only to the 0.7 m cap and
   only once soft boxes cover 35 % of the floor, and a top in the
   mid-height transport band (0.70-0.80 m) is not carried in, so a soft
   block is two layers of 0.23-0.25 m: about 11 items a square metre. A
   column of the smallest hard boxes holds two flat layers, a standing
   layer and a soft box on top: 18-27 a square metre. The count frame's
   premise (the soft boxes are the smallest items, so the count is theirs)
   holds by volume and fails by floor area.
3. **What pays is the standing rows, gated to the count.** `plan_standing_rows`
   was measured on the sample suite in the v19 era and not adopted: it
   trades soft and priority cargo for count. Gated to plans under the
   threshold it buys the count where nothing else counts.
4. **CI, the re-plan under the threshold (`acount0-*`)**: dense-a 10 -> 20
   crossings of 48, hard-a 26 -> 29, core-a 48 -> 48 with the soft and
   priority counts and covers identical (one episode changed, a-c1-s0012,
   whose plan of 19 was under the threshold: 21 -> 26 placed). Topples
   dense 8 -> 5, hard 19 -> 17, core 4 -> 4. No crossing lost in any
   suite.
5. **CI, the re-plan under the threshold plus 2 (`acount-*`)**: dense-a 21,
   hard-a 31, but core-a 47 (a-c1s-s0006 24 -> 19 against 21: its plan
   of 22 and the re-plan's of 22 were under the threshold plus 2, the
   dry-run's was over it, the race took the dry-run, and that replayed to
   19 items with no soft and no priority box), soft 381 -> 369, priority
   255 -> 246, the centre of mass +0.015, topples 4 -> 8. The band between
   the threshold and the margin is where core-a's plans sit (9 of 48), and
   those replay to crossings already: the re-plan there buys fill and pays
   in height, and the race's count rule hands some of them to the dry-run.
6. **Verdict**: the form to ship is `plan_count_secure=true,
   plan_count_secure_choice=true, plan_count_secure_race_replanned=true,
   plan_count_secure_margin=0, plan_count_secure_blocks=plain;top`
   (`reports/bench/arms/arm_acount0_a.txt`). It holds core-a exactly and
   doubles the dense-a crossings. Its platform value depends on what the
   uncounted A episodes are: c1x50 and c1x60 manifests cross (8 -> 10,
   2 -> 8 of 12), c1x70 barely (0 -> 2) and c1x80 not at all (the plan
   reaches 32-36 items against 41). If the platform's uncounted A
   episodes are single containers of 80-110 items, as the v40 note read
   from the optimize time, this lever does not reach them; if they are
   50-70, about half of them cross, about +2.3 points each.

## 1. The dense manifests

`frame_share.py` (the c1 container, 12 seeds a count):

| items | manifest / container | smallest threshold items / container | soft share of them |
|---:|---:|---:|---:|
| 50 | 0.68 | 0.28 | 0.48 |
| 60 | 0.81 | 0.33 | 0.50 |
| 70 | 0.96 | 0.38 | 0.48 |
| 80 | 1.09 | 0.43 | 0.48 |

c1x60 seed 2, the ordinary plan (`base_dbg.py`): six 0.65 x 0.45 boxes a
layer, two flat layers to 0.54 m, a standing layer of 0.55 x 0.40 x 0.24
boxes on their sides to 0.94 m (a flat third layer's top would land in the
transport band), and six soft boxes on top: 27 items, the hard cargo under
the soft headroom cap (1.12 m) and the soft cargo one layer over it.

## 2. The frame plans

The count frame is the threshold plus `plan_value_margin` smallest items,
every priority item included (c1x60 seed 2: 33 items, 18 of them soft:
four 0.45 x 0.30 x 0.20, eight 0.60 x 0.30 x 0.25, six 0.65 x 0.35 x
0.23; fifteen 0.55 x 0.40 x 0.24 hard, three of them priority; and the
two priority boxes of 73 L and 113 L). Its plan:

1. the frame's soft cargo, normal before priority, as a block on a strip
   (`block_regions`: the soft footprint over two layers, no less than the
   floor share soft-on-soft waits for, the width snapped to a sum of the
   soft boxes' sides, at most 0.6 of the floor's width or depth), packed
   by the planner's own rows inside the strip (`_RegionBoard` narrows the
   container's floor rectangle for `pack_rows`; the validator does not
   read it), flat poses only;
2. the frame's normal hard cargo in rows on the rest of the floor, then
   the frame's priority hard cargo on those rows' lines (nothing but
   priority cargo may rest on priority cargo; in a priority container the
   priority cargo goes first, deep-first, as the row planner does);
3. the rest: the bigger hard cargo on the frame's rows, the rest of the
   soft cargo on its own rows over the whole floor, the priority
   container's spare rows, the planner's pose search; the frame's steps
   renumbered to come first in the replay order.

What c1x60 seed 2 gets (`frame_dbg.py`): the left strip is 0.88 m of the
1.47 m floor; the block holds four 0.35 x 0.65 boxes on the floor (0.91
m^2, over the 35 % share), three on them, then nothing (the third layer's
tops are in the transport band, the 0.60 x 0.30 boxes do not rest on 80 %
of a 0.35 x 0.65 column pair); the hard strip takes three boxes a layer,
four layers under the headroom cap; 19 of the 33 frame items, 25 in all.
The first version (priority mixed by size into the frame's rows) put a
73 L priority box on the floor at the back and a 113 L one on the third
layer, and the frame's soft cargo found no top it could cover: 16 in all.

Analytic, planner only, ten dense scenes (`sweep.py`, `tab.py`;
`sw1`-`sw4.jsonl`), planned items:

| plan | c1x50 s1 / s2 | c1x60 s1-s4 | c1x70 s1 / s2 | c1x80 s1 / s2 | total | >= threshold |
|---|---|---|---|---|---:|---:|
| ordinary (shipped) | 27 / 23 | 27 / 27 / 25 / 30 | 27 / 26 | 27 / 26 | 265 | 1 |
| frame, block left | 26 / 24 | 26 / 27 / 25 / 26 | 27 / 28 | 27 / 30 | 266 | 1 |
| frame, block right | 25 / 23 | 23 / 21 / 21 / 25 | 22 / 24 | 21 / 24 | 229 | 0 |
| frame, block back | 26 / 23 | 25 / 25 / 26 / 24 | 25 / 26 | 25 / 26 | 251 | 1 |
| frame, top (no block) | 16 / 17 | 22 / 22 / 15 / 17 | 20 / 19 | 27 / 21 | 196 | 0 |
| plain (standing rows, soft own rows) | 29 / 26 | 29 / 33 / 33 / 32 | 29 / 34 | 29 / 34 | 308 | 5 |
| plain + soft smallest first | 29 / 26 | 29 / 34 / 33 / 32 | 29 / 34 | 29 / 34 | 309 | 5 |
| plain + headroom reserve off | 29 / 28 | 27 / 31 / 32 / 30 | 28 / 31 | 28 / 31 | 295 | 4 |
| plain, standing poses up to 0.45 m | 26 / 29 | 25 / 29 / 31 / 32 | 25 / 28 | 25 / 28 | 278 | 4 |
| ordinary + headroom reserve off | 29 / 25 | 28 / 27 / 29 / 29 | 29 / 27 | 29 / 26 | 278 | 1 |

(The frame rows are the measured form with standing rows on, `sw3`; the
first frame forms, `sw1`-`sw2`, were lower.) On the hard-a misses (16
scenes, `sw5`, `sw6`) the plain re-plan adds 21 planned items (+8 on
s0019, +10 on s0048) and the frame `top` plan beats it on four scenes by
2-6 items (s0015, s0032, s0037, s0039), none of them to the threshold; so
the CI arm carries `plain;top`.

On core-a (`swcore.jsonl`, c1 / c1s / c2p) 11 of 36 plans are under the
threshold plus 2, and the plain re-plan wins 9 of them (a-c1-s0007 22 ->
32 planned, s0009 21 -> 30, a-c2p-s0003 43 -> 52).

## 3. Local physics

`phys.py`, the shipped A arm with `offline_budget_seconds` 30 (dense) or
60 (core-a), four processes at once (`ph1*.jsonl`, `ph2*.jsonl`):

| scenes | arm | crossings | placed | fill | soft placed / covered | priority | topples | CoM |
|---|---|---:|---:|---:|---|---:|---:|---:|
| 6 dense | shipped | 1 | 27.3 | 39.7 | 39 / 0 | 25 | 0 | 0.329 |
| 6 dense | re-plan (threshold + 2) | 3 | 30.7 | 44.6 | 38 / 0 | 28 | 0 | 0.351 |
| 4 core-a (plans under threshold + 2) | shipped | 4 | 21.5 | 35.4 | 15 / 0 | 13 | 0 | 0.309 |
| 4 core-a | re-plan (threshold + 2) | 4 | 26.0 | 41.9 | 20 / 0 | 12 | 0 | 0.370 |

c1x60 s0002 27 -> 33, s0003 30 -> 33, c1x80 s0002 25 -> 34; on c1x60
s0004 and c1x70 s0002 the re-plan was cut by the 30 s budget under the
load of four processes (it starts only when 1.2 times the longest plan so
far fits). On core-a the episodes already cross; the re-plan adds 4.5
items and 6.5 fill points and raises the centre of mass by 0.06 (the
standing layer), which the continuous reading prices at about -3 a
changed episode against +0.6 for the fill. That is why the trigger at the
threshold itself was run on CI as a second arm.

## 4. CI (physics, budget 4.5 s, 6 shards; offline budget 140 s)

| suite | arm | crossings | placed | fill | soft placed / covered | priority placed / covered | topples | CoM | policy max |
|---|---|---:|---:|---:|---|---|---:|---:|---:|
| dense-a | shipped | 10 | 28.10 | 41.5 | 296 / 37 | 188 / 23 | 8 | 0.348 | 5.02 |
| dense-a | re-plan < thr + 2 | **21** | 31.04 | 45.4 | 297 / 10 | 220 / 19 | 3 | 0.363 | 3.97 |
| dense-a | re-plan < thr | **20** | 30.65 | 44.9 | 292 / 10 | 214 / 19 | 5 | 0.363 | 4.17 |
| hard-a | shipped | 26 | 46.83 | 35.4 | 389 / 7 | 386 / 13 | 19 | 0.350 | 5.30 |
| hard-a | re-plan < thr + 2 | **31** | 48.77 | 35.5 | 497 / 14 | 394 / 13 | 20 | 0.349 | 5.32 |
| hard-a | re-plan < thr | **29** | 48.02 | 34.8 | 500 / 12 | 395 / 12 | 17 | 0.343 | 5.37 |
| core-a | shipped | 48 | 37.54 | 36.2 | 381 / 0 | 255 / 1 | 4 | 0.326 | 3.64 |
| core-a | re-plan < thr + 2 | **47** | 38.12 | 37.5 | 369 / 0 | 246 / 1 | 8 | 0.341 | 3.78 |
| core-a | re-plan < thr | 48 | 37.65 | 36.4 | 381 / 0 | 255 / 1 | 4 | 0.328 | 3.63 |

Every episode ended on a decline in all six runs except hard-a's one
settle and one transport ending, which the baseline has too.

dense-a by count (crossings of 12; shipped -> re-plan < thr):

| items (threshold) | crossings | placed |
|---|---|---|
| 50 (26) | 8 -> 10 | 25.8 -> 26.9 |
| 60 (31) | 2 -> 8 | 28.7 -> 31.3 |
| 70 (36) | 0 -> 2 | 28.7 -> 31.8 |
| 80 (41) | 0 -> 0 | 29.3 -> 32.6 |

No dense-a episode places fewer items in either arm (33 and 36 up, 0
down). The crossings won under the threshold trigger: c1x50 s0002, s0009;
c1x60 s0002, s0003, s0004, s0005, s0006, s0008; c1x70 s0002, s0005.

hard-a, re-plan < thr: in s0021 (59 -> 70, threshold 70), s0038 (36 ->
38, 37), s0047 (41 -> 55, 49); none out; s0028 62 -> 51 (threshold 50:
the planner's plan was under the threshold, the re-plan's too, the
dry-run's held the threshold plus 2 and the race took it). The trigger at
the threshold plus 2 adds s0017 (83 -> 86, 86) and s0029 (9 -> 17, 16):
both had plans between the threshold and the margin.

core-a, re-plan < thr + 2: a-c1s-s0006 26 -> 21 (the threshold 21 still
held), a-c2p-s0002, s0008, s0011 -3 each, a-c1-s0007 +11, a-c2p-s0003 +9,
a-c1-s0009 +8; one crossing lost (judge: 48 -> 47), soft -12 and priority
-9 over the suite, the centre of mass +0.015 and topples 4 -> 8. Priced
(the refit's continuous reading, a suite's third of the total): fill
+0.12, soft -0.04, priority -0.18, cog -0.84, -0.93. Re-plan < thr: fill
+0.01, cog -0.10, the rest 0 (a-c1-s0012 alone).

The continuous reading on dense-a is negative for both arms (cog -0.85
against fill +0.33 and priority +0.28): the plain re-plan's loads stand
0.015 higher. It counts every episode, and on the platform the dense
episodes under the count score zero on cog whatever their height; the
crossing itself is the price (+2.3 points a platform episode), which the
continuous reading does not carry.

Optimize time: the re-plan adds a plan (two with `top`) to the 140 s
budget; the slowest optimize on dense-a went 66 -> 89 s, hard-a stays at
the 140 s budget (its biggest manifests plan longer than the budget leaves
for a re-plan, which is then not started). On a machine five times
slower the plain plan starts only when 1.2 times the longest plan so far
fits in what is left.

## 5. Verdict

- Ship candidate: `arm_acount0_a.txt`'s five fields on Task A
  (`plan_count_secure=true, plan_count_secure_choice=true,
  plan_count_secure_race_replanned=true, plan_count_secure_margin=0,
  plan_count_secure_blocks=plain;top`). core-a is held exactly (48 of 48,
  soft 381 / 0 and priority 255 / 1 unchanged, one already-crossing
  episode +5 items); dense-a 10 -> 20 crossings, hard-a 26 -> 29, no
  crossing lost, fewer topples in both.
- Not adopted: the trigger at the threshold plus 2 (core-a loses a
  crossing, 12 soft and 9 priority boxes, and gains 0.015 of height), and
  the soft block (every frame plan holds fewer items than the plain
  re-plan; the block is kept in the code, off unless named in
  `plan_count_secure_blocks`).
- The open question is the platform's manifests. If its uncounted A
  episodes are like c1x50-c1x70, about half of them cross; if they are
  single containers of 80-110 items, none does: no plan here reaches 41
  items in the c1 container (the best, 36, is 0.43 of the container at
  the smallest items), and the count there would need a different
  container picture, not a different plan.
- Not done: the per-episode A quality on the platform (the bench reads
  cog, placement and soft only through the continuous proxy), and a
  submission build; `submission/agent.py` is unchanged.

## 6. After v51: the race fix, the re-plan's timing, and the short-budget bench

v51 shipped the threshold-only form and scored 53.50 against v50's 56.04:
stability 18 lattice steps against 19 (one counted Task A episode lost,
none gained), cog -3.61, placement -1.95, soft -3.50, the optimize time
118.9 -> 138.8 s against the 140 s budget. The platform's A manifests are
the dense kind, so the re-plan ran on most of them.

**What changed** (commit bd2c6ee9; the v51 flags keep their meaning):

- `plan_count_secure_race_chosen`: the count rule decides the planner /
  dry-run race only where a re-plan completed and was chosen
  (`count_secure_log["chosen"] != "base"`); it prefers the planner's plan
  when that holds the threshold plus `plan_value_margin` and the dry-run's
  does not, and it hands the episode to the dry-run's plan only when the
  planner's plan is under the threshold itself. v51's rule
  (`plan_count_secure_race_replanned`) applied wherever the base plan was
  under the trigger, whether or not a re-plan finished, and a dry-run plan
  over the gate then replaced a planner plan that replays to the count
  (a-c1s-s0006 24 -> 19 and a-hard-s0028 62 -> 51 on the bench).
- `plan_count_secure_early`: the re-plan runs right after the planner's
  first complete plan, before its other variants and layouts. The shipped
  arm plans one base variant, so on it this is the same as v51's order
  (tested); it matters for arms with several variants.
- `plan_count_secure_start_factor` (1.2): a re-plan starts only when this
  many times the longest plan so far fits in what is left of the budget.
  The record says when one was skipped.
- The fixed form plans `plain` only. v51 also planned `top`, which doubled
  the re-plan's time (7.7 + 8.1 s a dense episode on the bench, about
  20-25 s each on the platform's machine), and `top` was chosen on
  a-c1x70-s0012 and a-c1x80-s0012 with **no priority box** (6 -> 0
  placed): under the threshold the re-plan ranks by count alone, and the
  count frame's plan holds the count without the priority cargo.
- `metrics.count_secure` in every episode record (`bench/episode.py`): the
  re-plan's variants (planned, soft, priority, seconds, skipped / cut), its
  pick, and the race (the count rule's decision, the plan the score alone
  would take, the planner's and the dry-run's plan sizes).
  `race_stats.py` and `scene_diff.py` read it.

Fixed form: `reports/bench/arms/arm_acountfix_a.txt` (`plan_count_secure,
plan_count_secure_choice, plan_count_secure_race_chosen,
plan_count_secure_margin=0, plan_count_secure_early,
plan_count_secure_blocks=plain`).

**The short-budget bench.** The bench's mean optimize time is 38 s on
dense-a and 49 s on core-a at the full budget against the platform's 119
s, so the platform plans about 2.5-3 times slower; 140 s there is about
40-60 s here. The three forms at 40 and 60 s, and the fixed form at the
full budget (records `reports/bench/acb40*`, `acb60*`, `acountfix-*`;
`budget_stats.txt`):

| suite | arm | budget | crossings | placed | soft placed / covered | priority placed / covered | topples | CoM | optimize mean |
|---|---|---:|---:|---:|---|---|---:|---:|---:|
| dense-a | shipped | 40 | 10 | 28.10 | 296 / 37 | 188 / 23 | 8 | 0.348 | 28.2 |
| dense-a | v51 | 40 | 20 | 30.65 | 292 / 10 | 214 / 19 | 5 | 0.363 | 38.4 |
| dense-a | fixed | 40 | 20 | 30.69 | 290 / 9 | 226 / 24 | 5 | 0.363 | 33.5 |
| dense-a | shipped | 60 | 10 | 28.10 | 296 / 37 | 188 / 23 | 8 | 0.348 | 27.5 |
| dense-a | v51 | 60 | 20 | 30.65 | 292 / 10 | 214 / 19 | 5 | 0.363 | 45.7 |
| dense-a | fixed | 60 | 20 | 30.69 | 290 / 9 | 226 / 24 | 5 | 0.363 | 44.4 |
| dense-a | shipped | 140 | 10 | 28.10 | 296 / 37 | 188 / 23 | 8 | 0.348 | 38.0 |
| dense-a | v51 | 140 | 20 | 30.65 | 292 / 10 | 214 / 19 | 5 | 0.363 | 45.3 |
| dense-a | fixed | 140 | 20 | 30.69 | 290 / 9 | 226 / 24 | 5 | 0.363 | 33.0 |
| core-a | shipped | 40 | 48 | 37.44 | 392 / 0 | 262 / 1 | 3 | 0.323 | 31.3 |
| core-a | v51 | 40 | 48 | 37.46 | 392 / 0 | 262 / 1 | 3 | 0.324 | 30.2 |
| core-a | fixed | 40 | 48 | 37.46 | 392 / 0 | 262 / 1 | 3 | 0.324 | 31.2 |
| core-a | shipped | 60 | 48 | 37.52 | 392 / 0 | 262 / 1 | 4 | 0.324 | 38.5 |
| core-a | v51 | 60 | 48 | 37.46 | 392 / 0 | 262 / 1 | 3 | 0.324 | 41.7 |
| core-a | fixed | 60 | 48 | 37.58 | 381 / 0 | 255 / 1 | 3 | 0.327 | 35.8 |
| core-a | shipped | 140 | 48 | 37.54 | 381 / 0 | 255 / 1 | 4 | 0.326 | 49.4 |
| core-a | v51 | 140 | 48 | 37.65 | 381 / 0 | 255 / 1 | 4 | 0.328 | 52.9 |
| core-a | fixed | 140 | 48 | 37.46 | 370 / 0 | 255 / 1 | 8 | 0.329 | 50.7 |

What the records say (`metrics.count_secure`):

- **The re-plan was never skipped or cut** at any budget: dense-a 44 of 48
  episodes re-planned, 43 picked the re-plan; core-a 2 re-planned and
  picked (a-c1-s0012 21 -> 26 placed, a-c1s-s0010 unchanged at 22). The
  plain re-plan takes 5.7-6.2 s (at most 10.1 s) here.
- **The race's count rule never overrode the score**, in either form at
  any budget: on dense-a it decided 7 episodes, every one for the
  planner's plan, which the score also picked; on core-a it decided none.
  So the bench does not reproduce the mechanism suspected for v51's lost
  episode; the fix removes it where it could act.
- **The core-a differences that are not a-c1-s0012 are the shipped race's
  own variance.** a-c2p-s0002, a-c2p-s0008, a-c2p-s0011 and a-c2-s0011
  change between runs of arms that make the same decisions there (base
  plan kept, no count rule): the ladder's dry-run plan differs from run to
  run, and when it wins on the score it can carry no soft and no priority
  cargo (a-c2-s0011: the dry-run's 58-item plan against the planner's 47
  won in the shipped form at 140 s and the fixed form at 60 s, 51 placed
  with 0 soft and 0 priority, and lost in the other runs, 50 placed with
  11 and 7; a-c2p-s0008 at the full budget,
  soft 11 -> 3). The fixed form's core-a soft count at 140 s (370 against
  381) is that variance (a-c2p-s0008 -8, a-c2p-s0011 -3), not the re-plan.
- dense-a is identical between v51 and the fixed form except the two
  `top` picks (c1x70-s0012 32 -> 33 and c1x80-s0012 33 -> 34 placed, 0 ->
  6 priority each); the fixed form also spends less optimize time.

**Reading.** At the platform-like budgets the bench shows neither the
lost episode nor the soft loss: v51 and the fixed form hold core-a at the
shipped form's numbers and double dense-a's crossings. The platform loss
then comes from what the bench does not model. The candidates are:

1. the `top` pick dropping the priority cargo (seen here, 2 of 48 dense
   episodes; placement -1.95 on the platform);
2. the re-plan's time taking the dry-run's budget on the slower machine
   and changing which plan wins on the episodes the dry-run used to win;
3. the shipped race's own variance: a counted episode's dry-run plan
   winning on the score with little soft cargo, as a-c2-s0011 and
   a-c2p-s0008 do here between identical arms.

The fixed form removes (1), halves the time behind (2), and restricts
the count rule. Nothing here guards against (3). A guard would keep the
planner's plan when the dry-run's carries markedly fewer soft and
priority boxes; `plan_prefer_planner`, already in the code, is one.

## 7. The dry-run's time: the planner alone, the dry-run alone, and the dry-run first, at the platform's budget

v51 and v52 lost a counted Task A episode on the platform, and the diagnostic
submissions said why: on the official sample the row planner alone reaches
exactly the count threshold (21 of 41, fill 20.1) and the ladder's dry-run
alone places 25 (fill 32.1, v50's shipped result); the re-plan's time took
the dry-run's. The platform's machine is 2.4-5 times slower than the bench,
so the bench's 140 s never starves the dry-run (section 6). This study runs
the offline phase at 20 and 30 s here, where it does, and prices every form
with `bench.platform_score` against the shipped form **at the same budget**.
Every episode record now carries `metrics.optimize` (the planner's and the
dry-run's seconds and plan sizes, whether the deadline cut the dry-run,
`dry_first`, the plan played), written by `bench/episode.py`.

Forms (`reports/bench/arms/`): the shipped race (`arm_ship_a`: the planner,
then the dry-run with what is left, the plan score picks); the dry-run alone
(`arm_adry_a`, `offline_planner=` empty); the planner alone (`arm_aplan_a`,
`offline_dry_run=false`); the dry-run first on every layout (`arm_adfirst_a`,
`plan_dry_run_first`: the planner only with `plan_min_seconds` = 15 s left);
the dry-run first on dense manifests only (`arm_adfirstd_a`,
`plan_dry_run_first_dense=0.62`, the manifest's volume at least 0.62 of the
containers'); and on the manifests under that share only (`arm_adfirsts_a`,
`-0.62`). The short budgets append `offline_budget_seconds=20` / `30` to the
arm; the records are `reports/bench/<form><budget>-<suite>` (`ship20-dense-a`,
`aplan30-hard-a`, ...) and `<form>-<suite>` at 140 s. core-a ran at 30 and
140 s only. Physics, policy budget 4.5 s, 6 shards, 48 episodes a suite. The
`ship*` records are fresh runs of the shipped form at each budget; the 140 s
bases are `ship-dense-a`, `ship-hard-a`, `ship-core-a`.

The dry-run reserve (`plan_dry_run_reserve`) is in the code and was not run:
the records below show the planner never needs reserving from.

### The tables

Columns: the platform-like score and its paired delta with the bootstrap
interval; counted episodes; episodes up / down against the base; the five
components' deltas; placed; the races won by the planner's / the dry-run's
plan; the planner's and the dry-run's mean seconds and mean plan size; the
episodes whose dry-run the deadline cut; the mean optimize time. The 140 s
`adry` / `aplan` records predate `metrics.optimize`.

**dense-a, offline budget 20 s** (base `ship20-dense-a`: score 23.31, counted 11 of 48, placed 28.17, fill 41.4, cog 18.0, stability 22.0, placement 11.9, soft 8.2)

| form | record | score | delta [95 % CI] | counted | up / down | fill | cog | stab. | place. | soft | placed | races planner / dry-run | planner s, plan | dry-run s, plan | dry-run cut | optimize s |
|---|---|---:|---|---:|---|---:|---:|---:|---:|---:|---:|---|---|---|---:|---:|
| shipped (planner, then the dry-run; the race) | `ship20-dense-a` | 23.31 | base | 11 | - | 41.4 | 18.0 | 22.0 | 11.9 | 8.2 | 28.17 | 46 / 2 | 5.6 s, 24.9 | 13.8 s, 21.4 | 41 | 19.4 |
| dry-run alone | `adry20-dense-a` | 12.77 | -10.54 [-16.83, -5.15] | 1 (-10) | 16 / 30 | +0.5 | -16.7 | -20.0 | -11.9 | -8.2 | -7.15 | 0 / 48 | - | 19.4 s, 21.4 | 44 | 19.4 |
| planner alone | `aplan20-dense-a` | 23.53 | +0.22 [-0.18, +0.84] | 11 (+0) | 1 / 1 | -0.4 | +0.4 | +0.0 | +1.0 | +0.7 | -0.02 | 48 / 0 | 5.9 s, 24.9 | - | 0 | 5.9 |
| dry-run first, every layout | `adfirst20-dense-a` | 12.78 | -10.53 [-16.82, -5.13] | 1 (-10) | 16 / 30 | +0.6 | -16.7 | -20.0 | -11.9 | -8.2 | -7.02 | 0 / 48 | - | 19.3 s, 21.6 | 42 | 19.3 |
| dry-run first, dense manifests (share >= 0.62) | `adfirstd20-dense-a` | 12.75 | -10.56 [-16.84, -5.17] | 1 (-10) | 16 / 31 | +0.5 | -16.7 | -20.0 | -11.9 | -8.2 | -7.12 | 0 / 48 | 6.2 s, 25.0 | 18.8 s, 21.5 | 42 | 19.0 |
| dry-run first, manifests under the share | `adfirsts20-dense-a` | 22.27 | -1.05 [-3.14, +0.00] | 10 (-1) | 0 / 1 | +0.0 | -1.7 | -2.0 | -1.0 | -0.7 | -0.06 | 45 / 3 | 5.1 s, 24.9 | 13.9 s, 21.7 | 34 | 18.8 |

**dense-a, offline budget 30 s** (base `ship30-dense-a`: score 22.27, counted 10 of 48, placed 28.10, fill 41.5, cog 16.3, stability 20.0, placement 10.9, soft 7.4)

| form | record | score | delta [95 % CI] | counted | up / down | fill | cog | stab. | place. | soft | placed | races planner / dry-run | planner s, plan | dry-run s, plan | dry-run cut | optimize s |
|---|---|---:|---|---:|---|---:|---:|---:|---:|---:|---:|---|---|---|---:|---:|
| shipped (planner, then the dry-run; the race) | `ship30-dense-a` | 22.27 | base | 10 | - | 41.5 | 16.3 | 20.0 | 10.9 | 7.4 | 28.10 | 45 / 3 | 4.8 s, 24.9 | 21.0 s, 22.3 | 19 | 25.8 |
| dry-run alone | `adry30-dense-a` | 12.82 | -9.45 [-15.69, -4.13] | 1 (-9) | 16 / 29 | +0.6 | -14.9 | -17.9 | -10.9 | -7.4 | -6.48 | 0 / 48 | - | 21.6 s, 22.5 | 13 | 21.6 |
| planner alone | `aplan30-dense-a` | 23.53 | +1.26 [-0.12, +3.63] | 11 (+1) | 2 / 1 | -0.4 | +2.1 | +2.0 | +2.1 | +1.4 | +0.04 | 48 / 0 | 5.2 s, 24.9 | - | 0 | 5.2 |
| dry-run first, every layout | `adfirst30-dense-a` | 15.92 | -6.35 [-11.78, -1.94] | 4 (-6) | 16 / 26 | +0.5 | -10.0 | -12.0 | -7.1 | -5.5 | -6.35 | 3 / 45 | 3.4 s, 25.8 | 23.5 s, 22.4 | 17 | 23.8 |
| dry-run first, dense manifests (share >= 0.62) | `adfirstd30-dense-a` | 12.81 | -9.45 [-15.69, -4.14] | 1 (-9) | 16 / 29 | +0.6 | -14.9 | -17.9 | -10.9 | -7.4 | -6.54 | 0 / 48 | 3.3 s, 25.0 | 25.9 s, 22.3 | 21 | 25.9 |
| dry-run first, manifests under the share | `adfirsts30-dense-a` | 23.25 | +0.98 [-0.18, +3.14] | 11 (+1) | 1 / 1 | -0.2 | +1.7 | +2.0 | +1.0 | +0.7 | +0.08 | 47 / 1 | 5.9 s, 24.9 | 21.4 s, 21.9 | 33 | 27.2 |

**dense-a, offline budget 140 s** (base `ship-dense-a`: score 22.27, counted 10 of 48, placed 28.10, fill 41.5, cog 16.3, stability 20.0, placement 10.9, soft 7.4)

| form | record | score | delta [95 % CI] | counted | up / down | fill | cog | stab. | place. | soft | placed | races planner / dry-run | planner s, plan | dry-run s, plan | dry-run cut | optimize s |
|---|---|---:|---|---:|---|---:|---:|---:|---:|---:|---:|---|---|---|---:|---:|
| shipped (planner, then the dry-run; the race) | `ship-dense-a` | 22.27 | base | 10 | - | 41.5 | 16.3 | 20.0 | 10.9 | 7.4 | 28.10 | 45 / 3 | - | - | - | - |
| dry-run alone | `adry-dense-a` | 12.81 | -9.46 [-15.70, -4.14] | 1 (-9) | 16 / 29 | +0.6 | -14.9 | -17.9 | -10.9 | -7.4 | -6.48 | 0 / 48 | - | - | - | - |
| planner alone | `aplan-dense-a` | 23.53 | +1.26 [-0.12, +3.63] | 11 (+1) | 2 / 1 | -0.4 | +2.1 | +2.0 | +2.1 | +1.4 | +0.04 | 48 / 0 | - | - | - | - |
| dry-run first, every layout | `adfirst-dense-a` | 22.27 | +0.00 [+0.00, +0.00] | 10 (+0) | 0 / 0 | +0.0 | +0.0 | +0.0 | +0.0 | +0.0 | +0.00 | 45 / 3 | 4.9 s, 24.9 | 24.6 s, 22.8 | 0 | 29.5 |
| dry-run first, dense manifests (share >= 0.62) | `adfirstd-dense-a` | 22.27 | +0.00 [+0.00, +0.00] | 10 (+0) | 0 / 0 | +0.0 | +0.0 | +0.0 | +0.0 | +0.0 | +0.00 | 45 / 3 | 6.4 s, 24.9 | 32.8 s, 22.8 | 0 | 39.2 |
| dry-run first, manifests under the share | `adfirsts-dense-a` | 22.27 | +0.00 [+0.00, +0.00] | 10 (+0) | 0 / 0 | +0.0 | +0.0 | +0.0 | +0.0 | +0.0 | +0.00 | 45 / 3 | 6.3 s, 24.9 | 32.5 s, 22.8 | 0 | 38.8 |

**hard-a, offline budget 20 s** (base `ship20-hard-a`: score 42.16, counted 28 of 48, placed 47.06, fill 33.8, cog 46.2, stability 55.8, placement 49.6, soft 25.1)

| form | record | score | delta [95 % CI] | counted | up / down | fill | cog | stab. | place. | soft | placed | races planner / dry-run | planner s, plan | dry-run s, plan | dry-run cut | optimize s |
|---|---|---:|---|---:|---|---:|---:|---:|---:|---:|---:|---|---|---|---:|---:|
| shipped (planner, then the dry-run; the race) | `ship20-hard-a` | 42.16 | base | 28 | - | 33.8 | 46.2 | 55.8 | 49.6 | 25.1 | 47.06 | 40 / 8 | 9.8 s, 45.8 | 8.8 s, 21.4 | 41 | 18.6 |
| dry-run alone | `adry20-hard-a` | 32.39 | -9.77 [-15.45, -4.39] | 21 (-7) | 14 / 26 | +4.8 | -14.6 | -13.7 | -17.9 | -17.9 | -9.06 | 0 / 48 | - | 17.9 s, 32.1 | 39 | 17.9 |
| planner alone | `aplan20-hard-a` | 39.68 | -2.48 [-6.27, +0.20] | 26 (-2) | 7 / 12 | -1.1 | -3.0 | -4.0 | -5.5 | +0.8 | -0.08 | 48 / 0 | 10.1 s, 45.6 | - | 0 | 10.1 |
| dry-run first, every layout | `adfirst20-hard-a` | 31.20 | -10.96 [-16.83, -5.49] | 20 (-8) | 15 / 28 | +4.6 | -15.9 | -15.7 | -20.0 | -18.6 | -9.17 | 1 / 47 | 4.2 s, 13.0 | 17.8 s, 30.5 | 40 | 17.9 |
| dry-run first, dense manifests (share >= 0.62) | `adfirstd20-hard-a` | 36.94 | -5.22 [-10.53, -0.87] | 23 (-5) | 15 / 13 | +3.6 | -9.0 | -10.1 | -10.1 | -5.1 | -7.06 | 18 / 30 | 8.9 s, 44.0 | 13.3 s, 25.4 | 39 | 17.7 |
| dry-run first, manifests under the share | `adfirsts20-hard-a` | 35.11 | -7.05 [-12.14, -2.72] | 24 (-4) | 5 / 24 | +1.0 | -9.1 | -8.2 | -11.8 | -13.6 | -1.73 | 24 / 24 | 10.5 s, 45.3 | 12.6 s, 26.7 | 41 | 18.3 |

**hard-a, offline budget 30 s** (base `ship30-hard-a`: score 39.93, counted 26 of 48, placed 47.19, fill 34.1, cog 42.5, stability 51.4, placement 46.5, soft 24.2)

| form | record | score | delta [95 % CI] | counted | up / down | fill | cog | stab. | place. | soft | placed | races planner / dry-run | planner s, plan | dry-run s, plan | dry-run cut | optimize s |
|---|---|---:|---|---:|---|---:|---:|---:|---:|---:|---:|---|---|---|---:|---:|
| shipped (planner, then the dry-run; the race) | `ship30-hard-a` | 39.93 | base | 26 | - | 34.1 | 42.5 | 51.4 | 46.5 | 24.2 | 47.19 | 38 / 10 | 10.6 s, 46.0 | 15.7 s, 28.7 | 35 | 26.0 |
| dry-run alone | `adry30-hard-a` | 31.27 | -8.66 [-15.35, -2.06] | 20 (-6) | 16 / 23 | +4.6 | -12.1 | -11.4 | -17.2 | -17.5 | -9.33 | 0 / 48 | - | 25.2 s, 34.8 | 34 | 25.2 |
| planner alone | `aplan30-hard-a` | 39.63 | -0.30 [-3.73, +3.30] | 26 (+0) | 8 / 10 | -1.7 | +1.1 | +0.6 | -2.6 | +1.3 | -1.02 | 48 / 0 | 12.8 s, 46.0 | - | 0 | 12.8 |
| dry-run first, every layout | `adfirst30-hard-a` | 35.40 | -4.53 [-9.30, +0.34] | 24 (-2) | 13 / 22 | +4.3 | -6.2 | -3.6 | -12.5 | -13.4 | -8.27 | 5 / 43 | 3.3 s, 16.5 | 25.4 s, 34.9 | 35 | 25.8 |
| dry-run first, dense manifests (share >= 0.62) | `adfirstd30-hard-a` | 36.86 | -3.07 [-8.51, +1.98] | 23 (-3) | 12 / 12 | +2.7 | -5.5 | -5.7 | -6.3 | -3.8 | -6.62 | 19 / 29 | 7.9 s, 41.1 | 21.0 s, 33.1 | 34 | 25.5 |
| dry-run first, manifests under the share | `adfirsts30-hard-a` | 37.57 | -2.36 [-5.87, +1.52] | 26 (+0) | 3 / 16 | +0.7 | -2.0 | +0.3 | -6.7 | -8.7 | -2.02 | 25 / 23 | 10.9 s, 42.6 | 19.9 s, 32.2 | 33 | 26.0 |

**hard-a, offline budget 140 s** (base `ship-hard-a`: score 39.57, counted 26 of 48, placed 46.83, fill 34.5, cog 41.9, stability 51.5, placement 45.5, soft 22.3)

| form | record | score | delta [95 % CI] | counted | up / down | fill | cog | stab. | place. | soft | placed | races planner / dry-run | planner s, plan | dry-run s, plan | dry-run cut | optimize s |
|---|---|---:|---|---:|---|---:|---:|---:|---:|---:|---:|---|---|---|---:|---:|
| shipped (planner, then the dry-run; the race) | `ship-hard-a` | 39.57 | base | 26 | - | 34.5 | 41.9 | 51.5 | 45.5 | 22.3 | 46.83 | 33 / 15 | - | - | - | - |
| dry-run alone | `adry-hard-a` | 32.21 | -7.36 [-13.65, -1.22] | 21 (-5) | 15 / 21 | +4.3 | -10.3 | -9.8 | -15.2 | -15.0 | -8.04 | 0 / 48 | - | - | - | - |
| planner alone | `aplan-hard-a` | 39.72 | +0.15 [-3.20, +3.61] | 26 (+0) | 12 / 10 | -1.7 | +1.3 | +0.2 | -1.1 | +3.2 | +0.23 | 48 / 0 | - | - | - | - |
| dry-run first, every layout | `adfirst-hard-a` | 38.07 | -1.51 [-4.11, +0.10] | 25 (-1) | 6 / 8 | +1.5 | -2.6 | -1.5 | -5.2 | -2.4 | -3.85 | 21 / 27 | 8.8 s, 36.1 | 70.2 s, 41.7 | 10 | 76.8 |
| dry-run first, dense manifests (share >= 0.62) | `adfirstd-hard-a` | 38.49 | -1.08 [-3.66, +0.45] | 25 (-1) | 7 / 7 | +1.6 | -2.1 | -2.2 | -3.6 | -0.8 | -2.38 | 26 / 22 | 9.4 s, 41.0 | 65.2 s, 41.9 | 10 | 73.2 |
| dry-run first, manifests under the share | `adfirsts-hard-a` | 40.60 | +1.02 [-0.38, +3.60] | 27 (+1) | 3 / 5 | -0.0 | +1.8 | +2.0 | +1.5 | -0.0 | -0.06 | 32 / 16 | 11.8 s, 44.7 | 67.8 s, 42.4 | 7 | 79.1 |

**core-a, offline budget 30 s** (base `ship30-core-a`: score 66.19, counted 48 of 48, placed 37.35, fill 35.6, cog 80.8, stability 96.8, placement 78.9, soft 47.4)

| form | record | score | delta [95 % CI] | counted | up / down | fill | cog | stab. | place. | soft | placed | races planner / dry-run | planner s, plan | dry-run s, plan | dry-run cut | optimize s |
|---|---|---:|---|---:|---|---:|---:|---:|---:|---:|---:|---|---|---|---:|---:|
| shipped (planner, then the dry-run; the race) | `ship30-core-a` | 66.19 | base | 48 | - | 35.6 | 80.8 | 96.8 | 78.9 | 47.4 | 37.35 | 44 / 4 | 9.0 s, 36.7 | 17.6 s, 30.6 | 26 | 26.6 |
| dry-run alone | `adry30-core-a` | 39.98 | -26.21 [-32.32, -20.13] | 33 (-15) | 0 / 44 | +4.1 | -33.4 | -31.3 | -57.3 | -37.6 | -3.48 | 0 / 48 | - | 20.9 s, 34.7 | 23 | 20.9 |
| planner alone | `aplan30-core-a` | 66.67 | +0.48 [+0.04, +1.14] | 48 (+0) | 5 / 0 | -0.9 | +1.2 | +0.0 | +0.8 | +2.4 | -0.21 | 48 / 0 | 7.8 s, 36.7 | - | 0 | 7.8 |
| dry-run first, every layout | `adfirst30-core-a` | 48.86 | -17.33 [-23.74, -11.34] | 38 (-10) | 0 / 28 | +2.0 | -21.4 | -21.2 | -38.1 | -23.6 | -3.25 | 16 / 32 | 3.3 s, 23.8 | 21.2 s, 34.7 | 24 | 22.4 |
| dry-run first, manifests under the share | `adfirsts30-core-a` | 43.78 | -22.41 [-28.62, -16.90] | 36 (-12) | 0 / 39 | +3.6 | -27.7 | -24.8 | -51.1 | -34.5 | -3.35 | 5 / 43 | 3.7 s, 22.1 | 22.8 s, 34.1 | 24 | 23.4 |

**core-a, offline budget 140 s** (base `ship-core-a`: score 65.75, counted 48 of 48, placed 37.54, fill 35.9, cog 80.3, stability 96.7, placement 77.1, soft 46.4)

| form | record | score | delta [95 % CI] | counted | up / down | fill | cog | stab. | place. | soft | placed | races planner / dry-run | planner s, plan | dry-run s, plan | dry-run cut | optimize s |
|---|---|---:|---|---:|---|---:|---:|---:|---:|---:|---:|---|---|---|---:|---:|
| shipped (planner, then the dry-run; the race) | `ship-core-a` | 65.75 | base | 48 | - | 35.9 | 80.3 | 96.7 | 77.1 | 46.4 | 37.54 | 42 / 6 | - | - | - | - |
| dry-run alone | `adry-core-a` | 39.06 | -26.69 [-33.14, -20.45] | 32 (-16) | 0 / 42 | +3.7 | -34.3 | -32.9 | -58.1 | -35.6 | -3.50 | 0 / 48 | - | - | - | - |
| planner alone | `aplan-core-a` | 66.68 | +0.93 [+0.12, +2.09] | 48 (+0) | 7 / 0 | -1.1 | +1.7 | +0.1 | +2.7 | +3.4 | -0.31 | 48 / 0 | - | - | - | - |
| dry-run first, every layout | `adfirst-core-a` | 65.53 | -0.22 [-0.67, +0.00] | 48 (+0) | 0 / 2 | +0.0 | -0.1 | -0.3 | +0.0 | -1.0 | -0.12 | 41 / 7 | 8.6 s, 36.7 | 43.4 s, 35.9 | 0 | 52.0 |
| dry-run first, dense manifests (share >= 0.62) | `adfirstd-core-a` | 65.75 | +0.00 [+0.00, +0.01] | 48 (+0) | 1 / 0 | +0.0 | -0.0 | +0.0 | +0.0 | +0.0 | +0.02 | 42 / 6 | 7.7 s, 36.7 | 37.8 s, 36.0 | 0 | 45.5 |
| dry-run first, manifests under the share | `adfirsts-core-a` | 65.52 | -0.23 [-0.67, +0.00] | 48 (+0) | 0 / 3 | -0.0 | -0.1 | -0.3 | +0.0 | -1.0 | -0.19 | 41 / 7 | 9.5 s, 36.7 | 48.6 s, 36.1 | 0 | 58.1 |

### What the records say

**The time regime.** The planner is the cheap half: 5-6 s a dense-a
manifest, 8-9 s core-a, 10-13 s hard-a here, so 12-65 s on the platform's
machine; its plan always finishes, at any budget here and there. The dry-run
is the expensive half: uncut it takes 25-33 s on dense-a, 38-49 s on core-a
and 65-70 s on hard-a here (the `adfirst*-*` 140 s records), 60-350 s on the
platform. So the platform's 119-139 s of optimize time is the dry-run running
into the deadline on nearly every manifest, and the bench's 20 s budget is
that regime: the deadline cut the dry-run on 41 of 48 dense-a and hard-a
episodes, at 30 s on 19 / 35 / 26 (dense / hard / core).

**The shipped race under the cut.** The cut does not hand the episode to
the dry-run: its cut plan is the smaller one (dense-a at 20 s: 21.4 items
against the planner's 24.9), so the planner's plan wins 46 of 48 dense-a,
40 of 48 hard-a and 44 of 48 core-a races at the short budgets, against 45 /
33 / 42 at 140 s, and the shipped form's score at 20 and 30 s is the 140 s
score within the race's own variance (dense-a 23.31 / 22.27 / 22.27, hard-a
42.16 / 39.93 / 39.57, core-a - / 66.19 / 65.75). The dry-run wins a race
where the planner's plan is under the threshold (hard-a at 20 s:
a-hard-s0044 planner 14, dry-run 25 of 43, 27 placed; a-hard-s0020 12
against 17 of 75; a-hard-s0006 22 against 27 of 41), and a cut dry-run plan
is still the better plan there. That is the mechanism the platform's sample
shows (planner 21, dry-run 25 of 41), and the bench's hard-a has it on 8-15
of 48 episodes.

**The dry-run alone** loses at every budget on every suite: dense-a -9.5 to
-10.5 (counted 10-11 -> 1), hard-a -7.4 to -9.8 (26-28 -> 20-21), core-a
-26 (48 -> 32-33). Its plan carries far less soft and priority cargo
(core-a placement -58, soft -36) and fewer items (dense-a -6.5 to -7.2), and
at 20 s it is cut on 39-44 of 48 episodes. The platform's sample, where it
beat the planner by four items, is the exception on the bench, not the rule.

**The dry-run first** at the short budgets is the dry-run alone: with 20 or
30 s the dry-run leaves less than `plan_min_seconds` (15 s), the planner
never runs (0-5 of 48 episodes), and the cost is the dry-run's (dense-a
-10.5 at 20 s, -6.4 at 30 s; hard-a -11.0 / -4.5; core-a -17.3 at 30 s).
Gated to dense manifests (`adfirstd`) it is the same on dense-a (every
manifest is over the share) and -5.2 / -3.1 on hard-a; gated to the
manifests under the share (`adfirsts`) it leaves dense-a alone (-1.05 at 20
s, +0.98 at 30 s, identical records at 140 s) and costs hard-a -7.1 / -2.4
and core-a -22.4 at 30 s. At 140 s, where the dry-run finishes and the
planner runs after it, the three forms are the shipped form on dense-a
(identical records) and -0.2 to -1.5 on core-a and hard-a (not
significant; `adfirsts-hard-a` +1.02 [-0.38, +3.60] is race variance: 3 up,
5 down). Nothing here gives the dry-run its time without taking the
planner's, and the planner's plan is the one worth having.

**The planner alone** is the only form never worse than the shipped race,
and better on core-a: +0.93 [+0.12, +2.09] at 140 s and +0.48 [+0.04,
+1.14] at 30 s (soft +2.4 to +3.4, placement +0.8 to +2.7, fill -0.9 to
-1.1, 48 of 48 counted); dense-a +1.26 [-0.12, +3.63] at 30 and 140 s (one
more counted episode) and +0.22 at 20 s; hard-a +0.15 / -0.30 / -2.48
[-6.27, +0.20] at 140 / 30 / 20 s. Where it gains is where the shipped
race hands the episode to the dry-run's plan: on core-a's six such scenes
the dry-run's plan is worth 58.8 an episode and the planner's 66.1 (the
dry-run's plan wins the race's score on fill and items with fewer soft and
priority boxes, which the platform prices higher); on dense-a's three, 24.1
against 44.4 (a-c1x50-s0011 counted by the planner's plan). Where it loses
is hard-a's sub-threshold rescue: on the 15 scenes the race gives the
dry-run at 140 s the dry-run's plan is worth 48.6 and the planner's 45.6
(one counted episode fewer), and at 20 s 51.2 against 42.8 on 8 scenes; the
planner's run-to-run variance on the other 33 (+1.6) hides it in the suite
mean. Its optimize time is 5-13 s here, 12-65 s on the platform, the rest
of the 140 s unused.

### Reading

- At the platform's budget the best measured form is the planner alone on
  core-a and dense-a and the shipped race on hard-a; the dry-run-first
  forms lose at every short budget and gain nothing at 140 s. **No form
  that gives the dry-run its time beats the shipped form**, at any budget.
- At the full budget the planner alone beats the shipped form on core-a
  (+0.93, the interval clear of zero) and is level on dense-a and hard-a.
  That gain comes from the race's score picking the dry-run's plan on
  6 of 48 core-a episodes where the platform's price prefers the planner's:
  the race's weights (fill 1, soft 0.5, priority 0.5, count 3) are not the
  platform's.
- **Recommended Task A form for the next submission: none of these; the
  shipped race stays.** The planner alone is the one candidate (`arm_aplan_a`,
  `offline_dry_run=false`), but the platform's only Task A data point is the
  sample, a sub-threshold-planner manifest of the hard-a kind (planner 21 =
  the threshold at fill 20.1, dry-run 25 at 32.1), where the dry-run's plan
  is worth about 3.4 points more by the fill alone and the planner's plan
  holds the count by one item; the bench's hard-a says the same (-2.5 at
  20 s). Shipping the planner alone bets that the platform's counted A
  episodes are of core-a's kind and not the sample's.
- The measurement that decides it is the trunk's new `sample-a` suite (the
  sample's own manifest, resampled): the shipped race against the planner
  alone there, at 20-30 s. If the planner alone holds the sample's kind, it
  ships; if not, the next form is a race that keeps the planner's plan
  unless it is under the threshold (the `plan_prefer_planner` rule with its
  threshold clause, unmeasured here; it would still prefer the planner on
  the sample itself, where the planner sits exactly at the threshold, so
  the clause would have to yield at the threshold too), which takes
  core-a's and dense-a's gain and keeps hard-a's rescue.
