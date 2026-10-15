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
   unchanged: 211 in `tests.test_rule_alpha tests.test_agent
   tests.test_bench`, plus 8 new ones in `tests/test_count_secure.py`).
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
