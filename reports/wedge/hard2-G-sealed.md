# The hard2 G misses: a level patch left but sealed from the door

Cause G of `hard2-miss-taxonomy.md` (9 v50 C misses, 14 v50 B misses): at the
final decline some visible item has a level spot, but no spot has a clear travel
path from the door. This report follows every G board back to the placement
that sealed each patch, re-runs the agent on the recorded board at those steps
to see what it chose among and why, branches the episode there with other moves,
and measures sealing on every hard2 episode, misses and crossings alike.

Scripts and compact outputs are in `reports/wedge/hard2-G-sealed/`
(`sealkit.py`, `trace.py`, `census.py`, `why.py`, `branch.py`, `cf.py`,
`make_plan.py`, `validate_sim.py`, `render.py`, `tables.py`; `tables.md` holds
every table, `data/tables.json` the rows). Heavy per-step output stayed in
`/home/user/inv-G-scratch` and can be regenerated.

Records read: `gate0-hard2` (v50 C), `gate0-hard2-b` (v50 B), and for the
robustness checks `gate0det-hard2` and `gate0-hard2-b-r2`. Boards are rebuilt
from `final_items` as in the taxonomy (settled poses, container offset from
`pos_local`).

PLACEHOLDER-SUMMARY

## 1. The reach model, checked against the official validator

The taxonomy's "reachable" is a 2 cm cell model of the simulator's path. It
was re-implemented here exactly, on boxes (`sealkit.exact_blockers`), from
`simulator/src/ground_handling/validator.py:85-175`:

- the y-leg from `(clamp(x), -W/2, z_t)` to the target depth, then the x-leg;
  `x` is clamped to `[-L/2+T+cut_x+hx+0.01, L/2-T-hx-0.01]`;
- `z_t` is the commanded centre plus the lift: 0.08 m, 0 when the commanded
  bottom is 0-5 cm over the floor or the mid-height level, clipped under the
  two ceiling surfaces when the clearance is under lift + 0.018, capped under
  the roof;
- the commanded pose is the agent's (`agent/agent.py:586-602`: floor +0.020,
  shelf +0.051, and the v49 band escape +0.003 over the band);
- blocked when a packed box (or the big shelf of a `require_shelf` container)
  comes within `safety_margin` 0.015 m (`validator.py:229-260`; the small
  shelf over the chamfer and the walls are not checked by the validator).

Results:

- **Exact against cells.** At the final decline the two models agree on
  whether some visible item has a reachable spot in 92 of 94 C and 94 of 96 B
  episodes that end with visible items (`tables.md`, end states). All 23 G labels stand under the exact
  model (0 reachable spots for every visible item). In `gate0det-hard2`
  c-hard2-s0059 the cells see 7 reachable spots where the exact check sees
  none.
- **One defect in the taxonomy's model, without effect here:** it carries a
  box over a shelf at bottom +0.02 m. The agent commands a shelf pose 5.1 cm
  up, so the simulator lifts it 8 cm more (bottom +0.131 m). No G
  label changes.
- **Official validator** (`validate_sim.py`: the record's actions replayed in
  the official environment, then `check_inclusion` and
  `check_transport_path` on sampled spots of each sealed patch, before and
  after its sealing placement and at the end).
  The replays reproduce the settled poses to 0.2-3 cm (14 cm on b-s0030).
  Five replays fail late (c-s0070 at step 6, c-s0081 49, b-s0055 18, b-s0073
  89, b-s0075 81), and their later checks are missing.

  | spots the trace says this sealer closed                    | official verdict                     |
  | ---------------------------------------------------------- | ------------------------------------ |
  | before the sealer                                          | 462 pass the sweep, 14 refused (3 %) |
  | after the sealer                                           | 476 of 476 refused                   |
  | at the end, every sampled sealed spot                      | 427 of 427 refused                   |
  | spots closed by an earlier placement, at the sealer's step | 124 of 125 refused                   |

  The sealing placement found from the rebuilt board is the one the official
  validator sees closing the path.

## 2. When and by what the patches were sealed

`trace.py` keys every level-but-sealed spot of the end board by container,
orientation, support level and window origin. For each spot it finds the
prefix at which the spot became level (`t_L`) and the earliest placement that
blocks its path (`t_S`; the path only loses clearance as boxes are added, so
this is exact for the rebuilt board). Spots group into patches (container,
support level). A patch is _sealed after open_ when some spot was level and
reachable for at least one prefix. Its sealing placement is the one that
closed the last open spot.

Per patch (`tables.md`, "The sealed patches"; 15 C patches in 9 episodes, 36 B
patches in 14):

- **All but one were open first** (C 15 of 15, B 35 of 36). For a median of
  13 placements (C 2-44, B 1-83) a box of the visible item's size could have
  been carried to them.
- **The seal comes early.**
  - Median lead from the seal to the end: 13 placements on C, 23.5 on B.
  - On the near misses: c-s0059 31, c-s0027 7-20, c-s0013 2 and 6, b-s0007 5
    and 8, b-s0009 23 and 32, b-s0077 17, b-s0026 10, b-s0064 2.
- **Two geometries:**

|                                                                         | C patches | B patches |
| ----------------------------------------------------------------------- | --------: | --------: |
| floor patch behind a floor box (fill order along the depth axis)        |         7 |        12 |
| raised patch (tops at 0.2-1.6 m) behind a box stacked on the front rows |         5 |        22 |
| raised patch behind a tall floor box                                    |         3 |         2 |

- **The sealer.**
  - Its door-side face is a median 0.18 m (C) and 0.20 m (B) from the door
    edge. It is within 0.15 m in 6 of 15 C and 13 of 36 B patches.
  - It stands on end in 6 of 15 C and 8 of 36 B patches.
  - It is soft in 3 C and 6 B patches, priority in 2 and 2.
  - The big shelf never blocked a path.
  - 6 B patches (b-s0004, s0007, s0026, s0030, s0071, s0073) have some spots
    in the chamfer pocket (reached by the x-leg). None is a pocket-only
    patch.
- **Sealing rungs:**
  - C: physics-resort 3, max-footprint 3, grid-rescue 2, and one each of
    front-wedge, wall-front, fallback, stack-rl, soft-edge, terrace-extension
    and wedge-step.
  - B: terrace-extension 14, max-footprint 6, soft-edge 4, wedge-step 3,
    hole-fill 2, stack-rl 2, and one each of priority-edge, pocket-soft,
    shelf-space-saving, wall-front and front-wedge.
- **Some patches are slots, not patches.**
  - c-s0059 (margin -1) ends with a single sealed patch of 2 window origins:
    the item fits with 2-4 cm of play.
  - c-s0013 has 6 and 5, b-s0071 7.
  - Calling these boards "a patch was left" overstates what was left.

On the B G misses the visible pool at the end is soft-heavy: a median soft
share of 0.8, against 0.4 in the B crossings and 0.33 in the other B misses.
The oldest pool item was revealed a median 15 placements before the end. B's
pool order puts every hard item before every soft one (`layer1.pool_order`,
`rule_alpha/layer1.py:4931`). So on B, G is the board on which the deferred
soft boxes are finally tried, and their only level spots lie behind the front
stacks that the hard boxes built.

## 3. Why these moves (decision archaeology)

`why.py` loads the recorded board before each sealing placement into the
agent, with the record's arm and `deterministic_budgets=true`, the shadow
running in pybullet. It instruments the call (`branch.instrument`: every
ladder decision with its rungs, candidates, rung keys and vetoes, every pose
put to the shadow, and the stages entered). The shipped code is untouched.

- **Fidelity.** 36 of the 50 re-run sealing decisions pick the recorded pose
  to 3 cm (`same` in `tables.md`). Of the other 14:
  - 6 keep the recorded rung but at another pose. The rebuilt board holds
    the settled end poses, not the poses the agent saw at the time.
  - 8 change stage, mostly where the record used a rescue stage (physics
    resort, grid rescue), which keeps its own clock.
  - On the near misses' last steps the re-run declines twice where the
    record's physics resort placed after 4.8-4.9 s (b-hard2-s0007 t17, t18).
- **Robust across runs.** 17 of the 23 G scenes share at least one sealing
  placement (same step, same rung) with the replicate record
  (`gate0det-hard2`, `gate0-hard2-b-r2`). 21 of 23 end level-but-sealed
  there too.

The chain repeats with small variations:

1. **The item has few candidates, and every one of them seals.**
   - At 32 of the 48 sealing steps where the ladder decided the placed item,
     none of its listed candidates (up to 12 per rung, 4 rungs) leaves the
     patch reachable.
   - In 25 of the 38 patch rows behind those 32 steps, the item had 1-3
     survivors.
   - The vetoes before the survivors are mostly unrelated to sealing:
     `overhangs-the-shelf`, `reserved-zone`, `corridor`, `wall-front-strip`,
     `no-plateau-to-build-on`, `free-standing-tipping-risk`.
2. **The sealing guards fire and fall back.**
   - The ladder's own seal veto drops floor candidates whose `sealed_added`
     exceeds 0.3 m² (`layer1.py:3683-3685`). If that would leave nothing,
     all candidates are kept (`layer1.py:3688-3689`).
   - Examples: c-s0013 t5 (the chosen pose read 0.43 m²), b-s0007 t12 (0.55),
     b-s0086 t52 (0.62), c-s0027 t18 (0.53, then refused by the shadow).
   - `would-wall-off-the-back` (`layer1.py:4072-4089`) is a preference with
     the same fallback. It exempts wall-front, wedge-step, slope-infill and
     front-wedge.
3. **The ladder's keys do not price the seal of a raised patch.**
   - `sealed_added` is computed for floor candidates only, unless
     `seal_check_all_surfaces` is set (`layer1.py:2105`; off in the shipped
     form).
   - So the terrace key's third term (`_key_terrace`, `layer1.py:2393`) is 0
     for every terrace candidate.
   - terrace-extension is B's main sealer (14 of 36 patches). It ranks
     plateau size first, which favours the long front rows.
4. **Door-side poses are on purpose in several rungs.**
   - `front-wedge` ranks by top height, then footprint, then depth: "start
     from the back of the band so the descent runs door-ward"
     (`layer1.py:2437`).
   - `soft-edge` and `priority-edge` rank the right-front corner first
     (`layer1.py:2323-2338`).
   - `max-footprint` ranks footprint before depth (`layer1.py:2259`). A
     larger footprint at the door beats a smaller one at the back unless the
     back-first rule's "good" set holds a deeper floor pose.
5. **The rescue stages place low first.**
   - The physics resort orders by cover class, then (under the count pass)
     partial support last, then shade bucket, then bottom height
     (`agent.py:2296-2321`).
   - c-s0027 t18: the ladder's hole-fill (shade 0.46 m²) and the stack
     option's pose (0.37) were shade-vetoed. The physics resort then placed
     a standing 0.45 x 0.25 x 0.65 box at the door (shade 0.30, bottom on
     the floor). It sealed the 966-origin patch at 0.29 m.
   - A pose on that patch (bottom 0.28 m, shade 0.0) existed and stood: the
     count pass placed it in the fill counterfactual (section 4). The strict
     resort accepted the door pose first, so the count pass did not run.
6. **On B the pool is not used to choose.**
   - At every B sealing step the ladder ran for exactly one item: the first
     pool item in `pool_order` (hard before priority before soft, smallest
     footprint first, `count_first`) that got a pose.
   - The agent emitted that pose. No other pool item was compared.
   - `pool_item_search` is off in the shipped form.

**Did the agent's own transport model know?** The census (section 5) reads,
for every sealing placement, the two measures the agent has:

- `shade_area`: the C shade veto and the resort order.
- `sealed_added`: the ladder's reach reading at the probe heights. It was
  computed here for every placement, which is more than the ladder does.

| record | sealing events | shade > 0.15 (C veto would fire) | shade > 0 | sealed_added > 0.3 (floor veto would fire) | sealed_added > 0 | true sealed (median, m² of windows) | shade (median) | sealed_added (median) |
| ------ | -------------: | -------------------------------: | --------: | -----------------------------------------: | ---------------: | ----------------------------------: | -------------: | --------------------: |
| C v50  |           1161 |                               59 |       599 |                                         24 |              577 |                                0.40 |           0.01 |                  0.00 |
| B v50  |           1265 |                              190 |       652 |                                         62 |              602 |                                0.41 |           0.01 |                  0.00 |

- **The two measures are mostly blind.**
  - 44 % (C) and 46 % (B) of the sealing placements read 0 on both.
  - 6 % (C) and 15 % (B) would trip either veto. On C the shade veto has
    already removed the poses it sees, so C's share is lower by
    construction.
- **Both measures are per-cell column readings.** A cell counts as sealed when
  something in front of it in its own column stands higher. The simulator
  needs a corridor as wide as the carried box.
- **Width is not the main gap.** Of the spots the G sealers closed, 85 %
  have their centre inside the sealer's own x-range.
- **What the readings miss:**
  - `sealed_added` is read at the fixed probe heights 0-1.0 m on the
    ladder's grid.
  - `shade_area` counts only terrain lower than the box top less 2 cm, with
    0.2 m of headroom.
  - Neither asks whether a level spot for a known class lies behind.
- **On B neither measure is used at all.**
  - The record's B arm has `shade_veto_area=0` and `resort_shade_step=0`.
  - The shipped `submission/agent.py` sets 0.15 / 0.1 on every task, but the
    code turns both off with a pool (`agent.py:624`, `agent.py:2289`).

## 4. Counterfactuals: "if this move had been different"

`cf.py` loads the board after t recorded placements and changes one decision.
The record's arm then continues on the analytic board to its decline, with
the shadow in pybullet and deterministic budgets. Modes (`branch.decide_cf`):

| mode        | the changed decision                                                                                                                                                                                        |
| ----------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `kth` k     | the k-th candidate in the ladder's order (as the selector)                                                                                                                                                  |
| `alt` k     | the k-th distinct pose the agent would emit: the first k-1 refused at `_emit`, so it moves on as after a shadow refusal                                                                                     |
| `noseal2`   | every pose any stage puts to the shadow (ladder, alternatives, physics resort, count pass, grid rescue) is refused if it seals a spot of the patch; one decision, or `persistent` until the patch is filled |
| `fill2`     | the same filter, but only poses that fill the patch pass                                                                                                                                                    |
| `defer` (B) | the decision with the sealing item taken out of the pool                                                                                                                                                    |

`noseal` / `fill` (the selector and `_emit` filter only) miss the rescue
stages, which do not pass through `_emit`. They are kept in `tables.md` but
superseded by `noseal2` / `fill2`.

The `agent` rows are the unchanged continuation, run twice. They give the
noise:

- c-s0059 from t16: 46 or 47 (record 47).
- c-s0027 from t19: 27 or 25.
- b-s0007 from t12: 17 against the record's 20. On this board the analytic
  continuation is 3 short of the physics record.
- b-s0009 from t20: 53 (record 52). The baseline itself reaches the
  threshold.

A branch counts as a rescue only if it reaches the threshold, and the
comparison is against its own baseline.

PLACEHOLDER-CF

## 5. Sealing in general

**Sealing is everywhere, at the same rate.** `census.py` replays every hard2
episode in both records, placement by placement. It counts the spots of the
class 0.55 x 0.40 x 0.24 that a placement seals: level and reachable before
it, still level after it, unreachable after it.

| record | group        | episodes | placements | events (≥ 0.1 m² sealed) | events / placement | sealed m² / placement |
| ------ | ------------ | -------: | ---------: | -----------------------: | -----------------: | --------------------: |
| C v50  | G            |        9 |        391 |                       99 |               0.25 |                  0.10 |
| C v50  | other misses |       44 |       2093 |                      557 |               0.27 |                  0.12 |
| C v50  | crossings    |       43 |       2027 |                      505 |               0.25 |                  0.11 |
| B v50  | G            |       14 |        658 |                      180 |               0.27 |                  0.11 |
| B v50  | other misses |       34 |       1689 |                      493 |               0.29 |                  0.13 |
| B v50  | crossings    |       48 |       2226 |                      592 |               0.27 |                  0.12 |

One placement in four seals something, in the G misses, in the other misses
and in the crossings alike, and on B as on C. The G boards are not sealed
more often. What differs is what is left elsewhere when the next item
arrives.

**The crossings seal before the threshold too.**

| record | group                     | episodes | patches sealed before the threshold placement | at or after it | lead (median) |
| ------ | ------------------------- | -------: | --------------------------------------------: | -------------: | ------------: |
| C v50  | G                         |        9 |                                            15 |              0 |            13 |
| C v50  | crossings that end sealed |        6 |                                            15 |              1 |          43.5 |
| B v50  | G                         |       14 |                                            36 |              0 |          23.5 |
| B v50  | crossings that end sealed |       26 |                                            47 |              7 |          22.5 |

A sealed patch at the end is no sign of a miss: 26 B crossings carry 54 of
them, 47 sealed before the crossing placement.

**Which rungs seal** (events per placement of the rung; `tables.md` has
sealed area too):

- **Floor rungs:**
  - wall-front: C 0.74, B 0.71.
  - max-footprint: C 0.52, B 0.57.
  - pocket-soft: C 0.52, B 0.55.
  - soft-edge: C 0.46, B 0.47.
  - wedge-step: C 0.39, B 0.42.
  - priority-edge: C 0.32, B 0.39.
- **Stacking rungs:**
  - terrace-extension: C 0.15, B 0.15.
  - shelf-space-saving: C 0.16, B 0.18.
  - stack-rl: C 0.16, B 0.08.
- **Rescue stages:**
  - physics-resort: C 0.17, B 0.04.
  - grid-rescue: C 0.09, B 0.10.
  - count-mode: 0.02 and 0.01.
  - grid-rescue-cover: 0.

The floor rungs seal at 3-5 times the rate of the stacking rungs. A floor box
seals the floor behind it whenever that floor is still empty.
terrace-extension seals rarely per placement but is placed often (B: 1205 of
4573 placements), so it is B's largest sealer of G patches.

**Fill order, tall boxes, priority, shelf, pocket:**

- **The depth order** (a floor box set down with empty floor behind it) is
  behind 7 of 15 C and 12 of 36 B G patches.
- **Front stacks rising above the back's tops** are behind 5 C and 22 B
  patches.
- **Tall floor boxes** are behind 3 and 2.
- **Standing sealers:** 6 of 15 C, 8 of 36 B.
- **Priority sealers:** 2 and 2.
- **The big shelf:** 0.
- **The chamfer pocket:** a minority of spots in 6 B patches, never a
  pocket-only patch.
- **Where the sealers stand.** Across all sealing events, the sealer's door
  face is in the front 0.23 m (y_min < -0.35) in 25-36 % of events. Most
  seals come from mid-depth placements.

**Why B ends sealed more often than C.** The taxonomy's contrast (26 of 48 B
crossings end with a level unreachable patch, against 6 of 40 on C) mixes two
things:

| record           | group     | episodes ending with visible items | no reachable spot for any visible item | of those, some level spot |
| ---------------- | --------- | ---------------------------------: | -------------------------------------: | ------------------------: |
| C, next item     | misses    |                                 53 |                                     44 |                 13 (0.30) |
| C, next item     | crossings |                                 41 |                                     40 |                  6 (0.15) |
| C, next 10 items | misses    |                                 53 |                                     29 |                 14 (0.48) |
| C, next 10 items | crossings |                                 41 |                                     20 |                 12 (0.60) |
| B, pool of 10    | misses    |                                 48 |                                     41 |                 24 (0.59) |
| B, pool of 10    | crossings |                                 48 |                                     48 |                 26 (0.54) |

- **The window.** With one visible item, C counts far fewer level spots.
- **The end condition.** B declines only when no pool item has a pose, so a
  B end board has no reachable spot by construction (48 of 48 crossings).
  Any level spot left on it is sealed.
- **Like for like.** Among boards with no reachable spot for the next 10
  items, about half have a sealed level spot on both tasks: C 0.48-0.60,
  B 0.54-0.59.
- **Per placement**, B seals at C's rate (0.27 against 0.25).
- **B does differ in the policy:**
  - no shade veto and no shade order;
  - a fixed pool order rather than a choice by board effect;
  - soft boxes deferred to the end;
  - terrace-extension as the main sealer.

  That is consistent with B's larger G count, but the per-placement rate does
  not show B sealing more.

## 6. Surprises and evidence against the labels

PLACEHOLDER-SURPRISES

## 7. Open questions

PLACEHOLDER-OPEN

## Scripts (`reports/wedge/hard2-G-sealed/`)

- `sealkit.py`: board rebuild, level spots (the `rule_alpha/surface.py` model),
  and the exact transport check.
- `trace.py`: sealed patches at the end, with `t_L` / `t_S` and the sealer.
  `--all` runs every episode; `VISIBLE=10` widens C's window.
- `census.py`: sealing events per placement, with the agent's own readings.
- `why.py`: the instrumented re-run at the sealing steps (and extra steps).
- `branch.py`: the recorded board as an `EpisodeState`, the instrumentation,
  the counterfactual decisions.
- `cf.py`, `make_plan.py`: the counterfactual queue. The output is a JSONL in
  the scratch directory.
- `validate_sim.py`: the record replayed in the official environment, with
  spot checks by the official validator.
- `render.py`: an ASCII top view of a container after t placements, sealed
  spots marked.
- `tables.py`: `tables.md` and `data/tables.json`.
