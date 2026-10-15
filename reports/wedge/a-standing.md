# Task A: the typed-standing plan (soft and priority cargo standing on the floor, under the count gate)

The question: on a dense Task A manifest the planner places the hard cargo
first and the soft cargo last, and the soft boxes (the smallest items of the
manifest) are left out while the count falls short (findings, "Why Task A
episodes fall under the count"). Does standing the soft and priority cargo
on its smallest face, against a wall and braced by the hard rows, fit the
count beside the hard rows, and what does it cost in stability?

Code: `rule_alpha/planner.py` (`count_frame`, `pack_typed_gallery`,
`_plan_typed_once`, `plan_typed_standing`, `_plan_tail`; `pack_rows` takes a
y window), flags in `rule_alpha/config.py` (`plan_typed_standing*`), tests
`tests/test_bench.py::TypedStandingTests`, probe
`scripts/standing_rows_probe.py`. Arms `reports/bench/arms/arm_astand*_a.txt`.
Records `reports/bench/astand-*`, `astand2-*`, `astandfb-*`, `astandff-*`
against `ship-*-a` (physics, budget 4.5, 6 shards).

## 1. The probe: standing rows in the official simulator, under the shake

`scripts/standing_rows_probe.py` builds the rows by hand in the c1
container (a standing box is the SKU with its smallest face down; floor
poses commanded 2 cm over rest, stacks at the settled top, gaps 2.6 cm) and
reads the bench's shake proxy (`terminal_metrics(with_shake=True)`). The
hard row is what the planner builds on a dense manifest: B boxes flat two
high, A boxes standing on top (top 0.94 m).

| arrangement | placed | standing | settle shift max | topples (standing) | shake shift max / mean | CoM |
|---|---:|---:|---:|---:|---:|---:|
| G row (4 x 0.30 x 0.25 x 0.60), wall only | 4 | 4 | 0.30 cm | 0 (0) | 0.7 / 0.34 cm | 0.182 |
| G row, wall + hard row in front | 14 | 4 | 0.30 cm | 0 (0) | 4.0 / 1.93 cm | 0.226 |
| G row behind a hard row already placed | failed: the G box is refused (`is_valid` false: carried over the hard row) | | | | | |
| G row, open floor | 4 | 4 | 0.27 cm | 0 (0) | 0.6 / 0.23 cm | 0.183 |
| G row, hard row behind only (gallery at the opening) | 14 | 4 | 0.44 cm | 0 (0) | 6.6 / 2.68 cm | 0.225 |
| mixed soft row (E, G, F, E), wall only | 4 | 4 | 0.69 cm | 0 (0) | 1.3 / 0.60 cm | 0.171 |
| mixed soft row, wall + hard row | 14 | 4 | 0.26 cm | 0 (0) | 4.0 / 2.12 cm | 0.223 |
| mixed soft row, open floor | 4 | 4 | 0.28 cm | 0 (0) | 0.5 / 0.30 cm | 0.171 |
| mixed soft row, hard row behind only | 14 | 4 | 0.25 cm | 0 (0) | 6.6 / 2.68 cm | 0.223 |
| priority A/B row standing (0.55 / 0.65 tall), wall only | 3 | 3 | 0.28 cm | 0 (0) | 0.0 / 0.01 cm | 0.185 |
| priority A/B row, wall + hard row | 13 | 3 | 0.28 cm | 0 (0) | 1.8 / 0.81 cm | 0.226 |
| priority A/B row, open floor | 3 | 3 | 0.22 cm | 0 (0) | 0.0 / 0.00 cm | 0.185 |
| two soft rows (mixed + G), wall only | 8 | 8 | 0.48 cm | 0 (0) | 0.8 / 0.29 cm | 0.177 |
| two soft rows, wall + hard row | 18 | 8 | 0.46 cm | 0 (0) | 4.0 / 1.59 cm | 0.216 |
| G flat (reference), wall only | 2 | 0 | 0.06 cm | 0 (0) | 0.0 / 0.03 cm | 0.074 |

Every soft class and the standing priority hard boxes stand on their
smallest face: settle shift under 0.7 cm, no topple under the shake in any
arrangement, braced or not; what moves under the shake is the hard row (the
standing A boxes on its top), 4-6.6 cm, most when the gallery is in front of
it (hard row against the wall, open side towards the opening). The gallery
must be planned before the hard rows that close it in: a soft box behind a
placed hard row is refused on the way in. The probe does not separate
braced from unbraced: a single standing row on a level floor does not tip
under this shake whatever is beside it. The difference shows on the real
boards (section 4).

## 2. Design

`plan_typed_standing` (default off), in `planner.plan_packing` after the
ordinary variants:

1. When the ordinary plan holds fewer than threshold + `plan_value_margin`
   items (the gate), the typed-standing plans of
   `plan_typed_standing_variants` are planned while the budget lasts.
   Otherwise nothing changes (the shipped plan stands).
2. The **count frame** (`count_frame`): every priority item, then the
   smallest items by volume of any class until the gate is filled. Its soft
   items and (`plan_typed_standing_priority`, default on) its priority items
   form the gallery (in a layout with a priority container the priority
   cargo goes there as before).
3. **Gallery** (`pack_typed_gallery`): rows from the back wall towards the
   opening, each row left to right, every box on its smallest face under
   `plan_typed_standing_max_top` (0.7 m: a 0.75 m standing box lies on its
   0.56 side), the priority cargo first; a row's depth is the one holding
   the most items per metre of depth; at most `<rows>` rows a container.
   `tower` mode lays the soft flat and stacks towers of one class on every
   base while the supporting top is under the soft structure cap (0.7).
4. **Hard rows** (`pack_rows` with a y window) in the rest of the floor:
   `back` -- the gallery against the back wall, the hard rows in front of
   it (each gallery box braced by the wall behind and the first hard row in
   front); `front` -- the hard rows from the back wall, the gallery in the
   front rows at the opening (braced by the hard row behind, open in
   front); `top` -- no floor gallery, the gallery's items at their
   least-footprint legal pose anywhere after the hard rows. Then the soft
   left over on the hard rows and the greedy pose search, as in the
   ordinary plan.
5. **Choice**: the plan that holds the gate, then the plan score
   (`plan_score_weights`), between the ordinary plan and every typed plan.
   The count is checked on the plan the replay plays (as every plan
   variant is); the online replay is unchanged.
   `plan_typed_standing_force` (measurement only) plays the best typed plan
   on every manifest.

Variant syntax `"<at>-<mode>-<rows>[-soft|-prio][-noreserve]"`.

## 3. Analytic plans (planner only, no physics)

Planned items, 16 dense-a scenes (c1x50-80, seeds 1-4) and hard-a seeds
1-16, base plan against each typed plan forced:

| | base | back-stand-1 | back-stand-2 | back-tower-2 | front-stand-2 |
|---|---:|---:|---:|---:|---:|
| dense (16), mean planned | 26.8 | 21.9 | 23.5 | 17.5 | 22.0 |
| hard (16), mean planned | 45.3 | 44.9 | 44.9 | 38.9 | 42.3 |

On the c1 container the ordinary plan holds 25-31 items whatever the
manifest's size (50-80): two flat hard layers, a standing third (the
mid-height transport band ends flat layers at 0.54 m), soft on top at 0.94
m. A standing gallery holds about one item per 0.09 m^2 of floor (with the
2.6 cm gaps), the hard columns about one per 0.075 m^2, so on paper the
gallery trades hard columns for soft boxes about one for one or worse; the
towers (soft on soft) lose more, because the soft floor share the support
rule asks (0.35) is rarely reached and the flat bases take the floor. On the
hard suite's varied containers the gallery wins on some manifests (s0004
52 -> 58, s0010 64 -> 71-79, s0012 39 -> 44) and loses on others. The
`noreserve` and soft-only forms move nothing beyond that spread. The plan
count is not the episode's: the episodes below decide.

## 4. Physics (CI, budget 4.5, against the shipped A arm)

### The gated form: `back-stand-2;back-stand-1;front-stand-2` (`astand-*`)

| suite | crossings | placed | fill | soft placed / covered | priority placed / covered | shake topples (episodes) | CoM |
|---|---|---:|---:|---|---|---|---:|
| dense-a | 10 -> **15** (6 in, 1 out) | 28.10 -> 28.54 (21 up, 11 down) | 41.47 -> 39.45 | 6.17 -> 7.69 / 37 -> 22 | 3.92 -> 5.02 / 23 -> 21 | 8 (7) -> 2 (2) | 0.348 -> 0.346 |
| hard-a | 26 -> **31** (5 in, 0 out) | 46.83 -> 48.35 (13 up, 3 down) | 35.40 -> 35.11 | 8.10 -> 11.00 / 7 -> 7 | 8.04 -> 8.63 / 13 -> 17 | 19 (10) -> 20 (9) | 0.350 -> 0.347 |
| core-a | 48 -> 48 | 37.54 -> 37.69 (7 up, 3 down) | 36.24 -> 36.16 | 7.94 -> 8.21 / 0 -> 0 | 5.31 -> 5.27 / 1 -> 1 | 4 (3) -> **10 (5)** | 0.326 -> 0.323 |

Crossings in: dense-a c1x50-s0001, s0010, c1x60-s0001, s0005, s0008, s0009
(c1x50-s0007 out, 26 -> 23); hard-a s0016, s0017, s0021, s0029, s0047.
Priced on the continuous reading (`cmp_dirs.py`, the suite's third of the
total): dense-a +1.14, hard-a +0.83, core-a +0.28. Policy time max 2.9 /
5.4 / 3.7 s.

Where the typed plan played (the first placements soft or priority standing
on the floor): 32 of 48 dense-a episodes, 8-11 of hard-a, 8 of core-a (all
on c1 / c1s, whose ordinary plans sit at 21-24 items against a gate of 23).
On core-a the typed episodes placed +16 items with
every crossing kept; the topples: a-c1s-s0003 0 -> 2 (typed: a hard B box at
1.04 m and the soft box on it), a-c2p-s0008 0 -> 3 (not typed: the flag
moved the plan from the planner's to the dry-run's, soft 11 -> 3, three A
boxes stacked to 1.3 m), a-c2p-s0011 1 -> 2 and a-c2p-s0002 (identical
replay to step 47-50, then the run's timing). **No standing gallery box
toppled in any episode of any suite**; the added topples are hard boxes
high on the stacks that the narrower floor left for the hard rows.

### The gallery forced on every manifest: braced against unbraced

| arm | suite | crossings | placed | soft share | priority share | soft / priority covered | topples (episodes) | CoM | priced |
|---|---|---|---:|---:|---:|---|---|---:|---:|
| shipped | dense-a | 10 | 28.10 | 0.338 | 0.581 | 37 / 23 | 8 (7) | 0.348 | |
| back-stand-2 forced (braced: wall + hard row) | dense-a | 8 (2 in, 4 out) | 25.69 | 0.489 | 0.728 | 39 / **0** | **1 (1)** | **0.334** | +1.53 |
| front-stand-2 forced (open in front) | dense-a | 13 (5 in, 2 out) | 26.77 | 0.427 | 0.805 | 62 / **86** | **27 (16)** | 0.355 | +0.65 |
| shipped | hard-a | 26 | 46.83 | 0.351 | 0.837 | 7 / 13 | 19 (10) | 0.350 | |
| back-stand-2 forced (braced) | hard-a | 30 (6 in, 2 out) | 47.04 | 0.533 | 0.905 | 7 / 12 | **10 (5)** | **0.339** | +1.60 |

The stability cost is not where it was expected. The braced gallery
*lowers* the load (CoM -0.011 to -0.014) and the topples (dense-a 8 -> 1,
hard-a 19 -> 10): the standing soft boxes are light and their tops at
0.45-0.65 m, below the hard stacks they replace. The unbraced gallery at the
opening triples the topples (8 -> 27 in 16 episodes) and covers 86 priority
and 62 soft boxes (against 23 and 37): the gallery stands where the cargo
placed after it is carried in, and what the replay or the ladder puts there
lands on it. Forced
everywhere the braced gallery costs count on dense-a (-2.4 placed, 8
crossings) -- the analytic trade above -- and gains on hard-a; gated, it
plays only where the ordinary plan misses the gate and the plan score
prefers it, which is where it pays.

### The braced form alone, and without priority-container layouts

The unbraced `front-stand-2` was chosen on 5 dense-a episodes in the gated
run (placed +12, soft / priority covered +5 / +11), so the variants were cut
to the braced ones (`arm_astand2_a.txt`, `back-stand-2;back-stand-1`), and
then also kept off layouts with a priority container
(`plan_typed_standing_no_priority_container`, `arm_astand3_a.txt`): on
core-a the c2p scenes are where the flag cost items and added topples
(c2p-s0002, s0008, s0011 -3 each; s0008 moved from the planner's plan to
the dry-run's, soft 11 -> 3, three A boxes toppled from 1.06-1.3 m). The
core-a records of `astand` and `astand2` are identical scene for scene, so
those changes are the flag's, not the runner's.

| arm | suite | crossings | placed | fill | soft placed / covered | priority placed / covered | topples (episodes) | CoM | priced |
|---|---|---|---:|---:|---|---|---|---:|---:|
| shipped | dense-a | 10 | 28.10 | 41.47 | 6.17 / 37 | 3.92 / 23 | 8 (7) | 0.348 | |
| astand2 (= astand3: no priority container in dense-a) | dense-a | **15** (6 in, 1 out) | 28.31 | 39.23 | 7.65 / 16 | 4.73 / 9 | **1 (1)** | 0.341 | +1.18 |
| shipped | hard-a | 26 | 46.83 | 35.40 | 8.10 / 7 | 8.04 / 13 | 19 (10) | 0.350 | |
| astand2 | hard-a | **32** (6 in, 0 out) | 47.96 | 34.93 | 10.73 / 7 | 8.46 / 15 | 20 (9) | 0.346 | +0.79 |
| astand3 | hard-a | **30** (4 in, 0 out) | 47.21 | 34.84 | 9.71 / 5 | 8.31 / 11 | 17 (8) | 0.344 | +0.71 |
| shipped | core-a | 48 | 37.54 | 36.24 | 7.94 / 0 | 5.31 / 1 | 4 (3) | 0.326 | |
| astand2 | core-a | 48 | 37.69 (7 up, 3 down) | 36.16 | 8.21 / 0 | 5.27 / 1 | 10 (5) | 0.323 | +0.28 |
| astand3 | core-a | 48 | **37.83 (6 up, 0 down)** | 36.14 | 8.40 / 0 | 5.27 / 1 | **6 (4)** | 0.322 | +0.36 |

Crossings in: dense-a c1x50-s0001, s0010, c1x60-s0001, s0005, s0008, s0009
(c1x50-s0007 out, 26 -> 23 against 26); hard-a astand2 s0016, s0017, s0021,
s0029, s0038, s0047; astand3 s0021, s0029, s0038, s0047 (s0016 has a
priority container; s0017 83 -> 83 against 86 in this run, 86 in the other
two). Shares on core-a (astand3): soft 0.464 -> 0.504, priority 0.781 ->
0.771 (two priority boxes fewer over 48 scenes: c1-s0010, c1s-s0011 5 -> 3,
c1-s0009, c1s-s0010 up 2 each, c1-s0007, c1s-s0003 down 1). The two added
topples are a-c1s-s0003 (typed, 22 -> 23 placed): a hard B box at 1.04 m and
the soft box on it, not a gallery box. Policy time max 5.3 s (hard-a), 3.7 s
(core-a), 5.3 s (dense-a).

### Local physics (4 dense-a and 4 hard-a scenes, offline budget 30 s, four at a time)

Noisy (the same base scene places 27-30 between runs) but in line with CI:

| arm | dense-a placed (c1x50-s2, c1x60-s2, c1x60-s5, c1x70-s3) | hard-a placed (s4, s6, s10, s12) | topples | CoM hard-a |
|---|---|---|---:|---|
| shipped | 23, 27, 25, 25 | 49, 23, 62, 40 | 0 | 0.344, 0.370, 0.291, 0.295 |
| back-stand-2 forced | 22, 23, 25, 22 | 55, 25, 64, 44 | 0 | 0.279, 0.460, 0.272, 0.317 |
| front-stand-2 forced | 19, 19, 24, 23 | 52, 21, 73, 37 | 0 | 0.358, 0.332, 0.335, 0.291 |
| gated (3 variants) | 22, 27, 30, 25 | 51, 23, 64, 40 | 0 | |

## 5. Why it works where it does

The analytic trade (a standing gallery holds about as many items per square
metre of floor as the hard columns it displaces) says the forced gallery
cannot raise the count on the c1 container, and forced it does not (dense-a
-2.4 placed). Gated, it plays only where the ordinary plan misses the gate
and the plan score -- whose count term weighs 3 and whose soft and priority
shares weigh 0.5 each -- prefers it, and there the episode gains. The
likely reasons (read off the records, not isolated): the gallery's boxes
are the first placements on an empty floor and replay as planned, where the
ordinary plan's soft rows sit last, on uneven hard tops at 0.94 m; and the
soft and priority cargo is placed early, so a decline late in the
hard rows no longer ends the episode with the valuable cargo still out
(dense-a soft placed 6.2 -> 7.7, priority 3.9 -> 4.7, priority covered 23 ->
9). The crossings come from scenes 1-5 items short (c1x60-s0009 23 -> 31,
hard-a s0029 9 -> 18, s0021 59 -> 70); dense-a's c1x70 / c1x80 manifests
(thresholds 36 / 41) stay out of reach of any plan of this pipeline (best
33).

## 6. Verdict

The typed-standing plan, gated by the count and braced against the back
wall, is the first Task A lever on the bench that crosses dense manifests:
**dense-a 10 -> 15 crossings, hard-a 26 -> 30-32, core-a 48 of 48**, with the
soft share up on all three suites, the load lower and fewer topples on
dense-a (8 -> 1) and hard-a (19 -> 17-20, level). Standing boxes did not
topple in any episode or probe arrangement; the stability cost the brief
expected from standing boxes is not there when the gallery is braced, and is
large when it is not (the front gallery forced: topples 8 -> 27, priority
covered 23 -> 86).

Against the ship rule for A, the best form (`arm_astand3_a.txt`:
`plan_typed_standing=true, plan_typed_standing_variants=back-stand-2;back-stand-1,
plan_typed_standing_no_priority_container=true`) meets: core-a 48 / 48,
placed +0.29 (6 up, 0 down), soft share +0.04; hard-a +4 and dense-a +5
crossings. It misses by a hair on two counts: core-a topples 4 -> 6 (one
episode, a-c1s-s0003, two non-gallery boxes high on a hard stack, the
episode itself +1 item) and the core-a priority share 0.781 -> 0.771 (two
priority boxes over 48 scenes). Strictly, **not adopted under the rule as
written**; on the platform's terms (about 2.3 points an A episode moved
over the count, 3-5 such episodes) the gain dwarfs one core-a episode's two
topples, so it is a ship candidate for the coordinator's call, the form
above, with `astand2` (priority-container layouts included: +2 hard-a
crossings, core-a topples 4 -> 10) as the alternative. Not measured: the
platform's slower machine (each typed variant is a planner pass, 3-30 s
here, so the two variants add up to a minute here to the 140 s optimize budget
and five times that there; the variant loop stops when the next pass would
not finish, and the dry-run after it gets what is left).
