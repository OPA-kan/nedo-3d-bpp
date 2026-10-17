# The soft frame block: the count frame's soft cargo standing two deep against the back wall

The question (findings, "Where the re-plan's count is lost on the dense
manifests: the frame's soft boxes"): the v56 form at the platform's regime
(`acsfix30-dense-a`, offline budget 30 s) counts 12/12 of the c1x50
episodes, 9/12 at 60 items, 2/12 at 70 and 0/12 at 80; the plans replay
faithfully, and what is missing from the count is the count frame's soft
boxes (x80-s0003: the frame holds 20 soft boxes, the chosen "plain" re-plan
7). Why does the re-plan hold so few of them, and can a block built for
them hold the count?

Code: `rule_alpha/count_secure.py` (`pack_soft_block`, the `soft` token of
`plan_count_secure_blocks` in `plan_frame`), `rule_alpha/planner.py`
(`pack_typed_gallery` mode `column`, `_replay`'s per-entry nudge), flags
`plan_count_secure_soft_*` in `rule_alpha/config.py`; tests
`tests/test_count_secure.py::SoftFrameBlockTest`. Scripts, the analytic
sweeps and the local physics records in `reports/wedge/a-soft-frame/`.
Arms `reports/bench/arms/arm_asoft_a.txt` (`plain;soft;soft@ledge`) and
`arm_asoftnl_a.txt` (`plain;soft`), `arm_asofte_a.txt` / `arm_asoftnle_a.txt`
(the same with the row-end slack); records `reports/bench/asoft30-*`,
`asoftnl30-dense-a`, `asofte30-*`, `asoftnle30-*`, priced with
`bench.platform_score` against `ship30-*` and the v56 form `acsfix30-*`.

## 1. The cause: the plain re-plan has one layer for the soft cargo

The "plain" block is `_plan_once` under the count-secured overrides
(standing rows, the soft cargo's own rows): the hard rows first, the soft
cargo on top. On the c1 container (floor 1.47 x 1.38 m at floor level,
2.03 m^2; ceiling 1.57 m; the mid-height transport band at 0.70-0.80 m)
that is two flat layers of 0.65 x 0.45 boxes (tops 0.29 and 0.54 m), a
standing layer of 0.55 x 0.40 x 0.24 boxes to 1.09 m (a flat third layer's
top lands in the band), and the soft cargo on the standing tops, 1.09 ->
1.32-1.44 m: 12 + 15 + 7 on x80-s0003. The soft layer is one deep and
stays one deep: soft carries soft only under `soft_structure_max_top`
(0.7 m), so nothing may rest on a soft box at 1.09 m, and the 0.25 m left
under the ceiling holds nothing else. 2.03 m^2 of standing tops hold at
most 8-9 flat soft boxes, so the plain re-plan holds 5-9 of the frame's
15-23 soft boxes whatever the frame says, and the hard-column structure
caps at 34-36 items on the c1 container (`reports/bench/acsfix30-dense-a`:
plain plans 24-36). None of the suspects in the brief is the reason: the
headroom reserve stops the hard rows at 1.27 m (the standing layer ends at
1.09 m anyway), the cover rule only keeps hard cargo off soft, the row
depths and the floor strip share are the flat block's (`left` / `right` /
`back`, which lose to plain, `a-count-secure.md` section 2), the
typed-standing variants hold one standing layer (0.096 m^2 a box), and the
30 s budget never cut a re-plan (the plain plan takes 2-5 s here).

What the floor allows, read off the analytic model with the shipped caps
(`probe.py`, `probe2.py`; `soft_is_structure`, cap 0.7 m, floor share
0.35): a flat soft stack is two layers (the third's top, 0.73 m, is in the
band and the transport sweep refuses it: 0.127 m^2 an item); a standing
0.65 x 0.35 x 0.23 box has its top at 0.69 m, under the cap, so a second
standing box rests on it (to 1.34 m) once soft boxes cover 0.35 of the
floor, at 0.048 m^2 an item (0.096 m^2 of floor with the gaps, for two)
-- better than a hard column of the smallest boxes (two flat, one
standing, one soft on top: about 0.058 m^2 an item). The small shelf over the chamfer pocket
(the c1 container's ledge at 0.805-0.845 m, 0.44 m wide, the whole depth)
takes standing soft boxes too (tops at 1.45-1.50 m); the row planner never
rests cargo on it, since a box dropped over the ledge fits under it and
lands in the chamfer, which the validator refuses.

## 2. What was built

`plan_count_secure_blocks` token `soft` (`count_secure.pack_soft_block`,
planned in `plan_frame` like the other count-frame plans, ranked with
them: under the threshold by the count, over it by the plan score, the
planner's plan standing when it holds the trigger):

1. the count frame's soft cargo, the normal boxes first and the priority
   ones last (nothing normal may rest on a priority box), standing on the
   smallest face in rows against the back wall (`pack_typed_gallery` mode
   `column`: the typed gallery's rows, each of the depth that holds the
   most items per metre), the rows stopping once the floor holds a base
   for every box left and the soft floor share the support rule asks is
   covered (never more than `plan_count_secure_soft_rows` rows, and past
   `plan_count_secure_soft_depth_share` of the depth only while the share
   is short, since nothing would stand on the first layer otherwise);
2. a second standing layer on the first (`plan_count_secure_soft_layers`
   2): each base takes a box of its own class, else any standing soft box
   within its footprint (the support rule wants most of the footprint
   carried), the validator refusing what the cap or the share forbids;
3. `plan_count_secure_soft_ledge` (the `soft@plan_count_secure_soft_ledge=true`
   token): before the rows, standing boxes along the small shelf's top,
   their bottom the shelf's top, from the back;
4. the frame's hard cargo in rows on the floor in front of the block (the
   normal hard cargo, the priority hard cargo on its lines), then the rest
   as `plan_frame` plans it: the bigger hard cargo on the frame's rows,
   the rest of the soft cargo on whatever top takes it, the pose search;
   the frame's steps first in the replay order.

Two physics facts shaped it (section 3): a standing soft box settles 2.3
cm towards the opening, every box of every row (a-c1x60-s0001), so the
block's rows keep `plan_count_secure_soft_gap` (3 cm) over the planner's
gap and the hard rows start that far in front of the block's edge; and the
replay's nudge (2 cm) was short of the 2.6 cm clearance the slid neighbour
left, so the block's plan entries carry `replay_nudge`
(`plan_count_secure_soft_nudge`, 4 cm), which `planner._replay` reads.
Without them the block's third row and the hard rows missed at replay, the
ladder laid the missed soft boxes on the floor where the hard rows were
planned, and the episode placed 29 of a 33-item plan; with them 31 of 31
(counted).

All of it is off unless the token is named; the typed gallery's `stand`
and `tower` modes and every test of the trunk are unchanged (222 in
`tests.test_rule_alpha tests.test_agent tests.test_bench`, 25 in
`tests.test_count_secure`, 6 of them new).

## 3. Analytic plans and local physics

The analytic sweep (`sweep.py`, `sw_gap.jsonl`, `tab.py`; the v56 arm with
`plain;soft;soft@ledge` at 30 s, the planner alone): per count, the mean
plan the re-plan started from, the plain re-plan's, and the plan the
re-plan picked with the block among the candidates; the plans at or over
the threshold; how often the block was picked; the soft boxes planned.

| items | base plan | plain re-plan | with the soft block | plans over the threshold: plain / with block | block chosen | soft planned: plain / with block | planner s |
|---|---:|---:|---:|---|---:|---|---:|
| c1x50 | 24.1 | 26.8 | 27.7 | 10 / 9 of 12 | 2 | 6.5 / 8.9 | 7.9 |
| c1x60 | 25.2 | 30.4 | 31.2 | 7 / 8 of 12 | 2 | 6.2 / 9.3 | 11.5 |
| c1x70 | 25.1 | 30.6 | 31.5 | 0 / 0 of 12 | 5 | 6.2 / 12.8 | 15.1 |
| c1x80 | 25.2 | 31.1 | 32.4 | 0 / 0 of 12 | 6 | 6.8 / 14.1 | 16.6 |

(The c1x50 column's 10 / 9: c1x50-s0003's plain plan of 26 yields to a
typed-standing plan of 24 with the higher plan score, as the v56 arm
already does; the block is not in that choice.) The block holds the
frame's soft cargo (18-24 soft boxes planned where plain holds 5-9) and is
picked on 15 of 48 scenes, where it adds 1-7 items to the plan
(x70-s0001 29 -> 32, x70-s0004 33 -> 35, x80-s0001 29 -> 33, x80-s0004
33 -> 36, x80-s0010 25 -> 29); on the other 33 the plain plan holds more,
because the block's rows are 0.25-0.35 m deep and three of them (the floor
share) leave the hard rows a strip of one row. No c1x70 or c1x80 plan
reaches its threshold (36 / 41): the best are 35 and 36. The three
re-plans take 5-9 s here (plain 2-5 s, the block 1-3 s, the ledge form
1-8 s), 12-25 s on the platform's machine, inside its 140 s.

Local physics (`python -m bench run`, the `asoft` arm at 30 s, policy
budget 4.5 s; `reports/wedge/a-soft-frame/phys_*`), against the v56
records at the same budget:

| scene | threshold | v56 placed / soft | block placed / soft | block plan | pick | topples |
|---|---:|---|---|---:|---|---:|
| a-c1x60-s0001 | 31 | 30 / 6 | **31** / 22 | 30 | soft + ledge | 0 |
| a-c1x60-s0009 | 31 | 31 / 9 | 31 / 9 | 27 | plain | 0 |
| a-c1x70-s0001 | 36 | 29 / 6 | 34 / 20 | 32 | soft | 0 |
| a-c1x70-s0004 | 36 | 33 / 6 | 35 / 23 | 35 | soft + ledge | 0 |

The block replays (a-c1x60-s0001: the first miss at step 29, a soft box on
the hard rows' top), the standing columns to 1.34 m and the ledge's boxes
at 1.45-1.50 m did not topple under the shake, and the episodes place the
plan plus the ladder's 0-2.

## 4. CI (physics, policy budget 4.5 s, 6 shards, offline budget 30 s)

`bench.platform_score` against the shipped form at the same budget
(`ship30-*`) and against the v56 form (`acsfix30-*`; on sample-a the v56
re-plan never ran, `acountfix30-sample-a` is the shipped record exactly).
The arms: `asoftnl` = the v56 form with `plain;soft`; `asoft` = with
`plain;soft;soft@plan_count_secure_soft_ledge=true`. Columns as
`platform_score` prints them: the score, the paired delta with the
bootstrap interval, the counted episodes, episodes up / down, the five
components' deltas, placed, the policy's max step time.

**dense-a** (base `ship30-dense-a`: 22.27, counted 10 of 48; v56
`acsfix30-dense-a`: 38.27, counted 23)

| form | record | score | delta vs shipped [95 % CI] | delta vs v56 [95 % CI] | counted | up / down vs v56 | fill | cog | stab. | place. | soft | placed |
|---|---|---:|---|---|---:|---|---:|---:|---:|---:|---:|---:|
| v56 | `acsfix30-dense-a` | 38.27 | +16.00 [+9.52, +23.28] | base | 23 | - | +2.1 | +20.3 | +26.5 | +23.8 | +14.0 | +2.88 |
| block | `asoftnl30-dense-a` | 38.63 | +16.36 [+9.70, +24.08] | **+0.36 [-1.18, +2.85]** | 24 (+1) | 1 / 7 | -2.9 | +1.6 | +2.0 | +1.0 | +2.0 | +0.17 |
| block + ledge | `asoft30-dense-a` | 36.60 | +14.33 [+7.70, +22.08] | -1.67 [-5.41, +1.80] | 23 (+0) | 1 / 13 | -6.2 | -0.0 | +0.0 | -2.2 | +3.0 | -0.08 |

By count (v56 -> block -> block + ledge; counted of 12, placed, soft
placed; `ci_tab.py`):

| items (threshold) | counted | placed | soft placed | block picked (nl / ledge form) |
|---|---|---|---|---|
| 50 (26) | 12 -> 12 -> 12 | 27.7 -> 27.7 -> 27.7 | 7.0 -> 7.0 -> 8.2 | 1 / 2 |
| 60 (31) | 9 -> **10** -> 9 | 31.4 -> 31.5 -> 31.0 | 6.8 -> 8.1 -> 9.3 | 1 / 2 |
| 70 (36) | 2 -> 2 -> 2 | 31.8 -> 32.6 -> 32.3 | 6.8 -> 10.3 -> 12.7 | 3 / 5 |
| 80 (41) | 0 -> 0 -> 0 | 33.0 -> 32.8 -> 32.7 | 7.0 -> 11.3 -> 13.8 | 4 / 6 |

Where the block played (the `count_secure` dict of the records): the
plan replays and the episode gains on a-c1x60-s0001 (30 -> 31, counted),
a-c1x70-s0001 (29 -> 34), a-c1x70-s0011 (29 -> 34), a-c1x80-s0001 (30 ->
34), a-c1x70-s0004 (33 -> 35, the ledge form), a-c1x80-s0004 (33 -> 35,
ledge); it loses where a block pose misses at replay and the ladder lays
the missed soft box flat on the floor in the strip the hard rows were
planned on, after which the hard rows have no floor: a-c1x80-s0009 (30 ->
25, both forms), and in the ledge form a-c1x60-s0004 (32 -> 26, the
crossing lost, two topples), a-c1x70-s0006 (32 -> 26), a-c1x80-s0012 (34
-> 30). `replay_dbg.py` on the settled boards: the missed pose is a row's
last box, planned at the wall's clearance, whose row neighbour drifted a
centimetre -- the replay cannot slide it right (the wall) and the ladder
takes over. The fill falls on the uncounted c1x70 / c1x80 episodes
whichever form: the block trades 0.07-0.11 m^3 hard boxes for 0.05 m^3
soft ones, and under the count the fill is the only component scored.

**hard-a** (base `ship30-hard-a`: 39.93, counted 26 of 48; v56
`acsfix30-hard-a`: 45.95, counted 31), the ledge form:

| form | record | score | delta vs shipped [95 % CI] | delta vs v56 [95 % CI] | counted | up / down vs v56 | fill | cog | stab. | place. | soft | placed |
|---|---|---:|---|---|---:|---|---:|---:|---:|---:|---:|---:|
| v56 | `acsfix30-hard-a` | 45.95 | +6.01 [+1.18, +11.88] | base | 31 | - | +0.0 | +7.9 | +10.1 | +9.9 | +5.3 | +1.77 |
| block + ledge | `asoft30-hard-a` | 46.72 | +6.79 [+1.75, +12.91] | **+0.78 [-0.68, +3.42]** | 32 (+1) | 4 / 8 | -2.1 | +1.8 | +2.0 | +1.3 | +2.7 | +1.17 |

The block was picked on 12 of 48: a-hard-s0032 18 -> 26 (counted, the
threshold 26), s0030 66 -> 85 (threshold 105), s0023 30 -> 38,
s0037 14 -> 26, s0027 24 -> 30, s0001 44 -> 50; s0040 15 -> 12 and
s0016 39 -> 38 down. Topples 20 -> 22 (s0001 and s0037 two each, s0023
and s0030 none from three and one).

**core-a** (base `ship30-core-a`: 66.19, all 48 counted; v56
`acsfix30-core-a`: 66.47): `asoft30-core-a` 66.26, +0.07 [-0.30, +0.47]
against the shipped form, **-0.21 [-0.64, +0.00]** against v56: one
episode, a-c1s-s0010 (23 -> 25 placed, two priority boxes fewer: cog
-0.6, placement -0.8), the other 47 identical in count, soft and
priority.

**sample-a** (base `ship30-sample-a` = `acountfix30-sample-a`: 59.23, all
12 counted): `asoft30-sample-a` 61.26, **+2.03 [+0.00, +4.89]**, 2 up / 0
down: the block picked on s0000 (the sample itself: the planner's plan 23
-> 25, the race still the dry-run's 25) and s0002 (25 -> 26 placed, soft 0
-> 14, priority 0 -> 1), soft +13.6, placement +2.8, cog +2.3, fill -3.0.

**The row-end slack (round 2, `asoftnle30-*` / `asofte30-*`:
`plan_count_secure_soft_end_slack=0.03`, the rows ending 3 cm short of
the wall so a row's last box can slide).** It changes which rows hold
five boxes, and the plans with it: against v56, dense-a without the ledge
-0.36 [-0.70, -0.07] (counted 23: the block is no longer picked on
a-c1x60-s0001, whose crossing round 1 won; a-c1x80-s0009 holds its 30
now), with the ledge -1.07 [-1.70, -0.50] (23 counted; a-c1x60-s0006 31
-> 32, a-c1x70-s0011 29 -> 26); hard-a without the ledge -1.41 [-3.86,
-0.07] (counted 30: a-hard-s0032 25 of 26, a-hard-s0047 49 -> 59), with
the ledge -0.36 [-0.78, +0.00] (31 counted, placed +1.38, soft +1.3,
fill -1.9); core-a -0.42 [-1.27, +0.00] (no block picked; a c2 scene's
race variance); sample-a +2.03 [+0.00, +4.89] again (the block on s0002).
The slack buys nothing the first form lacks, and the records say why the
block's gains are fragile: the row packing is rigid (a centimetre of
slack decides whether a row holds four boxes or five), and one missed
pose at replay costs the hard rows their floor.

**Time.** The planner's seconds a dense-a episode 4.5-8.4 -> 6.1-13.0
(the two block plans 1-3 s each, 2-8 s with the ledge, after the plain
re-plan and the typed variants), the optimize 14-24 -> 17-27 s of the 30
s: the dry-run was cut on more episodes (its plan loses the race there
anyway, section 7 of `a-count-secure.md`). On the platform's machine
(2.5-3 times slower) the planner's 30-40 s leave the dry-run 100 s of the
140. hard-a's largest manifests: planner up to 26 s (s0030, 120 items).

## 5. Verdict

- **The cause is the one layer.** The plain re-plan's soft cargo rides on
  the hard rows at 1.09 m, where soft cannot carry soft (the 0.7 m cap),
  and the standing tops hold 5-9 boxes; the frame's soft boxes are not
  refused by any rule the brief named (reserve, cover, cap, depths, strip
  share, budget) but by where the plan puts them. The block holds them:
  on the floor, standing two deep (0.048 m^2 an item), soft planned 6.2-6.8
  -> 8.9-14.1 a dense manifest, and the bench's soft component +2.0 /
  +3.0 on dense-a, +2.7 on hard-a, +13.6 on sample-a.
- **The count moves by one episode a suite, not by the ten the frame
  promised.** dense-a 23 -> 24 counted (block, no ledge), hard-a 31 -> 32,
  core-a and sample-a all counted already. The c1x70 / c1x80 thresholds
  (36 / 41) stay out of reach: the best plans hold 35 and 36, and the
  container's floor at 0.05 m^2 an item is the limit, not the frame.
  Where the block adds items to an uncounted episode it costs fill (the
  only component scored there): dense-a fill -2.9 / -6.2.
- **Priced against v56:** block without the ledge, dense-a +0.36 [-1.18,
  +2.85] (24 counted); with the ledge dense-a -1.67 [-5.41, +1.80],
  hard-a +0.78 [-0.68, +3.42] (32 counted), sample-a +2.03 [+0.00,
  +4.89], core-a -0.21 [-0.64, +0.00]; with the row-end slack dense-a
  -0.36 [-0.70, -0.07] / -1.07 [-1.70, -0.50], hard-a -1.41 [-3.86,
  -0.07] / -0.36 [-0.78, +0.00]. Nothing clears its interval on the
  dense suite the block was built for; the one interval clear of zero on
  the good side is sample-a's edge, and the ones clear on the bad side
  are the slack forms. **Not a ship candidate as measured.**
- On the platform the v56 form's planner alone scored 56.43 with the
  shipped race's count of A episodes (the coordinator's reading): the
  re-plan as shipped crosses none of the platform's uncounted A
  episodes, and what they need is exactly the one-episode-a-suite gain
  the block shows here -- +1 counted on dense-a (the no-ledge form) and
  on hard-a (the ledge form), neither on the same form, and each paid in
  fill on the episodes that stay out. Were the platform's uncounted A
  manifests of the c1x60 kind (a plan 1-3 items short), the no-ledge
  block would be the form to try there; of the c1x70 / c1x80 kind, no
  plan of this pipeline reaches them.
- Open: the fill price (the re-plan's rank under the threshold could
  weigh the score where the count stays out of reach), and the replay's
  fragility (a missed block pose should go to the tail of the order
  instead of the ladder's floor). Kept, off: the `soft` token and its
  fields default to the v56 form.
