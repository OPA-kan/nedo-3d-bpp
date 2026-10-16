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
`arm_asoftnl_a.txt` (`plain;soft`); records `reports/bench/asoft30-*`,
`asoftnl30-dense-a`, priced with `bench.platform_score` against
`ship30-*` and the v56 form `acsfix30-*`.

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
floor, at 0.048 m^2 an item (0.0805 m^2 of floor for two) -- better than a
hard column of the smallest boxes (two flat, one standing, one soft on
top: about 0.058 m^2 an item). The small shelf over the chamfer pocket
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

(pending)

## 5. Verdict

(pending)
