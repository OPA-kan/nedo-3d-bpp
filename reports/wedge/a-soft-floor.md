# Task A: soft cargo as a floor under hard cargo when the count is at stake

Question: on dense Task A manifests the planner places the hard cargo first and
the soft boxes, the smallest items, find no room on top (60 items -> 28-30
placed against a threshold of 31, 13-16 soft boxes left). Tasks B and C already
let hard cargo cover soft cargo under the count threshold (`count_mode`).
Can Task A plan the soft boxes as a floor under the hard rows, and does it buy
crossings?

Two parts: what the official simulator does with hard boxes on soft boxes
(the probe), then the plan (`plan_soft_floor_under_count`, off by default).

## 1. The probe: hard cargo on soft cargo in the official simulator

`scripts/soft_floor_probe.py` builds a private world with the official
validator and physics (the sample's ULD, no shelf), places boxes as the agent
commands them (2 cm floor lift, a stacked box at the settled top of what is
under it, carried in from the door) and records per placement the validator's
verdict, the settle displacement (commanded to settled centre, the 2 cm floor
lift included), the tilt; after the load each box's top against its nominal
top, the soft boxes' penetration into the floor plane, the evaluator's fill
inclusion and the bench's shake proxy. The item classes are the bench's
(`bench.scenes.SKUS`, `EXTRA_SKUS`) with their soft physics (contactStiffness
2000-3000, contactDamping 600-800, linearDamping 0.8). Every case was run a
second time with the soft boxes replaced by hard boxes of the same size and
mass (`--control`), to separate the soft physics from the geometry (the
transport bands at the shelf level, overhangs). 148 cases; the full table is
`a-soft-floor/probe-table.md`, the raw records `a-soft-floor/probe.json`,
`probe-control.json`.

Soft classes: D 0.50x0.40x0.40 (k 3000), E 0.45x0.30x0.20 (2000), F
0.65x0.35x0.23 (2500), G 0.60x0.30x0.25 (3000), J 0.40x0.40x0.60 (2500).
Hard: A 0.55x0.40x0.24, B 0.65x0.45x0.25, C 0.75x0.56x0.27, H 0.80x0.60x0.50.

| form | cases | placed | tilt (deg) | hard sink (cm) | topples under the shake | reading |
|---|---:|---|---|---|---|---|
| one hard box on one soft box | 20 | 19 of 20 (G+H: transport, also in the control) | 0.1-7.6; E under C/H 22 | 0.5-4.0 | 2 (D+H, G+B) | stands, except the small E under the big C/H boxes |
| two soft boxes side by side, one hard box bridging (same height) | 12 | 12 | 0.2-2.6; EE+C 5.3 | 1.1-2.3 | 1 (GG+C; the control topples too) | stands |
| bridging two soft heights 2-3 cm apart (EF, FG) | 6 | 6 | 2.3-4.3 | 1.0-2.7 | 1 (FG+C, also the control) | stands |
| bridging 5 cm (EG) / 15 cm (DG) apart | 6 | 6 | 5.4-17.3 / 16.6-23.9 | | 0 | tilts: the floor must be level |
| two soft storeys under one hard box | 12 | 10 of 12 (2xE+C settle failure, 2xG+C transport) | 0.2-14.3 | 4.3-8.8 | 3 | no: one storey only |
| one soft box under a column of 2-4 hard boxes | 36 | settle failures E+4xA, E+3xB, G+3xB, G+2xC (the control places all but the C overhangs) | to 41 | to 9.6 | E+2xA 2, E+3xA 3, G+3xA 3, G+4xA 4, G+2xB 2, F+4xB 4, D+4xC 4 (control 0) | no isolated columns |
| one soft row (along the back wall) under 1-4 hard rows | 38 | the band at the shelf level (control alike), plus D row + 3/4xA where the sink puts the third layer's bottom into the band at 0.90 m (control passes) | 0.5-17 | 1.5-11 | E row + 3xB 6, F row + 4xB 8, D row + 1xB 1 (control 0); with A rows none to 1.18 m | one isolated row carries two hard layers, not four |
| a soft block two rows deep under 1-3 hard layers | 18 | all but the band (control alike) | 0.6-3.1 | 1.0-4.6 | 0 | stands |
| a soft floor over the whole floor depth under 3-5 hard layers (tops 0.94-1.45 m) | 18 | all but the band | 0.7-3.4 | 2.7-6.2 | 0 | stands to 1.45 m |
| the same with rows of two heights (GFFE, FGFG: 2 cm steps) | 8 | all but the band | 1.9-4.9 | 2.4-6.2 | 0 | stands |
| rows 5 cm apart (GEGE) | 4 | | 2.9-7.9 | | 1 (control 2) | marginal |

What it measured:

- **Hard on soft survives placement, settle and the shake when the soft is a
  level block.** A floor of soft boxes in whole rows under three to five hard
  layers settled within 3.4 degrees and toppled nothing under the shake, the
  top at 1.41-1.45 m (E and G floors under A and B rows). The hard-for-soft
  control of the same geometry behaves the same.
- **What does not stand:** two soft storeys under hard cargo (sinks 4-9 cm,
  three topples in twelve), a single soft box under a column of two or more
  hard boxes (E, G: topples or settle failures), a single soft row under three
  or four hard layers of B (6-8 topples), the small E box under the C or H box
  (22 degrees), soft heights more than 3 cm apart under one hard box
  (5-24 degrees).
- **The soft boxes sink.** A soft box alone penetrates the floor plane by
  1.2 cm under its own weight; under one hard layer 2-3 cm, under three to
  five 4-7 cm; a hard box on top sits 1-6 cm under its nominal top, and the
  sink differs from box to box by 1-3 cm under different loads. The soft box
  itself does not deform (a rigid body with a soft contact), so it is the
  heights that move, not the shapes.
- **Fill:** a soft box on the floor is outside the evaluator's fill
  inclusion at a margin of +5 mm in every case, alone too (1.2 cm into the
  floor plane), as the bench's C records show for every soft floor box
  (fill_evaluator_tolerant 1-5 points under fill_volume on core C). A soft box
  that would otherwise stay out of the container costs no fill by going on the
  floor; a hard box it displaces would.

So part 2 may plan **one storey of soft boxes of one height, in whole rows
from the back wall, with hard layers on it up to the ceiling**; no soft on soft
under hard, no isolated soft columns.

## 2. The plan: `plan_soft_floor_under_count`

All in `rule_alpha/planner.py` (own functions, `_soft_floor_*`) and
`rule_alpha/config.py` (`plan_soft_floor_*`), every flag off by default:

- **Gate.** After the planner's variants, when the chosen plan holds fewer
  than the count threshold plus `plan_value_margin` items, the manifest is
  planned once more with the first variant's settings and the soft floor; the
  soft-floor plan plays when it holds more items and itself holds the
  threshold plus the margin (`plan_soft_floor_needs_gate`, added after the
  second CI round). Over the gate nothing changes; on core-a the c1 plans
  of 19-22 items (threshold 21) are under it, so the variant is planned
  there too.
- **The floor.** The non-priority soft boxes whose flattest pose is at most
  `plan_soft_floor_max_height` (0.30 m: E, F, G) and of one height band
  (`plan_soft_floor_level_tolerance` 5 mm, the band with the most footprint),
  in rows from the back wall (the row planner's own layout search), the floor
  only, one pass (`pack_rows(..., floor_only=True)`).
- **The hard rows on it.** The cover veto is waived for the soft floor boxes
  alone (`_cover_view`; priority cargo and every other soft box keep it), the
  soft floor carries load (the stability model's floor-share gate off, soft
  tops to the floor storey's height), the soft headroom reserve off
  (`plan_soft_floor_keep_reserve`; with it the hard rows stop under the cap
  and the variant held fewer items than the plan on 7 of 11 dense scenes).
  `plan_soft_floor_hard_max_top` caps the hard tops over the floor (0 = no
  cap, the probe's blocks stood to 1.45 m).
- **The sink.** The hard rows are planned on the soft floor 3 cm below its
  nominal top (`plan_soft_floor_sink`) and every hard pose over the floor must
  also be legal on the board as it would stand if the floor did not sink
  (`_soft_floor_unsunk_ok`). Without the second check the plans used the sink
  to slip a layer under the transport band at the shelf level (the
  validator's lift is clipped when a top comes within 9.8 cm under 0.805 m),
  and the replay missed it where the soft sank 1.5 cm less (a-hard-s0047,
  a-c1x60-s0002: 34 planned, 15 placed).
- **Replay.** Poses over the floor are marked (`over_soft`); the replay
  waives their soft cover, reads supports within 3 cm
  (`plan_soft_floor_contact_tolerance`: the uneven sink) and tries the
  settled height within 6 cm up or down (`plan_soft_floor_replay_drop`).
- **Online.** Once a soft-floor plan plays, the online board reads the floor
  boxes as hard cargo (`plan_soft_floor_online`, `soft_floor_board_view` in
  `_policy_inner`): without it a replay miss over the floor left the ladder no
  legal pose over most of the floor (the cover rule) and the episode declined
  at 12 of 26 planned items.
- **The dry-run race.** A soft-floor plan under the threshold yields to the
  dry-run plan when that holds more items (`soft_floor_yields`): the plan
  score's soft share had kept a 59-item soft-floor plan over a 63-item
  dry-run on a-hard-s0019. With the gate rule a soft-floor plan that plays
  holds the threshold, so the rule is a guard for `plan_soft_floor_needs_gate=false`.

The arm: `reports/bench/arms/arm_asoftfloor.txt` = the shipped A arm +
`plan_soft_floor_under_count=true`.

### Design iterations (analytic plan counts, then local physics)

| form | analytic: dense c1x50/c1x60 s1-6 (base 313) | local physics |
|---|---|---|
| floor + hard rows, reserve kept, cap 1.0 m | 315 best-of | - |
| reserve off in the variant | 336 | - |
| control: reserve off, no soft floor | 342 (soft placed 0-2 a scene) | - |
| + online view, replay tolerance | | dense c1x50 s2/3/5/6, c1x60 s3/5: 20-25 against the base's 24-30 |
| + planned 3 cm sink | 344 | 15-27: the plans used the sink under the band |
| + the unsunk check (the committed form) | 19 scenes (7 dense, 12 hard-a misses) 592 -> 640 best-of: dense +5, hard-a +43 | see below |

Local physics of the final form (offline budget 60 s, against the CI baseline
`ship-*`):

| scene | threshold | baseline placed | soft floor placed | soft covered |
|---|---:|---:|---:|---:|
| a-c1x50-s0002 | 26 | 25 | **28** (crosses) | 4 |
| a-hard-s0047 | 49 | 41 | **58** (crosses) | 21 |
| a-hard-s0032 | 26 | 17 | 25 | 4 |
| a-hard-s0021 | 70 | 59 | 62 | 11 |
| a-hard-s0016 | 41 | 37 | 34 | 4 |
| a-hard-s0019 | 64 | 63 (dry-run) | 59 (before the dry-run rule) | 15 |

## 3. CI

Physics, budget 4.5 s, 6 shards a suite, the shipped A arm + the flag
(`arm_asoftfloor.txt`), branch `claude/rl-packing-policy-ftogt3-a-softfloor`.
Baselines: `reports/bench/ship-core-a`, `ship-hard-a`, `ship-dense-a` (the
shipped arm on the trunk). Three rounds, the code changing between them:

- `asoftfloor-*` (round 1): the form above without the two rules below.
- `asoftfloor2-*` (round 2): the dry-run yield only while the soft-floor plan
  is under the threshold. Hard-a and dense-a read as round 1; core-a lost a
  crossing (a-c1-s0012: plan 21 of a threshold of 21 replayed to 20, where
  the shipped plan's 19 had replayed to 21).
- `asoftfloor3-*` (round 3, the committed form): the soft-floor plan plays
  only when it holds the threshold plus the margin itself
  (`plan_soft_floor_needs_gate`, default on).
- `asoftfloor-off-core-a`: the shipped arm on this branch's code (the flag
  off). It reproduces the baseline's three c2p differences (s0002, s0008,
  s0011, 3 items each, one through the dry-run race) exactly, so those are
  the CI run's, not the flag's; the flag never plans a soft floor on c2p.

| suite | arm | crossings | placed | fill | soft placed | soft covered (episodes' sum) | priority placed / covered | topples (episodes) | CoM ratio |
|---|---|---:|---:|---:|---:|---:|---|---|---:|
| core-a | shipped (trunk) | 48 | 37.54 | 36.24 | 7.94 | 0 | 5.31 / 1 | 4 (3) | 0.3264 |
| core-a | flag off (this branch) | 48 | 37.38 | 36.26 | 7.71 | 0 | 5.31 / 1 | 8 (4) | 0.3270 |
| core-a | round 1 | 48 | 37.56 | 36.70 | 7.60 | 4 | 5.15 / 1 | 9 (5) | 0.3347 |
| core-a | round 2 | **47** | 37.50 | 36.37 | 7.81 | 5 | 5.25 / 2 | 8 (4) | 0.3319 |
| core-a | **round 3** | **48** | 37.52 | 36.39 | 7.83 | 2 | 5.29 / 1 | 8 (4) | 0.3302 |
| hard-a | shipped | 26 | 46.83 | 35.40 | 8.10 | 7 | 8.04 / 13 | 19 (10) | 0.3500 |
| hard-a | round 1 | 28 | 47.75 | 35.05 | 9.67 | 66 | 8.02 / 12 | 22 (13) | 0.3418 |
| hard-a | round 2 | 28 | 47.52 | 34.91 | 9.56 | 67 | 7.90 / 13 | 23 (13) | 0.3405 |
| hard-a | **round 3** | **29** | 47.69 | 35.56 | 8.94 | 31 | 8.06 / 12 | 19 (10) | 0.3518 |
| dense-a | shipped | 10 | 28.10 | 41.47 | 6.17 | 37 | 3.92 / 23 | 8 (7) | 0.3478 |
| dense-a | round 1 | 11 | 28.31 | 41.66 | 6.52 | 49 | 3.92 / 23 | 12 (9) | 0.3520 |
| dense-a | round 2 | 11 | 28.31 | 41.66 | 6.52 | 49 | 3.92 / 23 | 12 (9) | 0.3520 |
| dense-a | **round 3** | **11** | 28.17 | 41.57 | 6.23 | 40 | 3.90 / 23 | 8 (7) | 0.3489 |

Round 3 against the shipped records, by episode (`judge2.py`, `cmp_dirs.py`):

- **core-a** 48 -> 48; against the flag-off control on the same code the
  only changes are a-c1-s0002 21 -> 24 (soft 4 -> 8, 2 covered), s0007
  22 -> 25 (soft 4 -> 8), s0009 22 -> 23: placed +0.15, soft share
  0.454 -> 0.462, priority share 0.781 -> 0.776 (one box), soft covered
  0 -> 2, topples equal, CoM +0.003. Margin 0/+1 episodes 9 -> 7.
- **hard-a** 26 -> 29. The soft floor played (the analytic replay of the
  planner, `a-soft-floor/analytic-attribution.txt`) on s0023, s0025, s0029,
  s0047, s0048: **s0047 41 -> 58 (threshold 49, 21 soft boxes covered),
  s0029 9 -> 16 (threshold 16)** cross; **s0048 22 -> 20 (threshold 21)**
  falls under (a 24-item soft-floor plan replayed to 20); s0023 and s0025
  went to the dry-run as before. s0017 (83 -> 86) and s0038 (36 -> 37) cross
  where the flag planned no soft floor: run-to-run variation, as are s0010
  +7, s0018 +8, s0028 -11 (rounds 1 and 2 had none of these, and had
  s0036 +11, s0030 +5 instead). Attributable: +2 / -1 crossings.
- **dense-a** 10 -> 11: a-c1x50-s0002 25 -> 28 (threshold 26; soft 5 -> 8,
  3 more covered) is the only change. The soft floor plans on c1x60-80 hold
  20-31 items against thresholds of 31-41: the manifests the platform's
  uncounted A episodes look like are not reached.
- Policy time max 3.77 / 5.21 / 5.44 s (base 3.64 / 5.30 / 5.02); the
  variant adds one plan (3-8 s locally) to the optimize call, under the gate
  only.

## Verdict

**The physics allows a soft floor; the planner can use it only rarely, and
the count it buys on the bench is two episodes in 144.** The probe says a
level soft floor of whole rows carries the hard rows to the ceiling (1.45 m,
no topple), one storey only, no isolated soft columns. The plan built on it
passes the ship rule on the letter (core-a 48 of 48 with its soft share
0.462 against the control's 0.454; hard-a crossings 26 -> 29, dense-a 10 ->
11), but what the flag itself moves is +2 / -1 hard-a crossings and +1
dense-a crossing, at 21 + 3 + 2 more covered soft boxes, and the dense
manifests of 70-80 items stay where they were (no soft-floor plan reaches
their thresholds). Three things limit it:

1. **The transport band at the shelf level.** A 0.20-0.25 m soft floor
   shifts every hard layer above it by that much, and the third layer's top
   then lands in the 9.8 cm under 0.805 m where the simulator clips the
   carry-in lift; the planner can only use the floor where the shifted
   layering still clears the band.
2. **The sink.** The soft boxes sink 1-6 cm, unevenly, under their loads.
   Plans that used the planned sink to fit a layer replayed to half their
   items; the committed form plans every pose over the floor so that it is
   also legal if the floor does not sink, which keeps the replay honest and
   removes most of the analytic gain on the dense manifests (+31 items over
   12 dense scenes in the fragile form; +5 over the 7 of them re-planned in
   the robust one).
3. **The floor tiles worse than the hard rows.** One soft height band
   (E, F or G) a floor, 3-4 boxes across the 1.47 m floor where the hard
   rows fill it exactly, so the floor holds 6-8 soft boxes and the strip
   beside it goes to hard boxes of another height.

Price: about 0.03 points a covered soft box on A (1 / soft total of the soft
score), against 2.3 points a platform crossing. On the bench round 3 covered
26 more soft boxes for 3 crossings gained and 1 lost: positive at those
prices, but the hard-a gains are on soft-heavy hard-suite manifests (s0047:
59 soft of 97) and the platform's A manifests are, by every reading so far,
sample-like mixes in one container of 80-110 items, where the variant does
not reach the count.

Recommendation: **do not ship as a Task A change on this evidence**; keep
the flag (`plan_soft_floor_under_count`, default off) and the probe. If the
platform's uncounted A episodes turn out to be soft-heavy, the flag is the
lever that moves them (s0047 +17 items, a crossing). The count on the
dense sample-like manifests needs volume, not a different floor: the
smallest items up to the threshold need a fill of 0.38-0.45 on c1x70/c1x80,
the pipeline plateaus at 28-29 items and 41-43 fill.

What a next step would try: (a) a soft floor in the band's shadow, i.e. a
soft storey whose height plus the hard layers' land the third layer above
the band rather than in it (choose the height band by the layering, not by
footprint); (b) the soft floor only in the strip the hard rows leave (the
0.34 m beside a row of three 0.45 m boxes), so the hard layering stays
whole; (c) the stack option's own soft-floor poses online, where the
settled heights are known.

## Files

- `scripts/soft_floor_probe.py` (the probe; `--control`, `--only`, `--json`),
  `a-soft-floor/probe.json`, `probe-control.json`, `probe-table.md`,
  `probe_table.py`.
- `rule_alpha/planner.py` (`_soft_floor_*`, `soft_floor_board_view`,
  `soft_floor_yields`; `pack_rows(floor_only=...)`, the replay's
  `over_soft` handling), `rule_alpha/config.py` (`plan_soft_floor_*`),
  `rule_alpha/agent.py` (the online board view, the dry-run rule),
  `tests/test_agent.py` (`SoftFloorPlanTests`).
- `a-soft-floor/sf_eval.py` (the analytic base-vs-soft-floor plan counts),
  `analytic-attribution.txt` (all 144 scenes of the three suites, the
  committed form).
- Records: `reports/bench/asoftfloor-*`, `asoftfloor2-*`, `asoftfloor3-*`,
  `asoftfloor-off-core-a`; arm `reports/bench/arms/arm_asoftfloor.txt`.
