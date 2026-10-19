# The dense plan off the sample mix: what its fixed numbers cost on other manifests, and what reading them off the manifest recovers

The question: Task A's dense count-secured plan (`rule_alpha/count_secure.py`
`plan_dense`, the shipped tokens
`plain;dense;dense@plan_standing_rows_max_height=0.4;dense@...=0.4&plan_count_secure_dense_priority_rows=1&plan_count_secure_dense_soft_thin=0.25`
under `plan_count_secure_soft_cap=1.6`; `reports/wedge/a-dense.md`,
`a-dense-quality.md`) was built and tuned on manifests of the official
sample's SKU mix (hard 0.55 x 0.40 x 0.24, 0.65 x 0.45 x 0.25, 0.75 x 0.56
x 0.27; soft 0.50 x 0.40 x 0.40, 0.45 x 0.30 x 0.20, 0.65 x 0.35 x 0.23,
0.60 x 0.30 x 0.25).  Some of its numbers are fixed rather than read off
the manifest.  (1) How much does the shipped plan lose when the mix
differs (bigger or smaller boxes, other soft shares and priority rates,
scaled containers)?  (2) Does deriving those numbers from the actual
manifest -- Task A sees the whole manifest offline -- recover it, without
changing anything on the sample mix?

Code: `rule_alpha/count_secure.py` (`adaptive_dense_tokens`,
`dense_standing_cap`, `carry_in_ok`, `soft_thin_threshold`,
`soft_layers_needed`; the cap resolved in `plan_dense`),
`rule_alpha/planner.py` (`manifest_row_depths`, `ROW_DEPTH_CLASSES`,
`online_row_lines(classes=)`), `rule_alpha/agent.py` (the manifest's row
depths in `optimize`), the flags `plan_count_secure_dense_adaptive`,
`plan_count_secure_dense_soft_layers`, `plan_row_depths_from_manifest` in
`rule_alpha/config.py` (all off by default); the suite `dense-mix-a`
(`bench/scenes.py` `make_dmix_scene`, `frame_demand`); tests
`tests/test_count_secure.py::AdaptiveDenseTest`, `ManifestRowDepthsTest`,
`tests/test_bench.py::SceneTests::test_dense_mix_scenes_...`.  Arm
`reports/bench/arms/arm_amix_a.txt` (the v59 form `arm_adenser_a` plus the
two flags); records `reports/bench/amix30-*`, priced with
`bench.platform_score` against the v59 records `adenser30-*`.  Scripts and
the analytic sweeps in `reports/wedge/a-mix/`.

## 1. The dense plan's fixed numbers, and what each one is

Every number in `plan_dense` and its tokens that is not read off the
board or the manifest, and what was done with it:

| number | where | what it stands for | adaptive form |
|---|---|---|---|
| `plan_standing_rows_max_height=0.4` (the on-edge token and the strip token) | the arm's tokens | the 0.55 x 0.40 x 0.24 class on edge: tops at 0.94 m in the c1 container, where two flat soft layers of the sample's 0.20-0.25 m classes fit under the ceiling | **derived** in the plan (`dense_standing_cap`): among no standing layer and every standing pose height of the frame's normal hard classes left after the flat layers, the cap whose layers hold the most items by an estimate (the standing slots of the tallest pose under the cap that the simulator can carry in and that keeps under the soft headroom reserve, in rows over the floor; up to two soft layers of the manifest's median soft height over the tops, each carried in, each the floor at the mean soft footprint, no more than the soft boxes), a cap whose tops take the two layers first, the lower cap on a tie; the token carries `plan_count_secure_dense_soft_layers=2` in place of the cap |
| the uncapped `dense` token | the arm's tokens | no number: the standing rows take the lowest poses first and the count-first layout picks (0.55 on end on the sample mix, 15 a layer) | kept as it is: the one-layer alternative the rank weighs the derived cap against |
| `plan_count_secure_dense_soft_thin=0.25` (the strip token) | the arm's tokens | the sample's three flat soft classes (0.20, 0.23, 0.25) laid before the 0.40 m one | **derived** (`soft_thin_threshold`): the manifest's flat soft heights sorted, a class is tall when it is 1.4 times the next thinner one, the threshold the tallest height under the first such jump; 0 (one pass) when no class is tall |
| the two flat layers / "two flat soft layers" | the docstrings, the count the estimate asks for | the row planner lays flat passes until one places nothing (the mid-height band stops a third 0.25 m layer at 0.79 m); the soft layers count what the cap leaves room for | not a number in the code: the flat top is read off the laid layers (`flat_top`), the soft layers asked are `soft_layers_needed` (two when the soft footprints cover more than three quarters of the floor, else one) and the geometry decides how many fit (`carry_in_ok`: the ceiling margin and lift clip, the mid-height band, the sweep's clearance, the soft cap) |
| the ledge: 0.44 m wide, 0.845 m top | the docstrings only | the c1 container's small shelf over the chamfer pocket | already the board's: `model.small_shelf` (scaled with the container, absent in none of the ULDs) |
| the priority strip's row arithmetic | `priority_strip` | the shallowest standing pose under the cap among the priority boxes, as many a row as the floor's width takes | already the boxes' and the floor's (`_standing_poses(p)`, `floor_rect`); it now reads the derived cap (`standing_config`) |
| `plan_count_secure_dense_priority_rows=1` | the strip token | one front row for the priority boxes | a count, not a mix number: kept |
| `plan_count_secure_soft_cap=1.6` | the arm | the plan's soft-on-soft cap, the c1 ceiling's height | kept: on a container under 1.64 m it never binds (the ceiling does), on a taller one it keeps the second soft layer under 1.6 m, which is what the physics was measured at (`a-dense.md`: the second layer at 1.17-1.40 m stands, at 1.32-1.52 m it toppled eight times) |
| the row-depth table `[0.56, 0.45, 0.40, 0.35, 0.30]` and the default `"0.56,0.45,0.4"` | `planner.online_row_lines` ("auto"), `config.online_row_depths` | the sample's hard flat depths and the soft widths that fill a floor's depth | **derived** under `plan_row_depths_from_manifest` (`planner.manifest_row_depths`): the distinct values of the hard boxes' two smallest dimensions for the table, the distinct middle dimensions for the default; the table's fallback with no hard box.  The shipped A arm runs neither the online rows policy nor the pool planner (`online_planner` is empty), so this changes nothing in its plans; it is there for the forms that do |
| `planner.SKU_MIX` | `mix_row_lines` (the "mix" rows spec) | the sample mix itself | not used by the A arm; left |
| `plan_typed_standing_max_top=0.7` | the ledge call (`pack_typed_gallery`) | the tallest standing pose of a soft box on the ledge | a stability cap, not a mix number (every soft class in the hard suites stands under 0.65 m); left |

The cap is resolved *in* the plan rather than at the token because the
flat layers' actual top is what the standing layer rests on, and which
classes tile the floor is the layout search's choice (on the sample mix
the 0.65 x 0.45 class, tops 0.29 / 0.54, by a tie-break among equal
counts; on a manifest without it the 0.55 x 0.40 class, 0.52): a cap
derived from the classes' thinnest dimensions alone would read 0.52 and
admit 0.55 on end for two layers by five millimetres.  The carry-in rules
are the simulator's (`transport.transport_lifts`): a box on packed cargo
needs a lift of at least the sweep's clearance (0.026 m), so the c1
ceiling of 1.57 m takes tops to 1.5255 m, and a top in the band under
the mid-height level (0.73-0.81 m in c1) cannot be carried in at all.
On the sample mix the estimate reads, over the 0.54 m flat top: cap 0.40
-- 10-11 on edge and two soft layers of 8 -- over 0.55 -- 13-15 on end and
one layer (the second would top 1.55) -- over no standing layer (the
soft on the flat top ends in the band): the shipped choice.  The first
cut of the rule took the count alone and on the few-soft dense-a
manifests picked 0.55 (15 + 8 against 10 + 9), changing eleven of the
first 26 dense-a plans; the rule now takes a cap whose tops take the
layers asked first, so the sample mix's plans are the shipped ones.

`plan_count_secure_dense_adaptive` rewrites the tokens
(`adaptive_dense_tokens`): a token's `plan_standing_rows_max_height`
becomes `plan_count_secure_dense_soft_layers=<1|2>`, its
`plan_count_secure_dense_soft_thin` the derived threshold, every other
field and every other token stays, a rewritten token equal to an earlier
one is dropped; the token count does not grow (the budget's share is the
shipped one).  The shipped arm's four tokens become `plain; dense;
dense@plan_count_secure_dense_soft_layers=2;
dense@plan_count_secure_dense_soft_layers=2&plan_count_secure_dense_priority_rows=1&plan_count_secure_dense_soft_thin=0.25`
on the official sample (the test `AdaptiveDenseTest` checks the strings,
the derived cap of 0.40, the thin threshold of 0.25, the plan of the
official sample manifest equal pose for pose to the plan without the
flag, and on a synthetic manifest of a 0.60 x 0.50 x 0.25 hard class --
no standing pose under 0.40 -- a cap of 0.50 and a fuller plan, 39
against 31).  The chosen cap and its estimate go into the re-plan's
record (`count_secure.variants[].standing_cap`) and the plan log.

## 2. The suite: `dense-mix-a`

`bench.scenes.make_dmix_scene` (seed 40000 + s): the mix one of the hard
suite's four (the sample's, big-heavy, small, with the extra SKUs) at
equal odds; one container scaled from the ULDs as the hard suite scales
them (length 0.85-1.25x, width 0.85-1.15x, height 0.85-1.2x, the chamfer
0.7-1.3x, a shelf one time in four), no priority container; the soft
share 10-60 %, the priority rate 0-30 %; the count the one of 60, 70, ...,
120 whose smallest half-plus-one items by volume come closest to a demand
drawn in 0.30-0.50 of the container's volume (`frame_demand`: what the
count asks of a Task A agent, which orders the manifest; dense-a's
c1x50-c1x80 ask 0.30-0.45), a draw over 0.55 redrawn with the same mix.
The brief's 60-90 items reach 0.16-0.26 on the small mix, under dense-a's
c1x50, so the count runs to 120 there.  48 scenes: sample 16, small 14,
extra 10, big 8; counts 60-120 (120 on 16, the small mixes); soft shares
0.1 x 8, 0.2 x 10, 0.32 x 10, 0.45 x 9, 0.6 x 11; priority rates 0 x 14,
0.05 x 9, 0.1 x 9, 0.2 x 10, 0.3 x 6; shelves 10; the demand 0.25-0.53,
median 0.36; no seed needed a redraw.  Per scene in
`reports/wedge/a-mix/suite.md`.

**`huge-a`** (added on the coordinator's platform reading, section 6):
`make_huge_scene` (seed 50000 + s): 100, 130 or 160 items (s mod 3, 12
scenes each), the mix the sample's one time in two (11 of 36) and the
hard suite's big-heavy (6), small (11) or extra (8) otherwise, the
container, the soft share and the priority rate as `dense-mix-a` draws
them, no demand check: the demand runs 0.15-1.05 (median 0.52), so the
count threshold is out of reach on most of them and the fill is the one
component scored.  Per scene in `reports/wedge/a-mix/suite_huge.md`.

## 3. `plan_count_secure_fill_first` (the coordinator's third ask)

The v59 platform reading (the re-plan ran, 35 -> 52 s, and never ranked a
dense plan over the plain one; the fill identical to the planner-alone
diagnostic's) says the platform's uncounted A manifests are the kind
where the count is out of reach, and there the dense plans are time
spent for nothing and the re-plan's rank -- the count first -- is the
wrong one: the fill is what is scored.  `plan_count_secure_fill_first=X`
(0: off): when the planner's plan holds fewer than X times the count
threshold, the re-plan ranks its plans by the planned volume
(`count_secure.plan_volume`, `_rank(by_fill=True)`) and skips the
`dense` tokens (`record.fill_first`, the skipped tokens marked); the
early re-plan's pick against the variants' choice is read the same way
(`prefer_secured`).  The volume of every plan made is now in the
re-plan's record (`variants[].volume`).  Arm `arm_afill_a.txt` (the v59
form plus `plan_count_secure_fill_first=0.85`).  Tests
`FillFirstTest`: the rank by volume, a 160-item manifest where the
dense tokens are skipped and the pick is the largest plan made, the
official sample unchanged (its plan holds the threshold, the rule never
fires).

## 4. The planner alone (analytic, the 30 s budget, `plan_sweep.py`, `sw_*.md`)

Both arms on every scene of dense-a and dense-mix-a, the plan the
optimize ships compared pose for pose (a digest of every entry's item,
centre and size):

| suite | scenes | identical plans | plans over the threshold base / amix | planned base / amix | soft | priority | planner s mean (max) base / amix |
|---|---:|---:|---|---|---|---|---|
| dense-a (c1x50-c1x80, the sample mix) | 48 | **48** | 46 / 46 | 38.4 / 38.4 | 14.4 / 14.4 | 4.0 / 4.0 | 14.8 (23.6) / 14.2 (24.2) |
| dense-mix-a | 48 | 40 | 16 / 16 | 45.1 / 44.9 | 12.2 / 12.1 | 5.3 / 5.4 | 22.4 (30.0) / 22.0 (30.0) |

On dense-a the adaptive form's plan is the shipped plan on all 48 scenes
(and on the official sample, `AdaptiveDenseTest`): the derived cap
reads 0.40 wherever a dense plan is made, the thin threshold 0.25, the
token strings differ in name only.  Two earlier cuts of the rule did
not have this property and are recorded here because they are what the
measurement would otherwise have hidden: the count estimate alone picked
0.55 on the few-soft dense-a manifests (eleven of the first 26 plans
changed, +1 to +3 items a plan for 1-3 priority boxes fewer), and a cap
resolved for the standing layer alone let the fill's standing rows
stand boxes above it (three plans a soft box apart).  On dense-mix-a
eight plans differ (`sw_dmix.md`): the derived cap is 0.0 -- no
standing layer -- on 19 of the 25 dense plans that resolved one (the
soft headroom reserve keeps the hard tops under the ceiling less the
tallest soft class, 0.89 m in a 1.38 m container, so no standing pose
fits over the flat layers; the big mix's boxes have no pose under any
reasonable cap), 0.40 on 3, 0.45 / 0.55 / 0.56 on one each; the same
16 plans over the threshold either way.

## 5. CI, the adaptive form (physics, policy budget 4.5 s, 6 shards, 30 s offline budget; `arm_amix_a` against `arm_adenser_a`)

`bench.platform_score`, the records `amix30-*` against the v59 records
`adenser30-*` (dense-mix-a's baseline run for this report):

| suite | v59 `adenser30-*` | `amix30-*` | delta [95 % CI] | counted | up / down | fill | cog | stab. | place. | soft | placed | optimize s mean (max) |
|---|---:|---:|---|---|---|---:|---:|---:|---:|---:|---:|---|
| dense-a | 69.64 | 69.64 | **+0.00 [+0.00, +0.00]** | 47 -> 47 | 0 / 0 | +0.0 | +0.0 | +0.0 | +0.0 | +0.0 | +0.00 | 13.3 (22.9) -> 15.2 (22.7) |
| core-a | 67.21 | 67.23 | +0.02 [+0.00, +0.07] | 48 -> 48 | 1 / 0 | +0.1 | -0.1 | +0.0 | +0.0 | +0.0 | +0.06 | 3.7 (18.5) -> 4.2 (13.5) |
| hard-a | 48.38 | 47.10 | -1.28 [-3.88, +0.02] | 33 -> **32** | 1 / 1 | -0.0 | -1.5 | -2.1 | -2.1 | -1.5 | +0.06 | 11.3 (30.1) -> 11.4 (29.9) |
| dense-mix-a | 25.82 | 25.86 | +0.04 [-3.47, +3.66] | 12 -> 12 | 8 / 5 | +0.0 | -0.1 | +0.2 | +0.0 | +0.1 | -0.02 | 20.6 (30.0) -> 20.8 (30.2) |

- **dense-a: identical**, episode for episode (48 of 48 the same score,
  the same 47 counted, no topple either way): the shipped plans on the
  sample mix are unchanged, which is the property that would make the
  form safe to ship blind.
- **core-a**: one scene, a-c1s-s0010 (+1.16: the strip's plan on the
  shelf container replaced by the unstripped on-edge plan, 26 -> 29
  placed, the same 5 of 5 priority boxes).
- **hard-a: one crossing lost**, a-hard-s0016 (-62.0 on the scene: 81
  items of the big mix in two containers, the threshold 41; both arms
  pick the strip plan of 42 planned with 17 soft and 5 priority, v59's
  replays to 41 placed and the adaptive one to 40.  The derived cap
  there is 0.0 -- the estimate reads no standing pose worth a layer over
  the 0.53 m flat top under the reserve -- against the fixed 0.40, which
  admits the mix's few 0.55 x 0.40 boxes on edge in the fill; a one-box
  difference in a plan that sits exactly on the threshold).  a-hard-s0018
  +0.39 (82 -> 86 placed, the planner's own plan).  The other 46
  identical in count.
- **dense-mix-a: nothing to recover.**  The shipped form counts 12 of 48
  (sample mix 6 of 16, big 1 of 8, extra 3 of 10, small 2 of 14; by the
  demand band 6 of 22 under 0.35, 6 of 19 at 0.35-0.45, 0 of 7 over
  0.45; `ci_amix30_dmix.md`), and the adaptive form the same 12: one
  big-mix crossing lost (a-dmix-s0037, 34 -> 27 placed at 31, -55.8) and
  one extra-mix crossing gained (a-dmix-s0042, 27 -> 31 at 31, +57.8),
  the rest within +2.2 / -3.3 on the fill of uncounted episodes.  By
  mix: big -7.05, extra +5.82, sample -0.03, small +0.06; the fill 40.34
  -> 40.37, the topples 9 -> 8, the optimize time the same.

So (1) the shipped dense plan loses most of its crossings off the
sample mix -- 12 of 48 against 47 of 48 on dense-a -- but (2) not for
the numbers the brief named.  The CI records say where the loss is: the
derived cap resolves to *no standing layer* on 36 of the 51 dense plans
it was asked for (18 with two soft layers estimated over the flat top,
12 with one, 6 with none), because the containers are scaled -- the soft
headroom reserve (the tallest soft class plus 5 cm) under a 1.3-1.5 m
ceiling leaves no room for a standing pose over two flat layers -- and
because the big mix's hard classes have no standing pose that fits; the
sample's 0.40 was a live candidate on 5 plans and 0.55 on 7.  Where the
count is out of reach (36 of 48 scenes, the demand 0.25-0.53 of a
container whose floor the mix's boxes tile worse than c1's), no cap
recovers it.  Reading the numbers off the manifest is therefore
*neutral*: +0.04 on the mix suite, identical on dense-a, one knife-edge
crossing lost on hard-a.

## 6. The huge manifests and the fill-first switch (the coordinator's platform reading)

v59 on the platform scored 56.25 against the planner-alone diagnostic's
56.43 with the fill identical to the second decimal and the same 19
counted episodes: the re-plan ran (optimize 35 -> 52 s) and never ranked
a dense plan over the plain one.  With the timing curve (41 items 7.5 s,
80 -> 30 s, 120 -> 50 s, 160 -> 65 s here, the platform 1.4x slower) the
platform's mean A manifest reads as 90-100 c1-equivalent items, so the
uncounted A episodes are probably 100 items and more, where the count
threshold is out of reach of any plan and the fill is the one
component scored.  `huge-a` (section 2) is that regime; the runs there
are at the arm's own 140 s budget, the verdict the fill and the
optimize time (under 140 s on the platform: under 100 s here).

`bench.platform_score` and `ci_tab.py` (`ci_*_huge.md`), the v59 form
`adenser-huge-a` the base:

| arm | record | score | delta [95 % CI] | counted | up / down | fill (eval.) | placed | topples | optimize s mean (max) | scenes over 100 s |
|---|---|---:|---|---|---|---|---|---|---|---:|
| v59 | `adenser-huge-a` | 14.45 | base | 2 | - | 39.03 | 44.1 | 9 | 49.6 (139.6) | 6 |
| adaptive (`arm_amix_a`) | `amix-huge-a` | 15.83 | +1.38 [-0.34, +4.45] | 3 (+1) | 5 / 7 | 38.29 (-0.7) | 43.9 | 12 | 44.8 (126.2) | 4 |
| fill-first, dense skipped (`arm_afill_a`) | `afill-huge-a` | 12.68 | **-1.77 [-2.53, -1.08]** | 2 | 7 / 26 | **33.35 (-5.7)** | 39.6 | 9 | **25.9 (69.8)** | 0 |

By count (`ci_afill_huge.md`, `ci_amix_huge.md`):

| items (thr.) | v59 fill / placed / optimize s (max) | adaptive | fill-first |
|---|---|---|---|
| 100 (51) | 36.2 / 39.2 / 32.6 (56.5) | 36.3 / 39.7 / 24.5 (56.4); counted 2 -> 3 | 35.4 / 38.3 / 17.6 (41.8) |
| 130 (66) | 39.0 / 41.8 / 52.9 (139.6) | 37.0 / 41.0 / 53.9 (126.2) | 33.1 / 37.1 / 25.0 (49.3) |
| 160 (81) | 41.9 / 51.2 / 63.4 (121.2) | 41.6 / 51.0 / 55.9 (112.2) | 31.5 / 43.4 / 34.9 (69.8) |

- **The dense plans carry the fill on the huge manifests too.**  v59
  picks a dense plan on 33 of the 36 scenes (dense 15, on edge 11, the
  strip 7) although only 2 cross; with the dense tokens skipped the
  plain re-plan or the planner's own plan is all there is, and the fill
  falls 5.7 points (26 scenes down, 7 up: a-huge-s0024 53.2 -> 21.3,
  s0009 39.5 -> 20.9, s0005 49.2 -> 35.1).  The time saved is real --
  the mean 49.6 -> 25.9 s, the maximum 139.6 -> 69.8 s, every scene under
  100 s -- but it is bought with the one component the episode is scored
  on.  As specified (the dense tokens skipped) the switch is **not
  kept**; on dense-a it also loses 22 of 47 crossings (`afill30-dense-a`
  -27.31 [-34.45, -19.76]: the planner's plan under 0.85 x 41 on c1x80
  is the normal case there, and the dense plans are what cross), and
  core-a reads -0.05 [-0.16, +0.00].
- The variant that keeps the dense tokens and only ranks the plans
  under the threshold by their volume (`plan_count_secure_fill_first_skip_dense=false`,
  `arm_afillk_a`; a plan over the threshold still ranks first, so no
  crossing within reach is traded) is measured in section 6a.
- **The time.**  v59 itself runs over 100 s on 6 of the 36 huge scenes
  here (a-huge-s0017 139.6 s and s0023 139.5 s -- the whole 140 s budget,
  the plans cut; s0021 121.2, s0003 113.7, s0027 109.6, s0006 93.7), the
  adaptive form on 4 (126.2, 112.2, 111.3, 96.3; its mean 44.8 against
  49.6).  On the platform's slower machine these would hit the 140 s
  budget as the deadline (the optimize returns at the budget; the
  platform's 180 s optimization timeout holds), with the plans cut
  short.  The fill-first form's 25.9 s mean (69.8 max) is the only one
  comfortably under; a cheaper time lever than skipping every dense
  plan would be skipping the strip and uncapped tokens only where the
  count is out of reach, which this report did not measure.
- The adaptive form on huge-a: +1.38 n.s. (one crossing gained,
  a-huge-s0022 45 -> 51 of 100, +50.3; the fill -0.7; three topples
  more), the optimize 5 s shorter on average.

### 6a. Fill-first with the dense tokens kept (`arm_afillk_a`)

`plan_count_secure_fill_first=0.85` with
`plan_count_secure_fill_first_skip_dense=false`: the dense plans are
made and every plan under the threshold is ranked by its volume, a plan
over the threshold still first.  Records `afillk-huge-a`,
`afillk30-dense-a`, `afillk30-core-a` (`ci_afillk_huge.md`):

| suite | v59 | `afillk` | delta [95 % CI] | counted | up / down | fill | placed | optimize s mean (max) |
|---|---:|---:|---|---|---|---|---|---|
| huge-a (140 s) | 14.45 | 14.45 | +0.01 [-0.08, +0.08] | 2 -> 2 | 3 / 1 | 39.03 -> 39.06 | 44.1 -> 43.9 | 49.6 (139.6) -> 41.3 (139.5) |
| dense-a (30 s) | 69.64 | 69.64 | +0.00 [+0.00, +0.00] | 47 -> 47 | 0 / 0 | 54.27 -> 54.27 | 38.5 -> 38.5 | 13.3 (22.9) -> 13.0 (23.4) |
| core-a (30 s) | 67.21 | 67.21 | +0.00 [+0.00, +0.00] | 48 -> 48 | 0 / 0 | 34.63 -> 34.63 | 37.8 -> 37.8 | 3.7 (18.5) -> 3.7 (12.0) |

Harmless and worthless: the volume rank picks the plan the count rank
picked on 32 of the 36 huge scenes (the dense plan with the most items
is the one with the most volume), the fill moves +0.03, the crossings
and dense-a / core-a are v59's episode for episode.  The ranking was
never the problem on the huge manifests; the budget is (the plans cut
at 140 s on the 130-160-item manifests either way).

**The planner alone at the 140 s budget on the slowest huge manifests**
(`huge140.jsonl`, this machine): a-huge-s0017 (130 items) v59 139.8 s /
63 planned, adaptive 136.9 s / 59, fill-first 63.4 s / 46, kept-dense
135.8 s / 63; s0021 (160) 130.9 / 73, 129.2 / 73, 67.9 / 58, 133.1 / 73;
s0023 (130) 139.5 / 61, 106.3 / 73, 68.3 / 57, 139.8 / 61; s0036 (160)
105.9 / 76, 137.7 / 76, 55.9 / 67, 105.4 / 76.  The budget is the
deadline on these: the planner's own variants and the plain re-plan
take 60-70 s on 130-160 items here (the fill-first form's time), and
the dense plans take what is left to the 140 s.  On the platform (1.4x
slower) the dense plans would be cut or skipped by the start-factor
guard on such manifests, as hard-a's 88-120-item manifests already show
at the 30 s proxy (`a-dense.md`, section 5).

## 7. Verdict

- **(1) What the shipped dense plan loses off the sample mix**: on
  `dense-mix-a` it counts 12 of 48 against 47 of 48 on dense-a (the
  sample mix in scaled containers 6 of 16, big 1 of 8, extra 3 of 10,
  small 2 of 14; nothing over a demand of 0.45).  The loss is the
  containers and the counts, not the fixed numbers: the standing layer
  has no room under the soft headroom reserve in a 1.3-1.5 m container
  (the derived cap reads "no standing layer" on 36 of 51 dense plans),
  and the mixes' boxes tile the floor worse than c1's.
- **(2) Reading the numbers off the manifest recovers nothing
  measurable**: dense-mix-a **+0.04 [-3.47, +3.66]** (12 counted either
  way, one big-mix crossing lost and one extra-mix crossing gained),
  dense-a **+0.00 [+0.00, +0.00]** -- the plans are v59's pose for pose
  on all 48 scenes and on the official sample -- core-a +0.02 [+0.00,
  +0.07], hard-a **-1.28 [-3.88, +0.02]** with one crossing lost
  (a-hard-s0016, a 42-item strip plan replaying to 40 instead of 41 at a
  threshold of 41; the derived cap 0.0 against the fixed 0.40, one box
  of the fill), huge-a +1.38 [-0.34, +4.45] n.s.  The ship rule for A
  (no crossing lost on core-a / dense-a / hard-a) is broken on hard-a by
  that one knife-edge scene, and the mix suite does not pay for it:
  **not kept**.  The shipped plans on the sample mix are unchanged plan
  for plan (dense-a identical episode for episode, the official sample's
  plan equal pose for pose), so the form *is* safe to ship blind on the
  sample's kind of manifest; it just has nothing to give elsewhere.
  Arm `arm_amix_a.txt`; the flags stay off.
- **`plan_count_secure_fill_first` as specified** (the dense tokens
  skipped under 0.85 of the threshold): huge-a **-1.77 [-2.53, -1.08]**,
  the fill 39.0 -> 33.4 (-5.7: the dense plans carry the volume there
  too, 33 of 36 picks), for the optimize 49.6 -> 25.9 s (max 139.6 ->
  69.8, every scene under 100 s); dense-a -27.31 (22 crossings lost),
  core-a -0.05.  **Not kept.**  With the dense tokens kept
  (`arm_afillk_a`): huge-a +0.01, dense-a and core-a identical --
  harmless, worthless.
- **What the huge suite says about the platform's uncounted A
  episodes**: at 100-160 items in a scaled container the best plans
  hold 23-64 of the 51-81 asked and the fill is 20-58 (mean 39); the
  v59 optimize runs to its 140 s budget on 6 of 36 scenes here (the
  130-160-item ones), 1.4x that on the platform, so the plans there are
  cut.  A time lever that keeps the dense plans' fill is still open:
  skipping the strip and the uncapped dense tokens only where the count
  is out of reach (the on-edge plan alone carries most of the fill),
  not measured here.
- **The fixed-number audit** (section 1): of the dense plan's numbers,
  the standing cap and the thin-soft threshold were the sample's and
  are now derivable; the ledge, the strip's rows and the flat layers
  were already the board's and the manifest's; the row-depth table is
  derivable but unused by the A arm; the soft cap 1.6 and the strip's
  one row are not mix numbers.
