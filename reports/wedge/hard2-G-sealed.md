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

## Summary

- **The G label stands, and the sealing step is real.**
  - An exact box model of the official sweep (`validator.py:85-175`) agrees
    with all 23 G labels.
  - In the official validator, the spots a sealer closed pass the sweep
    before it in 462 of 476 checks and fail after it in 476 of 476.
  - 17 of 23 G scenes share a sealing placement (same step, same rung) with
    the replicate record.
- **Sealing is early and was avoidable for a while.**
  - 50 of 51 patches were open first, for a median of 13 placements.
  - The median lead from the seal to the end is 13 placements (C) and 23.5
    (B).
  - Two geometries: a floor patch behind a floor box (the depth order; C 7
    of 15, B 12 of 36), and a raised patch behind a stack on the front rows
    (C 5, B 22; on B mostly terrace-extension).
- **Why the sealing move won (the typical chain).**
  - The item has 1-3 survivors, every one of which seals: at 32 of 48
    ladder-decided sealing steps no listed candidate left the patch open.
  - The seal veto fires but falls back (`layer1.py:3688`).
  - The keys do not price the seal of a raised patch: `sealed_added` is a
    floor-only reading, so terrace candidates score 0 on it.
  - Several rungs put boxes at the door on purpose: front-wedge, soft-edge,
    priority-edge, and max-footprint (footprint before depth).
  - The rescue stages place low first, after the shade veto has refused the
    alternatives.
  - On B the ladder runs for one item only, the first in a fixed pool order.
- **The agent's own transport readings mostly do not see the seal.**
  - On 44-46 % of sealing placements both `shade_area` and `sealed_added`
    read 0.
  - Only 6 % (C) and 15 % (B) would trip either veto.
  - Both are per-cell column readings at fixed heights.  Neither asks
    whether a level spot for a known class lies behind.
- **Counterfactuals on the 8 near misses** (record arm, analytic board,
  controls at every step).
  - No single change in the last 5 placements crosses.
  - Patch-specific rescues, with every control flat:
    - c-s0027: fill the patch at the sealing step, lead 8 (26 -> 34, thr 29);
    - b-s0077: fill it 17-19 placements before the end (20 -> 23, thr 21);
    - b-s0026: 12 before (14 -> 20, thr 16; one control reaches 17).
  - Filling the patch while it is reachable is the strong move.  Sparing it
    for the rest of the episode reaches the threshold only twice (b-s0026 16,
    c-s0027 30), and for one decision never.
  - c-s0013 and b-s0064 do not move under any branch.  c-s0059's patch is a
    2-origin slot, and its outcome is decided between t8 and t16 by
    something else.  b-s0007 and b-s0009 cross under controls or unchanged
    too.
- **Choosing among the pool on B (cause 6).** Every pool item was tried
  first at each sealing step.
  - b-s0007 t12: 6 of 10 items cross.
  - b-s0077 t3: 4 of 10 (best 22, every control 20).
  - b-s0026 t2: 3 of 10 (best 17).
  - None at b-s0007 t15, b-s0026 t4 or b-s0064.
  - The crossing items are almost all soft boxes the fixed order defers.
  - The oldest deferred soft box on the B G boards had a reachable level spot
    from the moment it entered the pool on 12 of 13 boards.  It lost that spot 6-8 placements before the end of the
    short boards.
- **Pricing the seal on every surface (cause 3).**
  `seal_check_all_surfaces` from the B terrace sealing steps raises 6 of 9
  boards (+1 to +5), costs b-s0009 4, and crosses none.
  `seal_ranks_terraces` alone barely moves anything.
- **Shade veto -> rescue stage (C).** 3 of 15 C sealing placements came
  through it, and 5 of 15 had the ladder's pose shade-vetoed.  At c-s0027
  t18 a shade-0.0 pose on the patch existed and would have crossed.
- **On the shipped arm** (`arm_ship_*`):
  - Filling holds: c-s0027 t18 (27 -> 29 / 31), b-s0077 t1 (17 -> 21),
    b-s0026 t2 (14 -> 22).
  - b-s0077 t3 and the persistent protections do not hold.
  - Of the pool-choice rescues only b-s0007 t12 holds (18 -> 21).
  - The shipped records (`ship-hard2*`) miss 22 of the 23 G scenes, with the
    same sealing placements.
- **Sealing is not specific to G.**
  - One placement in four seals level surface, in G, in the other misses and
    in the crossings alike (C 0.25-0.27, B 0.27-0.29 events a placement).
  - The crossings that end sealed sealed their patches before the threshold
    too.
  - The floor rungs seal two to five times as often per placement as the stacking
    rungs and the rescue stages.
- **B is not more prone per placement.**
  - The 26-of-48 against 6-of-40 contrast is mostly the end condition (B
    declines only when no pool item has a pose) and the window (10 items
    against 1).
  - Like for like, about half the boards without a reachable spot hold a
    sealed level spot on both tasks.
  - What does differ on B is the policy:
    - no shade veto or shade order (`agent.py:624`, `2289`);
    - a fixed pool order, hard before soft;
    - so its G boards end with soft-heavy pools (median 0.8 soft, against
      0.4 in the crossings), whose spots lie behind the front stacks.
- **Two surprises about the inputs:**
  - The bench's B records run `rescue_order_gate=low`, where the shipped B
    form runs `low+single` (the rescue sealing pass is off on B in the
    submission).
  - The taxonomy's reach model carries shelf boxes 11 cm too low.  It
    changes no label.

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

`tables.md` ("Counterfactual summary") has every branch, and the rows
are in `data/tables.json`.  Condensed (placed at the end; threshold in
brackets; controls are the ladder ranks 2-3 and the 2nd-3rd distinct poses):

| scene (thr) | last 5 steps: 2nd pose | sealing step: agent / controls / `noseal2` / `fill2` / `defer` | earlier step: agent / controls / `fill2` | patch-specific rescue |
|---|---|---|---|---|
| c-s0059 (48) | 47 at t42-46 | t16: 46,47 / 46 / 46 / 46 / - | t8: 51 / 49, 51, 54, 54 / 53 | no.  From t16 nothing crosses.  From t8 the unchanged continuation crosses itself (51), so the miss is decided between t8 and t16 by something other than this 2-origin slot |
| c-s0027 (29) | 26 at t21-25 | t18: 26, 26 / 26-27 (5) / 27, 28 / **34, 34** / - | t12: 38 / 27, 38, 27, 38 / 36; t6: 27 / 37, 21, 27, 27 / 38; t3: 27 / 39, 35, 38, 27 / 39 | **yes at t18 (lead 8)**: filling the 966-origin patch at 0.29 m crosses by +5 where every control stays at 26-27.  Before t16 the board is chaotic: the unchanged continuation from t12 reaches 38 |
| c-s0013 (11) | 6-7 | t5: 7 / 7 (4) / 7 / 7; t1: 7 / 7, 10, 10, 7 / 7 / 7 | t0: 7 / 10, 7, 5, 10 / 5 | no.  Nothing crosses; the best of any branch is 10 |
| b-s0007 (21) | 18-20 | t15: 17, 17 / 17, 20, **22**, 18 / 20 / **21** / **21**; t12: 17, 17 / 18, **21**, **21**, 18 / **21** / 20 / **21** | t14: 18 / 20, 18, **21**, 18 / 21 | no: crossings at t12-t15, but controls cross too.  The analytic baseline is 3 under the record (17 against 20) |
| b-s0009 (53) | 52 | t29: 52, 52 / - / 53 / 53; t20: **53, 53** / - / 54 / 54 | t14: - / - / 49 | no: the unchanged continuation from t20 already crosses (53) |
| b-s0077 (21) | 20 | t3: 20, 20 / 20 (4) / 20 / **23** | t1: 20 / 20 (4) / **23** | **yes at t1-t3 (lead 17-19)**: filling the back floor patch (a soft-priority 0.3 x 0.6 x 0.25 at y 0.37 at t3, a 0.8 x 0.6 x 0.5 at t1) gives 23 against 20 in all 11 other branches |
| b-s0026 (16) | 14 | t4: 14, 14 / 14, 15, 15, 14 / 15 / 15 | t2: 14 / 14, 14, 17, 14 / **20** | **mostly, at t2 (lead 12)**: filling gives 20; one control of four reaches 17 |
| b-s0064 (30) | 25-26 | t24: 26, 26 / 26 (4) / 26 / 26 / 26 | t21: 26 / 26 (4) / 26 | no.  Nothing moves the count |

**Persistent protection.** `noseal2` held from the sealing step until the
patch is filled:

- **Crosses on two boards, each time with flat controls:**
  - b-s0026 from t4: 16, at the threshold.  The baseline is 14/14 and the
    controls 14-15.
  - c-s0027 from t18, protecting patch 3: 30.  The baseline is 26/26 and the
    controls 26-27.  Protecting patch 0 instead gives 26.
- **Crosses on boards where the controls cross too:**
  - c-s0027 t6 40, t12 38.
  - b-s0007 t10 21.
- **Does not cross:**
  - c-s0059 47 (t16) and 47 (t8).
  - c-s0013 7, 10 and 7 (t5, t2, t0); a control at t2 also gives 10.
  - b-s0007 20 (t15, t14), 21 (t12).
  - b-s0077 20 (t3) and 19 (t1).
  - b-s0064 26 (t24, t21).

Sparing a patch for the rest of the episode is weaker than filling it, but it
is not empty: it can be worth one or two items.

What the branches say:

- **How far back.** No single change in the last five placements crosses on
  any near miss.  The 2nd pose at t-1 ... t-5 lands within one item of the
  baseline everywhere.  The earliest step at which a patch-specific change
  crosses is 8 placements before the end (c-s0027), 12 (b-s0026) and 17-19
  (b-s0077).
- **What rescues: filling, not sparing.** In the three patch-specific
  rescues the winning branch puts the current item on the patch while it is
  still reachable:
  - c-s0027 t18: the count pass stands a 0.25 x 0.45 x 0.65 box on the
    0.29 m patch (shade 0.0) instead of the resort's door pose.
  - b-s0077 t1 / t3: a box on the back floor instead of a 0.8 x 0.5 x 0.6
    max-footprint at the door.
  - b-s0026 t2: a 0.45 x 0.65 x 0.25 on the back floor.

  Barring the seal for one decision (`noseal2`) gives +0 to +2 and crosses
  nowhere on its own.  The agent's next pose seals the patch, or the patch
  stays empty and unreachable later.  Barring it for the rest of the episode
  reaches the threshold on b-s0026 (16) and c-s0027 (30, patch 3) only.
- **Would filling the sealed patch first have crossed?** Yes on c-s0027
  (+5), b-s0077 (+2) and b-s0026 (+4 at t2, +0 at t4).  No on c-s0013,
  b-s0064 and c-s0059 (the slot).  b-s0007 and b-s0009 cannot be read: their
  controls or baselines cross too.
- **Noise.** On several boards the outcome swings by up to 12 items after one
  early change: c-s0027 from t3-t12 gives 21 to 39 over branches whose first
  move has nothing to do with the patch.  Single-branch gains early in an
  episode are not evidence about the patch unless the controls stay flat, as
  they do on b-s0077 and c-s0027 t18.

### Choosing among the pool on B (cause 6)

At each B near-miss sealing step, and at the earlier steps where filling
rescued, every pool item was tried first.  The `first_item` mode moves it to
the front of `pool_order` for that one decision.  If it gets no pose, the
agent goes on as usual.  Each branch was rolled out to the end
(`tables.md`, "Choosing among the pool").

| scene (thr) | step | agent | items tried | items that cross | best | which items cross |
|---|---|---:|---:|---:|---:|---|
| b-s0007 (21) | t12 (seal) | 17, 17 | 10 | 6 | 21 | every soft item that got a pose (soft-edge, 0.65 x 0.35 x 0.23 flat on the floor where the hard 0.65 x 0.25 x 0.45 stood) |
| b-s0007 (21) | t15 (seal) | 17, 17 | 10 | 0 | 18 | none: the soft items get no pose, and the terrace item is placed regardless |
| b-s0077 (21) | t3 (seal) | 20, 20 | 10 | 4 | 22 | soft 3 and 7 (22), soft 1 (21), priority 9 (21) |
| b-s0077 (21) | t1 | 20 | 10 | 1 | 21 | soft 1 |
| b-s0026 (16) | t2 | 14 | 10 | 3 | 17 | priority-hard 4 (17), soft 1 and soft-priority 6 (16) |
| b-s0026 (16) | t4 (seal) | 14, 14 | 10 | 0 | 15 | none; 9 of 10 give 15 |
| b-s0064 (30) | t24 (seal) | 26, 26 | 7 | 0 | 26 | none |
| b-s0009 (53) | t20 (seal) | 53, 53 | 11 | 11 | 54 | all (the baseline crosses too) |

- **The pool choice rescues three of the five readable B near misses**
  (b-s0007, b-s0077, b-s0026).  At b-s0077 t3 the 8 controls and the 3
  baseline repeats all stay at 20, while two pool choices give 22.
- **The rescuing choice is almost always a soft box placed early.**
  - The agent's fixed order (hard, then priority, then soft, smallest
    footprint first) would have reached that box only after the board
    closed.
  - At b-s0007 t12 the soft box goes on the floor at the door like the hard
    box it replaces, but 0.23 m tall instead of 0.45.  So the rescue is not
    always "keep the patch reachable".  It can be "put the low box there".
- **The step matters.** At the second sealing step of b-s0007 (t15) and at
  b-s0026 t4 no pool choice crosses.  The choice has to be made one to three
  placements before the seal, while the soft box still has a pose.

### The soft deferral on B

For the oldest soft box still in the pool at the end of each B G board,
`softtime.py` records every prefix from the step it entered the pool (exact
sweep; soft support up to 0.7 m allowed).

- **12 of 13 boards had a reachable level spot for it.** In the near misses
  it had one from the moment it entered the pool:
  - b-s0007 prefixes 0-12, b-s0077 0-10, b-s0026 0-8, b-s0055 0-12,
    b-s0004 0-11, b-s0064 10-20;
  - b-s0009 0-49, b-s0075 0-58, b-s0086 29-63.
- **The agent kept trying hard items first** until those spots were sealed.
  The last reachable spot disappeared 6-8 placements before the end on the
  short boards.
- **Exception:** b-s0056's last soft box never had one.
- **Interleaving from the start.** The whole episode was re-run with soft
  boxes interleaved: `soft_first_when_free`, and a pool order with soft in
  the hard bucket (`soft_equal`).  PLACEHOLDER-SOFT

### Pricing the seal on every surface (cause 3)

The record arm, with `seal_check_all_surfaces` and/or `seal_ranks_terraces`
appended from the B terrace-extension sealing step to the end of the
episode:

| scene (thr) | t | agent | seal_check_all_surfaces | seal_ranks_terraces | both |
|---|---:|---:|---:|---:|---:|
| b-s0007 (21) | 15 | 17, 17 | 18 | 18 | 18 |
| b-s0009 (53) | 20 | 53, 53 | 49 | 52 | 49 |
| b-s0055 (30) | 10 | 18 | 22 | 18 | 22 |
| b-s0056 (76) | 47 | 66 | 66 | 66 | 66 |
| b-s0081 (62) | 36 | 44 | 49 | 44 | 49 |
| b-s0081 (62) | 45 | 46 | 46 | 46 | 46 |
| b-s0030 (79) | 53 | 62 | 65 | 65 | 65 |
| b-s0073 (105) | 78 | 86 | 87 | 87 | 87 |
| b-s0075 (109) | 58 | 78 | 78 | 78 | 78 |

- **`seal_check_all_surfaces` raises 6 of 9 boards and crosses on none:**
  - b-s0081 t36 +5, b-s0055 +4, b-s0030 +3, b-s0007 +1, b-s0073 +1;
  - b-s0009 -4, the one board whose baseline crosses;
  - b-s0056, b-s0075 and b-s0081 t45 unchanged.
- **`seal_ranks_terraces` alone:** b-s0030 +3, b-s0073 +1, b-s0009 -1, the
  rest unchanged.
- **Noise.** The baselines here are single runs on most boards, and the
  noise elsewhere is ±1-2.  Only the +3 to +5 moves stand out.
- **Reading.** The cheap fix prices a real effect.  The veto keeps its
  fallback, buys a few items on long boards, costs four on b-s0009, and
  rescues none of these.

### The shade veto handing the seal to a rescue stage (C)

On C, `shadepath.py` takes every G sealing step.  It finds the poses the
re-run's shadow refused, recomputes their `shade_area`, and checks whether a
rescue stage then placed:

- **3 of 15 C sealing placements came through this path:**
  - c-s0027 t18: hole-fill 0.46 and stack-rl 0.37 refused, then the physics
    resort.
  - c-s0027 t19: terrace-extension 0.49 and stack-rl 0.27 refused, then the
    physics resort in the record (the grid rescue in the re-run).
  - c-s0087 t13: terrace-extension 0.21 and stack-rl 0.25 refused, then the
    physics resort.
- **Two more come close:**
  - c-s0060 t65: the ladder's terrace pose (0.86) and stack-rl (0.27) were
    refused; the record's pose came from the grid rescue.
  - c-s0063 t14: the ladder's pocket-soft pose (0.38) was refused and the
    stack option placed.

  With these, the ladder's own pose was shade-vetoed at 5 of 15 C sealing
  steps.
- **6 of the 15 C sealing placements were made by a rescue stage** in the
  record.
- On c-s0027 t18 the counterfactual shows what the path cost: a shade-0.0
  pose on the patch existed, and placing it gives 34 against 26.

### The rescues on the shipped arm

The record arms differ from the shipped form (section 6).  Every branch that
reached the threshold on the record arm was re-run with `arm_ship_c` /
`arm_ship_b` (`origin/claude/rl-packing-policy-ftogt3` 9e4ada85,
`reports/bench/arms/`), together with the unchanged continuation at the same
step (`tables.md`, "The rescuing branches on the shipped arm").

The patch-specific and pool-choice rescues:

| rescue | record arm: baseline -> branch | shipped arm: baseline -> branch | holds on the shipped arm |
|---|---|---|---|
| c-s0027 t18, fill patch 0 / patch 3 | 26 -> 34 / 34 | 27 -> 29 / 31 (thr 29) | **yes** (+2 / +4) |
| c-s0027 t18, protect patch 3 (persistent) | 26 -> 30 | 27 -> 28 | no |
| b-s0077 t3, fill | 20 -> 23 | 18 -> 18 | no |
| b-s0077 t1, fill | 20 -> 23 | 17 -> 21 (thr 21) | **yes** (+4) |
| b-s0026 t2, fill | 14 -> 20 | 14 -> 22 (thr 16) | **yes** (+8) |
| b-s0026 t4, protect (persistent) | 14 -> 16 | 14 -> 15 | no |
| b-s0007 t12, a soft item first (6 items) | 17 -> 21 (6 of 6) | 18 -> 21 (4 of 6), 20 (2) | **yes** |
| b-s0077 t3, soft 3 / soft 7 / soft 1 / priority 9 first | 20 -> 22 / 22 / 21 / 21 | 18 -> 13 / 13 / 17 / 17 | no |
| b-s0077 t1, soft 1 first | 20 -> 21 | 17 -> 17 | no |
| b-s0026 t2, items 1 / 4 / 6 first | 14 -> 16 / 17 / 16 | 14 -> 15 / 14 / 15 | no |

- **Filling the patch holds** on the shipped arm on c-s0027, b-s0077 (from
  t1) and b-s0026.
- **The pool-choice rescues hold only on b-s0007.**
- **Branches that crossed on chaotic boards keep crossing,** together with
  their controls: c-s0027 t3-t12, c-s0059 t8 (the shipped baseline from t8
  gives 48 and 53), b-s0007 t10-t15 (fill, defer, protect and the 3rd pose
  all reach 21-22).
- **b-s0009's baseline still crosses from t20** on the shipped arm (54).
  Its fill / protect at t29 does not (52).

**The shipped records** (`ship-hard2`, `ship-hard2-b`, CI, landed on that
branch after the arms):

- 22 of the 23 G scenes still miss.  Only c-s0059 crosses on shipped C (+2).
- The shipped B form crosses 44 of 96 hard2 B against the record arm's 48.
  `shipseal-hard2-b` (the shipped B form with the sealing pass on B) gets 47.
- On the shipped boards the same scenes end level-but-sealed: 20 of the 22
  that miss.  The exceptions are c-s0070 (reachable) and b-s0075 (no level
  spot).
- The sealing placements recur at the same steps, by the same rungs:
  b-s0007 t12 / t15, b-s0009 t29 / t20, b-s0077 t3, b-s0026 t4, b-s0064 t24,
  b-s0004 t11, b-s0055 t10, b-s0056 t22, c-s0027 t18, c-s0013 t5, c-s0063
  t14, c-s0055 t6, c-s0081 t42, c-s0087 t13 (`trace.py` on the shipped
  records).
- So the archaeology describes the shipped form too.

### Control: the same fill on crossing boards

One changed move near the threshold is close to a coin toss.  The H
investigation's control (crossing boards at margin 0 to +2, one move
changed) dropped 27 % of its branches below the threshold, against a 14 %
rescue rate, with a mean change of about 0.  So the fill was applied the
same way to crossing boards.  The boards are the 8 hard2 B crossings at
margin 0 to +2 that end with a patch sealed after open, 5-20 placements
before the end.  The branch is `fill2` at the sealing step of the largest
patch, against the unchanged continuation at that step.

| scene (thr) | t (lead) | record | agent | fill2 | fill applied |
|---|---|---:|---:|---:|---|
| b-s0013 (11) | 6 (7) | 13 | 13 | 15 | yes |
| b-s0015 (15) | 10 (7) | 17 | 17 | 16 | yes |
| b-s0032 (13) | 10 (5) | 15 | 14 | 15 | yes |
| b-s0051 (24) | 7 (19) | 26 | 24 | 25 | yes |
| b-s0058 (37) | 22 (17) | 39 | 37 | 38 | yes |
| b-s0059 (48) | 35 (13) | 48 | 43 | 45 | no pose filled it (fell back) |
| b-s0076 (22) | 14 (10) | 24 | 21 | 21 | no pose filled it |
| b-s0087 (45) | 42 (5) | 47 | 48 | 48 | no pose filled it |

- **Where the fill was applied it broke no crossing,** 0 of 5.  The changes
  were +2, -1, +1, +1 and +1 (mean +0.8).
- **The sample is small.** Two of the analytic baselines (b-s0059, b-s0076)
  already fall below the threshold on the analytic board.
- So the fill does not behave like a random move here.
- The near-miss rescues still rest on their own controls (flat at c-s0027
  t18 and b-s0077), not on a large sample.  With 3 rescues from 8 boards, a
  coin-toss reading cannot be excluded for b-s0026, where one control
  reached 17.
- C has no crossing at margin 0 to +2 that ends sealed within that lead, so
  the control is B-only.

PLACEHOLDER-OTHERS

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

The floor rungs seal at two to five times the rate of the stacking rungs (max-footprint 0.52-0.57 against terrace-extension 0.15). A floor box
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

- **G is an end state, not a separate failure.**
  - Sealing placements are as frequent in the crossings and in the other
    misses as in G (section 5).
  - The crossings that end sealed sealed their patches before the threshold
    placement too.
  - What makes a board G is that the next item (C), or every deferred item
    (B), happens to need the one class of surface that lies behind the
    front.
  - A per-episode "sealed" flag therefore cannot separate misses from
    crossings, and the counterfactuals must be read against their own
    baselines.
- **The B/C contrast is mostly the end condition.**
  - B declines only when no pool item has a pose, so its end boards have no
    reachable spot by construction.
  - C is scored on one item.
  - With the same 10-item window, about half of the boards without a
    reachable spot hold a sealed level spot, on both tasks (section 5).
- **Some G patches are slots.** c-s0059 (margin -1) has a single sealed
  "patch" of 2 window origins, c-s0013 6 and 5.  The level check's 3 cm
  clearance makes these real but marginal targets.
- **The rung of the largest usable-surface drop is not the sealing rung.**
  - The taxonomy's "largest drop" rung is mostly max-footprint.
  - The sealers are spread across rungs on C (rescue stages 5 of 15).
  - On B they are mostly terrace-extension (14 of 36).
- **The high priority floor share** (0.18 in C's G group) does not come from
  priority sealers: only 2 C patches (c-s0013 t1, c-s0070 t43) and 2 B
  patches were sealed by a priority box.
- **The shade veto can hand the seal to the rescue.** c-s0027 t18:
  - The veto refused the ladder's door-side hole-fill (shade 0.46) and the
    stack option's pose (0.37).  The stack option's pose would have kept the
    966-origin patch reachable.
  - The physics resort then sealed the patch with a 0.30-shade door pose.
  - The veto prices the floor area behind a pose in its own columns.  It
    does not see which surfaces a known item could use, so a pose that keeps
    a large patch reachable and one that seals it read about the same.
- **The bench's B arm is not the shipped B form.** The record's B arm differs
  from `submission/agent.py` at this branch's HEAD in:
  - `rescue_order_gate` `low` against `low+single`: the records run the
    rescue's deep-first order and sealing pass in B's low phase, and the
    submission does not;
  - `stack_deadline` false against true;
  - `soft_headroom_volume_share` 0.75 against 0.9;
  - `shade_veto_area` and `resort_shade_step` 0 against 0.15 / 0.1, inert on
    B because the code turns them off with a pool;
  - Task A plan fields.

  The C arm differs in the same fields except the shade pair and the gate
  (`low+single` equals `low` with a pool of one).  The counterfactuals here
  use the record's arm, to stay comparable with the records.
- **The taxonomy's reach model** carries a shelf box at bottom +0.02 m
  instead of +0.131 m (the 5.1 cm shelf escape plus the 8 cm lift).  It also
  checks the small chamfer shelf, which the validator does not.  Neither
  changes a label: the exact model and the official validator agree with
  its G labels.
- **The analytic continuation is not the physics episode.** From the same
  recorded board:
  - b-s0007 continues to 17 analytically (twice), against the record's 20.
  - b-s0009 continues to 53, against the record's 52.
  - The gap sits in the rescue stages: the physics resort's clock, and the
    analytic board, which has no settle drift.
  - Counterfactual gains are measured against the analytic baseline.  A
    branch at the threshold on a board whose baseline sits 3 under the
    record (b-s0007) is weaker evidence than its margin suggests.

## 7. Open questions

- **Do the fill and protection gains hold beyond the near misses, and what
  do they cost on the crossings?** Barring every pose that seals a known
  level patch is the kind of change that cost B four crossings as the shade
  veto (core B 48 -> 44, findings "The door-side walls").  Only the near
  misses were branched here.
- **The rescue stages' clock.** The physics resort and the grid rescue keep
  their own deadlines, so near the end the re-run and the record differ (two
  declines at b-s0007 t17-18).  A tail measured under a loaded machine
  understates the record.
- **A pool choice by board effect on B.** At every B sealing step the agent
  tried one item.  Would a choice among the pool items (`pool_item_search`
  with a reading of sealed surface) avoid the B seals without the shade
  veto's losses?  The `defer` branches give the first evidence (section 4).
  This is not measured as a policy.
- **Soft deferral on B.** G's B boards end with soft-heavy pools (median 0.8).
  How much of B's G comes from holding soft boxes until the front is closed,
  rather than from the front itself?
- **A measure that knows the classes.** Both agent readings are per-cell
  columns over fixed heights.  The exact reading ("level spots of the
  stream's classes that a pose makes unreachable") is cheap on the 2 cm grid:
  `census.py` runs it for every placement in about 5 s an episode.  Its value
  as a gate is untested.  No weight was fitted here and none is proposed.

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
