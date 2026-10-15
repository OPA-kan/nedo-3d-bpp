# The hard2 soft carpet (cause D): how it forms, why, and what a different move does

Deep-dive into cause **D** of `hard2-miss-taxonomy.md` (soft footprints cover
≥ 40 % of the floor at the end): the 10 v50 C carpets (`gate0-hard2`) and the 8
v50 B carpets (`gate0-hard2-b`). Every decision of the carpet episodes was replayed
in the official simulator (PyBullet, built locally), on the record's own board,
and the shipped arm was asked what it would do and why. Single moves were then
branched and rolled out to the end. Scripts, compact data and the per-branch
results are in `reports/wedge/hard2-D-carpet/`. Heavy probe output is kept out of
git (`/home/user/inv-D-scratch`).

## Summary

- **Two kinds of carpet.**
  - 7 of the 18 are one-ULD *priority-container* boards. Plain soft cargo is
    barred there from the strict ladder and the stack option
    (`layer1.routing_order`, `wedge_rl/option.py:245`), so every soft box is
    placed by the last resort's relaxed ladder or by the rescues.
  - The other 11 use normal containers. There the strict ladder floors the soft
    boxes and only the pocket guard (181 of 271 probed soft-on-soft decisions),
    the stack option (62) and the rescues (27) put them on soft tops.
  - With the shipped settings **no ladder rung ever offers a soft box a soft top**
    (`layer1._supports`).
- **Most carpets are the soft cargo's own problem.** 11 of the 18 misses decline
  on a soft item. In 8 the stream's first big hard item comes only after the
  threshold, and 6 place no hard item at all. "The floor that the later hard
  items needed" describes 8 of the 18.
- **Why 228 floor-bound soft boxes went to the floor** (record boards, first rule
  that fires):

  | reason | boxes |
  |---|---:|
  | the clock (on the same board the deterministic agent tops them; mainly the pocket guard's 0.8 s window) | 91 |
  | the guard: cross-container comparison | 21 |
  | the guard: tie to the lower pose | 25 |
  | the guard: stood down (its 41-items-a-container prior) | 13 |
  | the guard: margin | 1 |
  | no soft top under the cap (24 of them only on the *shelf's* soft layer) | 29 |
  | no soft top at all | 12 |
  | soft tops legal but outside the guard's generator | 21 |
  | the shadow world vetoed the soft top, the resort floored it | 9 |
  | floor rated better / guard not asked | 6 |

  69 of the 228 are on priority-container boards.
- **The time cut is real but does not explain the carpet.** It is concentrated on
  the multi-container soft-first boards (c-s0036 28 of 31, s0072 14 of 23,
  s0075 13 of 18, b-s0005 15 of 30). But the deterministic record still misses
  s0072 and s0075, and c-s0036 misses deterministically on this machine (−3).
- **Single moves that cross**, confirmed on the shipped arm:
  - c-hard2-s0004: the first floor-bound soft box (k = 3, or k = 5) put on the
    shelf's soft layer at 1.15 m (the cap lifted for that one box): −2 → 0 on
    both arms, against a baseline that reads −2 from all 12 branched steps.
  - c-hard2-s0006: the late floor-bound soft boxes kept on the soft column (k = 20
    and 21, where the shadow world or the tie rule had floored the guard's soft
    top): −1 → 0 and +2 on the record arm; 0 / −1 and +2 / 0 on the shipped arm.
  - c-s0006 is a coin-flip board: the agent's own continuations from neighbouring
    steps read −5 to +1.
- **c-s0004 is decided early, c-s0006 late.** Lifting the cap the same way on
  c-s0006 loses 3-4 items in 4 of 5 branches.
- **Area or shape?**
  - On one ULD it is area: compacting the soft cells into one block still leaves
    0 slots for a 0.65 × 0.45 on 6 of 7 boards.
  - On two or three ULDs the shape halves the slots: 2.4 real against 4.6 compacted.
  - A **realisable** compaction (back-first, flush, through the shadow check) does
    not deliver the bound: crossings 3 → 1 on 15 boards, −1.4 placed a board, no
    slot gain, soft covers −3 to +4. It moves floor-bound boxes but floors no fewer.
- **The v50 gate** starts soft-on-soft earlier on every carpet, but it opens no
  generator. The floor-or-top choice still belongs to the guard, so the floor
  count moves by ±4 and the carpet survives.


## 0. Method, and how far it can be trusted

- **Replay.** `physbranch.py` replays the record's actions (pool index, container,
  orientation, `place_pos`) in the official environment up to step k. It warms the
  agent with the pools it would have seen; the pocket guard's class counts are the
  only part of the agent's state that depends on earlier calls. From k the agent
  plays, or an alternative is forced at k and the agent plays from k+1.
- **Arm.** Branches use the record's arm with `deterministic_budgets=true`, so an
  answer does not depend on this machine's clock. Branches that rescued a board
  were re-run on the shipped form (`arms/arm_ship_c.txt`, `arm_ship_b.txt`, from
  `origin/claude/rl-packing-policy-ftogt3` at 9e4ada85). That form adds
  `stack_deadline`, `rescue_order_gate=low+single`,
  `soft_headroom_volume_share=0.9` and `grid_rescue_pool_seconds=1.5`.
- **The local physics is not the CI's.** Replaying all 33 recorded actions of
  `gate0det-hard2` c-hard2-s0006 moves soft boxes by 0.9 cm on average (9 cm at
  most), and the 33rd action fails the sweep (`physbranch.replay_check`). The full
  deterministic episode here places 32 against the record's 33. It makes the same
  choices up to step 31, then declines where the record placed.
  - Long replays break where a recorded pose no longer fits the drifted board:
    c-s0036 at step 60 of 82, c-s0061 at 61, c-s0075 at 55, b-s0036 at 35.
  - Branches are therefore compared with the agent's own continuation from the
    same board on the same machine (the "baseline at k"), never with the record.
- **Noise floor.** On a near-threshold board the agent's own continuation from
  neighbouring steps of one record spreads widely. On c-s0006 the 18 baselines
  (k = 0..32) range from −5 to +1. On c-s0004 all 12 read −2. A single branch that
  ends one item better than its baseline is not evidence. The tables mark a
  **rescue** only where the branch crosses and its own baseline does not. The text
  relies only on patterns that repeat over several k or several alternatives.
- **Probe** (`instrument.py`, `archaeology.py`). At every step the agent's own
  `policy` runs, with opt-in wrappers around `layer1.choose_for_item`,
  `layer1.apply_vetoes`, the pocket guard's `alternative`, the stack option's
  `propose` and the rescue stages. Nothing in `rule_alpha/` is edited. The probe
  keeps:
  - the ladder's shortlist with its vetoes;
  - the guard's full ranking (slots kept for the expected hard classes, for every
    floor or top pose it generates);
  - a census of the legal soft-top poses with the 0.7 m cap and without it.

  Probes cover all 10 C carpets and 6 of the 8 B carpets. b-s0068 and b-s0043 were
  stopped: the census on their 3-container boards ran past 50 minutes.


## 1. The 18 carpets: two kinds, and most never meet the hard cargo

| scene | order | ctrs (P = priority) | margin | soft placed: floor / on soft / shelf | soft floor share (end) | step soft share passed 0.4 | first big hard item in stream / threshold | hard placed | declined on |
|---|---|---|---:|---|---:|---:|---|---:|---|
| c-hard2-s0006 | small-first | P | -1 | 21: 10 / 4 / 7 | 0.70 | 16 | 24 / 34 | 12 | 0.65x0.45x0.25 |
| c-hard2-s0036 | soft-first | ... | -1 | 82: 34 / 34 / 14 | 0.73 | 36 | 95 / 83 | 0 | soft 0.6x0.3x0.25 |
| c-hard2-s0004 | small-first | P | -2 | 11: 5 / 3 / 3 | 0.44 | 10 | 11 / 22 | 9 | soft 0.5x0.4x0.4 |
| c-hard2-s0053 | random | .P | -7 | 28: 12 / 4 / 10 | 0.49 | 19 | 3 / 47 | 12 | 0.8x0.6x0.5 |
| c-hard2-s0069 | small-first | P | -12 | 20: 10 / 5 / 5 | 0.66 | 14 | 20 / 39 | 7 | 0.55x0.4x0.24 |
| c-hard2-s0072 | soft-first | .. | -17 | 51: 23 / 22 / 6 | 0.68 | 25 | 75 / 68 | 0 | soft 0.6x0.3x0.25 |
| c-hard2-s0049 | small-first | . | -21 | 28: 9 / 7 / 12 | 0.63 | 14 | 34 / 49 | 0 | soft 0.65x0.35x0.23 |
| c-hard2-s0075 | soft-first | .. | -23 | 41: 19 / 7 / 15 | 0.41 | 39 | 42 / 109 | 45 | 0.65x0.45x0.25 |
| c-hard2-s0061 | small-first | .. | -27 | 57: 15 / 23 / 17 | 0.49 | 77 | 162 / 119 | 35 | soft 0.45x0.3x0.2 |
| c-hard2-s0068 | small-first | P | -38 | 20: 10 / 0 / 9 | 0.54 | 39 | 88 / 80 | 22 | soft 0.45x0.3x0.2 |
| b-hard2-s0036 | soft-first | ... | -4 | 79: 31 / 29 / 19 | 0.65 | 39 | 95 / 83 | 0 | soft 0.65x0.35x0.23 |
| b-hard2-s0006 | small-first | P | -9 | 21: 8 / 7 / 6 | 0.70 | 13 | 24 / 34 | 4 | 0.55x0.4x0.24 |
| b-hard2-s0069 | small-first | P | -10 | 20: 7 / 4 / 9 | 0.65 | 12 | 20 / 39 | 9 | 0.55x0.4x0.24 |
| b-hard2-s0005 | soft-first | .P. | -15 | 85: 30 / 29 / 26 | 0.70 | 35 | 87 / 101 | 1 | soft 0.4x0.4x0.6 |
| b-hard2-s0072 | soft-first | .. | -15 | 53: 21 / 20 / 12 | 0.72 | 28 | 75 / 68 | 0 | soft 0.5x0.4x0.4 |
| b-hard2-s0049 | small-first | . | -21 | 28: 10 / 6 / 12 | 0.64 | 15 | 34 / 49 | 0 | soft 0.65x0.35x0.23 |
| b-hard2-s0068 | small-first | P | -25 | 33: 10 / 12 / 9 | 0.54 | 39 | 88 / 80 | 22 | soft 0.6x0.3x0.25 |
| b-hard2-s0043 | small-first | .. | -26 | 40: 20 / 4 / 16 | 0.59 | 42 | 53 / 85 | 19 | 0.55x0.4x0.24 |


Numbers from `course.py` and `d_table.py`, records only.

- **The carpet is not mainly a floor taken from hard items still to come.** 11 of
  the 18 misses end on a *soft* item that finds no pose, not a hard one. In 8 the
  stream's first big hard item comes after the threshold (it would only be met
  after crossing). 6 place no hard item at all. In those the soft cargo runs
  out of room among the soft cargo itself. The taxonomy's lever ("where soft cargo
  goes in the soft-early orders", so the hard items find floor) applies cleanly to
  only 8 episodes: c-s0006, s0004, s0053, s0069, s0075; b-s0006, s0069 and s0043
  are the ones with a hard run before the end.
- **Two kinds of board.** They differ in which code path places the soft cargo:
  - **(P) one priority container**: c-s0004, s0006, s0068, s0069; b-s0006,
    s0068, s0069. 7 of 18, and every one of them is a 1-ULD scene.
    `layer1.routing_order` lets plain soft cargo into a priority container only
    under `routing_any_container` ("soft-only never enters a priority
    container"). So the strict ladder returns nothing for every soft box. The stack
    option checks routing with its own strict config
    (`wedge_rl/option.py:245`), so it returns nothing too, even inside the last
    resort. Every soft box is placed by the last resort's *relaxed* stage
    (`agent.py:_last_resort`, settled clearance 0.016 m) or by the rescues. The
    `soft-edge` and `shelf-space-saving` labels in these records are that relaxed
    stage.
    - On c-s0006 the probe shows `ladder- stack- ladder+ _last_resort+` for every
      soft step 3-21. c-s0006 and s0069 carry no priority item at all (the
      container is reserved for cargo that never comes).
  - **(N) normal containers**: the other 11. The strict ladder places soft cargo
    (shelf, then `soft-edge` on the floor). The pocket guard and the stack option
    are what put it on soft tops.
- **The soft-early orders do not change where a soft box goes. They change what
  the floor holds when it goes there.** Over all v50 C episodes, soft cargo goes
  to the floor, onto soft, onto the shelf and onto hard in these proportions:
  - soft-first: 0.42 / 0.32 / 0.26 / 0.00;
  - small-first: 0.37 / 0.22 / 0.37 / 0.04;
  - soft-last: 0.25 / 0.32 / 0.07 / 0.36;
  - random: 0.34 / 0.16 / 0.30 / 0.20.

  Soft-last puts a third of its soft boxes on hard tops, which do not exist yet in
  a soft-first stream. A soft-early stream lays roughly every second or third soft
  box on an empty floor: 34 of 82 on c-s0036, 10 of 21 on c-s0006.

## 2. How a carpet forms (decision archaeology)

### 2.1 The ladder never offers a soft box a soft top

With the shipped settings (`typed_cap_enabled=False`, `lift_to_tops=0`), the
ladder's Layer 1 generator anchors a soft item on three surfaces only (`layer1._supports`):
- the floor;
- the shelf;
- non-soft, non-priority tops in the wedge strip.

`soft_is_structure` (the v50 gate) changes only what *carries* in the stability
model, not what is generated.

In the probes, 271 soft-on-soft decisions were made by the deterministic agent on
the record boards. None came from a ladder rung:
- `pocket-soft` (the pocket guard's override): 181;
- `stack-rl`: 62;
- `grid-rescue`: 18;
- `physics-resort`: 8;
- count-mode / grid-rescue-cover: 2.

So in this config a soft box reaches a soft top only when the pocket guard
overrides the ladder's floor pose, when the ladder has nothing at all (stack
option), or in a rescue. This is evidence against the findings' "the rungs put soft
on soft once it is structure" (zone form). On these boards with this config the
rungs do not.

### 2.2 The typical sequence (c-hard2-s0006, v50 C, margin −1)

Stream: 3 small hard boxes, 21 soft (5 of 0.45 × 0.30 × 0.20, then 9 of
0.60 × 0.30 × 0.25, then 7 of 0.65 × 0.35 × 0.23), then 9 of 0.55 × 0.40 × 0.24
and the 0.65 × 0.45 × 0.25 class. One priority ULD (no priority cargo), shelf at
0.845 m over the back half of the floor (y 0.05..0.68 of −0.68..0.68).

| steps | what happened (record) | why (deterministic probe on the record board) |
|---|---|---|
| 0-2 | small hard boxes, wall front and wedge steps | strict ladder |
| 3-7 | 5 soft boxes on the shelf | strict ladder empty (priority container), last resort relaxed: `shelf-space-saving` |
| 8 | first soft box on the floor (back, under the shelf) | last resort's floor pose; the guard moved it to another floor spot (slots 3.82 → 4.38); no soft top exists yet |
| 9 | soft on soft (0.30 m) | the guard: a soft top keeps 4.32 slots against 3.76 for the floor pose |
| 10 | floor | the only soft top (0.63 m) is under the shelf: a third layer of 0.30 m reaches 0.93 m, through the shelf at 0.845 m (`overlaps-main_shelf`); with the cap lifted the only soft tops are the shelf's soft boxes at 1.14 m |
| 11 | soft on soft | guard |
| 12 | floor | no soft top under the shelf ceiling; the guard moved the floor pose |
| 13 | floor | a soft top existed but scored 3.02 against the floor's 2.81: inside the guard's 0.25 margin |
| 14 | floor | no soft top |
| 15 | soft on soft | guard |
| 16 | floor (physics resort) | the guard chose a soft top at 0.53 m; the shadow world vetoed it; the resort put it on the floor (soft share passes 0.40) |
| 17-18 | soft on soft, then floor | guard |
| 19-20 | floor (physics resort) | guard chose a soft top; the shadow vetoed it; resort to the floor |
| 21 | floor (`soft-edge`) | guard: soft top and floor both keep 0 slots; tie to the lower pose (`pocket.py:214`) |
| 22-23 | soft on soft (physics resort) | the floor is gone (0 floor poses) |
| 24-32 | the 9 hard boxes: 1 on the shelf, 8 by count mode on soft tops at 0.6-1.15 m (covering soft) | nothing on the floor fits a 0.55 × 0.40: free floor 0.28 in strips (largest empty rectangle 0.10 × 1.38 m) |
| 33 | declined: 0.65 × 0.45 × 0.25 | |

The pattern on the (P) boards: shelf first. Then soft alternates floor / soft top,
because a two-high column under the shelf has no third layer. Every new floor box
creates one new soft top, and that top is used by the next box. Once the floor is
gone the rescues stack on soft. The hard run arrives on a floor that is 70 % soft
and 2 % hard.

### 2.3 When soft-on-soft stops and the floor starts being consumed

There is no single moment. Soft-on-soft starts early (first soft-on-soft step
in the v50 C carpets: 9, 5, 4, 22, 4, 6, 19, 14, 52 and none on c-s0068). It
continues to the end in the soft-first boards (the last one is the episode's last
placement on c-s0036, s0072). Soft-on-soft and floor placements
*interleave*. The floor share climbs in steps of 0.06-0.10 a floor box. It
passes 0.40 at:
- step 10-16 on the 1-container boards (c-s0004 10, s0006 16, s0069 14, s0049 14);
- step 19-39 on the multi-container soft-first boards (s0072 25, s0036 36,
  s0075 39).


### 2.4 Why the floor-bound soft boxes went to the floor (counts)

Unit: every soft box that the **record** put on the floor in the 16 probed carpet
episodes (10 C, 6 B; replays stop where a recorded pose fails on the local board),
228 boxes. The first rule that fires is counted (`reasons.py`,
`data/reasons.json`).

| # | reason | boxes | what it means |
|---:|---|---:|---|
| 1 | **time cut** | 91 | on the same board the deterministic agent puts the box on a soft top (90) or the shelf (1). The record's clock cut a stage, mainly the pocket guard's own window (`agent.py:_pocket_guarded`: `min(start + 0.85 x budget, now + pocket_guard_seconds 0.8)`). Without a deadline the guard took 1.3-3.3 s on c-s0036 (21 such steps) and found soft tops in containers 1-2 that its 0.8 s never reached. |
| 2 | rescue floor | 9 | the deterministic agent floors it too, through the physics resort: its guard (or ladder) pose on a soft top was vetoed by the shadow world. All 9 are on priority-container boards (c-s0006 3, c-s0069 6) |
| 3 | guard stood down | 13 | the guard expected no hard class any more: `ClassFrequencies` counts 41 items a container, so after ~35-40 items seen every arrival probability is < 0.5 (c-s0068: all 10, "seen 40, remaining 1"). The hard2 streams are longer (c-s0068 has 80 items, its big hard items come at 88) |
| 4a | no soft top under the cap | 29 | soft-top poses exist only with the 0.7 m cap lifted. In 24 of the 29 the lowest such pose is ≥ 0.75 m: on the soft boxes stacked on the *shelf*, not a floor column |
| 4b | no soft top at all | 12 | no column yet, or the column is at its ceiling (two layers under the 0.845 m shelf) |
| 4c | soft tops legal but not in the guard's set | 21 | the census finds fully supported soft-top poses, but the guard's generator (anchors every 0.06 m, 120 poses a container, ≥ 0.6 support) does not offer them |
| 5 | **cross-container comparison** | 21 | a soft top existed; the guard took a floor pose in another container because it ranks poses by the slots left in *each pose's own* container (`pocket.py:212-214`), not by slots lost. In all 20 measured cross-container cases the soft top costs fewer slots (`guard_xctr.py`): e.g. c-s0053 step 17 floor in c1 loses 2.45 slots, the soft top in c0 0.06 |
| 6 | tie to the lower pose | 25 | a soft top and a floor pose keep equal slots (the floor spot is dead for the expected classes), and the tie goes to the lower pose, the floor (`pocket.py:214`) |
| 7 | inside the margin | 1 | the soft top was better by < 0.25 slots |
| 8 | floor rated better | 4 | |
| 9 | guard not asked | 2 | |

**The priority-container bar is a flag on top of these.** 69 of the 228 boxes
were plain soft boxes in a priority container, placed by the last resort's relaxed
stage because the strict ladder and the stack option may not route them there.
Their primary reasons are: 4a 16, 6 11, 2 9, 3 9, 4c 8, 1 8, 4b 5, 5 3.

The five causes asked about, in one line each:
- **0.7 m cap**: 29 boxes, mostly by closing the shelf's second soft layer.
- **No soft top yet**: 12 with none at all, plus 21 where legal ones exist but
  the guard's generator does not offer them.
- **Priority-container bar**: 69 boxes on the 7 (P) boards (a flag).
- **Pocket guard** (stood down, cross-container, tie, margin): 13 + 21 + 25 + 1 = 60.
- **Time cut**: 91, concentrated on the multi-container soft-first boards:
  - C: s0036 28 of 31, s0072 14 of 23, s0075 13 of 18;
  - B: s0005 15 of 30, s0036 7 of 15.

  It is nearly absent on the 1-container boards (0-2 each).

What this does not say: that removing the time cut crosses these boards. The
deterministic C record (`gate0det-hard2`) still misses s0072 (−21) and s0075
(−23). c-s0036 crosses there (+5), but the deterministic episode on this machine
reads −3 (80 of 83; branch `k = 0`).

### 2.5 Other structural facts the probes surfaced

- **The shelf caps the columns at two.** On the 1-ULD hard2 containers the main
  shelf covers the back half of the floor at 0.845 m. A soft box on edge
  (0.30 m tall, the orientation the guard's generator prefers for its smaller
  footprint) stacks two high under it. The third is refused as
  `overlaps-main_shelf` (c-s0006 step 10). The 0.7 m cap is never the binding
  rule there.
- **The upper third of the container is unused by soft cargo.** The highest soft
  top on the soft-first carpets is 1.14-1.6 m in containers 1.4-1.94 m tall. Soft
  above 0.7 m gets there only by the shelf, the stack option and the rescues
  (c-s0036: 32 of 82 soft boxes end above 0.7 m: shelf 6, `stack-rl` 13,
  `grid-rescue` 8, `pocket-soft` 5).
- **The shadow world refuses soft-on-soft poses that the simulator accepts.** At
  c-s0006 steps 19 and 20 the guard chose a soft top. The shadow vetoed it and the
  physics resort put the box on the floor. Forced onto the same soft top
  (`soft:0`), the box stays in the official simulator and the episode crosses
  (34 against the baseline's 33; section 3).
- **A decline with thousands of legal soft-top poses.** c-s0068 declines at step
  42 on a soft 0.45 × 0.30 × 0.20. The census finds 9,848 legal poses on soft tops
  under the cap. The strict ladder and the stack option skip the priority
  container. The guard is not asked (no floor pose). The physics resort and grid
  rescue return nothing (`decline_probe.py` would say why; not run, see open
  questions).



## 3. Counterfactuals: "if this move had been different"

All branches are on the record's board at step k, with the record's arm and
deterministic budgets. The agent plays from k+1 to the end. The full per-branch
table is `cf_table.py` (from `data/cf_results.jsonl`). The alternatives:
- `ladder:N`: the N-th pose of the ladder's rung, before the guard;
- `guard:N`: the guard's N-th best pose;
- `soft:0`: the lowest soft-top pose under the cap with ≥ 0.6 support;
- `softnocap:0`: the same with the 0.7 m cap lifted for this one box;
- `floor:1`: the guard's second floor pose.

### 3.1 The near misses

**c-hard2-s0004** (threshold 22, record 20). The agent's own continuation reads
−2 from every one of 12 steps (k = 0..19): a stable board.

| k | move | pose | margin | baseline at k | shipped arm: alt / baseline |
|---:|---|---|---:|---:|---|
| 3 (first soft floor box) | softnocap:0 | on the shelf's soft box, 1.15 m | **0** | −2 | **0 / −2** |
| 5 (second soft floor box) | softnocap:0 | the same | **0** | −2 | **0 / −2** |
| 3 | ladder:0 (the ladder's floor pose, not the guard's) | floor | −1 | −2 | |
| 8 | soft:0 | soft top 0.34 m | −2 | −2 | |
| 11-19 (the hard run) | guard:0 / guard:1 / ladder:1 | | −1 to −2 | −2 | |
| 3, 5, 7, 10 | soft:0 | none exists | | | |

One box moved off the floor at the very start crosses c-s0004, and the shipped
arm confirms both branches. The move puts the first floor-bound soft box onto
the shelf's soft layer at 1.15 m, which the 0.7 m cap forbids. No single move in
the hard run does it, and the decline itself (soft 0.5 × 0.4 × 0.4, 0 floor and 0
soft-top poses) has no move. **The carpet is decided at the first soft floor
placements here.**

**c-hard2-s0006** (threshold 34, record 33). The agent's own continuations spread:
- from k = 0..21: −2, −1, −2, −5, +1, −1, 0, −1, −1, −1, −1 (2 of 11 cross);
- from k = 23..32: every one crosses (0 to +1).

The record's own late moves (count-mode covers at steps 25-32, under the clock) and
this machine's physics leave the end board one item from the line either way.

| k | move | pose | margin | baseline at k | shipped arm: alt / baseline |
|---:|---|---|---:|---:|---|
| 19 | soft:0 (the guard's choice that the shadow vetoed) | soft top 0.34 m | 0 | −1 | 0 / 0 |
| 20 | soft:0 (the same) | soft top 0.34 m | 0 | −1 | **0 / −1** |
| 21 | soft:0 (the guard's tie went to the floor) | soft top 0.34 m | **+2** | −1 | **+2 / 0** |
| 16 | soft:0 | soft top 0.53 m | −1 | 0 | |
| 8, 10, 14, 18 | softnocap:0 | on the shelf's soft box, 1.14 m | −3 / −4 | −1 / −2 | |
| 12 | softnocap:0 | the same | 0 | −5 | 0 / −1 |
| 8 | ladder:0 | floor | 0 | −1 | −2 / −2 |
| 23 | guard:0 (a hard box on soft) | | −9 | 0 | |

- Keeping the late floor-bound soft boxes on the existing soft column crosses on
  both arms at k = 20 and k = 21 (the shipped baseline at k = 21 crosses by
  itself; the alternative adds two). At k = 19-21 the soft-top pose was the
  guard's own pick, or tied with the floor. The shadow world's veto, or the tie
  rule, sent it to the floor.
- Lifting the cap for one box onto the shelf layer does the opposite on this board.
  4 of 5 branches lose 3-4 items against their baseline, presumably because the
  shelf layer is where the late soft and hard boxes went (not traced).
- **c-s0006 is decided late, and by a margin smaller than the board's own noise.**

<!-- CF36 -->


## 4. Area or shape?

`shape.py` rasterises the floor at the moment the stream's first big hard item
(footprint ≥ 0.2 m²) arrives. It counts how many footprints of the commonest big
hard class (0.65 × 0.45 m plus 2 × 0.026 m clearance) a greedy back-to-front
packer fits in three cases:
- the real free floor;
- with the same soft cells moved into one compact block from the chamfer side (the
  idealised bound: it ignores arrival order, the door path, column stability and
  the cap);
- on the floor with the hard cells only.

| boards (v50 C + B, soft floor share ≥ 0.40 at the first big hard item) | n | real | compact bound | no soft |
|---|---:|---:|---:|---:|
| all | 17 | 1.47 | 2.94 | 8.29 |
| one container (1.9 m² of floor) | 7 | 0.14 | 0.57 | 3.57 |
| two or three containers | 10 | 2.40 | 4.60 | 11.60 |
| those that crossed anyway | 5 | 2.00 | 3.40 | 9.60 |
| those that missed | 12 | 1.25 | 2.75 | 7.75 |
| soft-early boards that are not carpets (share 0.10-0.40) | 16 | 5.88 | 6.56 | 9.12 |

- **On the 1-ULD boards the carpet's cost is its area.** A 0.66-0.74 soft share
  of a 1.38 × 1.38 m floor leaves a 0.38 m strip even when compacted, narrower
  than the 0.50 m the class needs. The bound is 0 slots on 6 of the 7. Only fewer
  soft boxes on the floor helps there, not a better arrangement.
- **On the multi-ULD boards the shape costs about half the slots**: 2.4 real
  against 4.6 compacted.
- **Slots at the first hard item do not decide the episode on their own.**
  c-s0014 and b-s0014 cross with 0 slots: their hard items go onto soft tops by
  count-mode covers and onto the shelf. c-s0075 misses with 3.


### 4.1 A realisable compaction, branched: it does not deliver the bound

`alts.wrap_compact` replaces every soft floor pose the agent chooses (`compact`)
or the first six (`compact:6`) with a compaction pose:
- a fully supported floor pose from the guard's own generator;
- in the deepest 5 cm band still open (back wall first, so the block grows from
  the back and cannot seal the door side, the G investigation's failure);
- flush with a wall or with a soft box already on the floor;
- then from the chamfer side.

The rule is lexicographic, with no weights. The pose goes through the agent's own
shadow check, and the agent's pose stands when the check vetoes it. Whole
episodes (k = 0) on the record's arm, deterministic budgets. The baseline is the
same arm unwrapped on this machine. The slots are counted at the first big hard
item, on the branch's own intended poses (`compact_slots.py`).

| scene | branch | placed / margin | soft floor share at the first big hard item | slots real / compact bound | soft placed / covered |
|---|---|---|---:|---|---|
| b-hard2-s0006 | baseline | 32 / -2 | 0.63 | 0 / 1 | 21 / 0 |
| b-hard2-s0006 | compact | 26 / -8 | 0.65 | 0 / 0 | 21 / 3 |
| b-hard2-s0006 | compact:6 | 26 / -8 | 0.64 | 0 / 1 | 21 / 0 |
| b-hard2-s0036 | baseline | 74 / -9 | 0.56 (end, no big hard item) | 2 / 6 | 74 / 0 |
| b-hard2-s0036 | compact | 69 / -14 | 0.69 (end, no big hard item) | 0 / 4 | 69 / 0 |
| b-hard2-s0069 | baseline | 25 / -14 | 0.65 | 0 / 0 | 20 / 0 |
| b-hard2-s0069 | compact | 33 / -6 | 0.47 | 1 / 2 | 19 / 0 |
| b-hard2-s0069 | compact:6 | 32 / -7 | 0.47 | 1 / 2 | 18 / 0 |
| c-hard2-s0004 | baseline | 20 / -2 | 0.45 | 1 / 1 | None / None |
| c-hard2-s0004 | compact | 21 / -1 | 0.51 | 1 / 1 | 12 / 1 |
| c-hard2-s0004 | compact:6 | 21 / -1 | 0.51 | 1 / 1 | 12 / 1 |
| c-hard2-s0006 | baseline | 32 / -2 | 0.70 | 0 / 0 | None / None |
| c-hard2-s0006 | compact | 33 / -1 | 0.65 | 0 / 0 | 21 / 4 |
| c-hard2-s0006 | compact:6 | 32 / -2 | 0.68 | 0 / 0 | 21 / 6 |
| c-hard2-s0009 | baseline | 55 / +2 | 0.42 | 3 / 5 | 35 / 0 |
| c-hard2-s0009 | compact | 54 / +1 | 0.55 | 1 / 5 | 35 / 2 |
| c-hard2-s0010 | baseline | 47 / +3 | 0.35 | 4 / 7 | 25 / 0 |
| c-hard2-s0010 | compact | 42 / -2 | 0.40 | 5 / 6 | 25 / 0 |
| c-hard2-s0014 | baseline | 40 / +1 | 0.65 | 0 / 0 | 39 / 0 |
| c-hard2-s0014 | compact | 36 / -3 | 0.69 (end, no big hard item) | 0 / 0 | 36 / 0 |
| c-hard2-s0036 | baseline | 80 / -3 | 0.59 (end, no big hard item) | 1 / 5 | 80 / 0 |
| c-hard2-s0036 | compact | 81 / -2 | 0.67 (end, no big hard item) | 0 / 3 | 81 / 0 |
| c-hard2-s0049 | baseline | 33 / -16 | 0.70 (end, no big hard item) | 0 / 0 | 33 / 0 |
| c-hard2-s0049 | compact | 29 / -20 | 0.63 (end, no big hard item) | 0 / 2 | 29 / 0 |
| c-hard2-s0049 | compact:6 | 32 / -17 | 0.70 (end, no big hard item) | 0 / 0 | 32 / 0 |
| c-hard2-s0053 | baseline | 44 / -3 | 0.00 | 10 / 10 | 31 / 0 |
| c-hard2-s0053 | compact | 40 / -7 | 0.00 | 10 / 10 | 28 / 4 |
| c-hard2-s0068 | baseline | 42 / -38 | 0.54 (end, no big hard item) | 0 / 1 | 20 / 0 |
| c-hard2-s0068 | compact | 44 / -36 | 0.47 (end, no big hard item) | 0 / 2 | 22 / 0 |
| c-hard2-s0068 | compact:6 | 42 / -38 | 0.45 (end, no big hard item) | 0 / 2 | 20 / 0 |
| c-hard2-s0069 | baseline | 26 / -13 | 0.67 | 0 / 0 | 20 / 4 |
| c-hard2-s0069 | compact | 22 / -17 | 0.69 | 0 / 0 | 20 / 1 |
| c-hard2-s0069 | compact:6 | 28 / -11 | 0.74 | 0 / 0 | 20 / 2 |
| c-hard2-s0072 | baseline | 37 / -31 | 0.54 (end, no big hard item) | 1 / 4 | 37 / 0 |
| c-hard2-s0072 | compact | 52 / -16 | 0.74 (end, no big hard item) | 0 / 0 | 52 / 0 |
| c-hard2-s0075 | baseline | 87 / -22 | 0.45 | 4 / 5 | 41 / 0 |
| c-hard2-s0075 | compact | 71 / -38 | 0.58 | 1 / 5 | 41 / 0 |


- **Crossings: 3 → 1** on the 15 boards. The three baseline crossings (c-s0009
  +2, s0010 +3, s0014 +1) become +1, −2 and −3. No miss crosses.
- **Placed items: −1.4 per board on average** (sum −21 over 15). The spread is
  wide:
  - large gains: c-s0072 +15, b-s0069 +8, c-s0068 +2;
  - large losses: c-s0075 −16, b-s0006 −6, b-s0036 −5, c-s0010 −5.
- **Slots at the first big hard item do not rise.** The real count equals or
  falls below the baseline's on 13 of the 15 boards (up on b-s0069 and c-s0010).
  The soft floor share at that moment *rises* on 10. The compaction moves
  floor-bound boxes; it does not send fewer boxes to the floor. A box flush in
  the back row is also one the guard would otherwise have moved onto a soft top
  later: the soft-on-soft placements drop.
- **Soft quality.** Covered soft boxes change by −3 to +4 a board (c-s0053 0 → 4,
  c-s0009 0 → 2, b-s0006 0 → 3, c-s0069 4 → 1; the c-s0004 / s0006 baselines
  predate the metric). So the compaction does not buy soft score either. The count
  of uncovered soft boxes falls with the placed count where the episode ends
  earlier (b-s0006, b-s0036, c-s0010, c-s0014, c-s0049, c-s0075).
- **How this differs from the zone form** ("The zone form", findings, lost
  3 stretch crossings in the deterministic pair).
  - The zone raised the cap to 1.2 m, so soft columns grew taller. The
    compaction keeps the cap and the column rules and changes only *where on the
    floor* a floor-bound soft box goes.
  - The zone's cost was height: settle endings 1 → 6 and the cog. The compaction
    adds no height. Its cost is the soft-on-soft placements it pre-empts, and a
    back-row block that leaves the hard rows less depth.
  - Neither reduces the number of floor-bound soft boxes. The counterfactual
    rescues of §3 do: they move one box *off* the floor.
- **No compaction branch rescued a board**, so there is nothing to confirm on the
  shipped arm.

What the compact *bound* of §4 measures is real floor area left in pieces. What
this branch says is that the online rule does not recover it. The bound assumes
the soft area is known in advance and laid out as one block. The stream lays it
one box at a time, and every floor box also creates the next soft top.



## 5. The gate (v49 to v50): why the carpet survives it

The gate makes soft cargo structure from the first soft box, where v49 waited
until soft covered 35 % of the floor (`soft_structure_floor_share` 0.35 → 0). By
§2.1 it does not open a new generator. What it changes is which soft-top poses
the pocket guard, the stack option and the rescues may use from the start. In the
deterministic pair (`bandntdet-hard2` → `gate0det-hard2`, `course.py`):

| scene | margin v49 → v50 | first soft-on-soft step | soft boxes on the floor / on soft | soft floor share at the end |
|---|---|---|---|---|
| s0010 | −1 → +6 | 23 → 14 | 14 / 2 → 10 / 6 | 0.46 → 0.35 |
| s0014 | −5 → +1 | 10 → 9 | 14 / 8 → 13 / 15 | 0.70 → 0.65 |
| s0036 | −1 → +5 | 17 → 2 | 35 / 34 → 36 / 38 | 0.70 → 0.64 |
| s0004 | 0 → −2 | 7 → 4 | 4 / 2 → 5 / 3 | 0.44 → 0.44 |
| s0006 | −4 → −1 | 13 → 9 | 8 / 6 → 10 / 4 | 0.75 → 0.70 |
| s0072 | −9 → −21 | 13 → 3 | 22 / 21 → 16 / 17 | 0.71 → 0.65 |
| s0075 | −23 → −23 | 13 → 6 | 17 / 17 → 16 / 19 | 0.46 → 0.45 |

Soft-on-soft starts earlier on every board, but the floor count hardly moves (±4)
and the end share drops by 0.00-0.11. The gate adds soft tops. It does not change
the floor-or-top choice, which belongs to the guard (§2.4) and is still made under
its 0.8 s window, its cross-container ranking, its 41-item prior and the shelf
ceiling. The three carpets that became crossings gained 4-12 soft-on-soft
placements. s0004 lost 2 items with the same floor count, which is inside the
noise of §0 (c-s0004's baselines are stable at −2 on this machine, but c-s0006's
spread over 6 items).



## 6. Against the taxonomy's labels, and other surprises

- **"The soft-edge rung makes the largest drop"** is true of the label, not of the
  ladder. On the 7 priority-container boards the label is the last resort's
  *relaxed* ladder (the strict ladder never sees a soft box there). On the (N)
  boards about half of the soft floor poses the records label `soft-edge` or
  `pocket-soft` are the pocket guard's choice, or a guard cut short by its 0.8 s
  window (§2.4).
- **"Time pressure is concentrated here"** is right, and the binding clock is
  the guard's 0.8 s window, not the 4.5 s budget. On the multi-container
  soft-first boards 55 of the 72 record floor placements are soft-top placements
  in the deterministic agent's hands.
  - The deterministic record still misses most of them (s0072, s0075).
  - On this machine c-s0036 misses deterministically too (80 / 81 of 83).
  - So the clock explains the C/C-det difference on s0036, not the carpet.
- **The carpet is mostly the soft cargo's own problem.** In 8 of the 18 carpets
  the big hard cargo comes only after the threshold. 11 decline on a soft item.
  The volume the soft cargo can use is bounded by the cap and the shelf: columns
  two high under the shelf, nothing above about 1.2 m except via the rescues.
- **The cap is mostly the shelf's.** In 24 of the 29 floor placements where only
  the cap stood between the box and a soft top, the soft top was the soft layer
  on the shelf (≥ 0.75 m), not a floor column.
- **The shadow world refuses soft-on-soft poses that the simulator keeps**
  (c-s0006 steps 19-20, §3). Its soft-box model is the likely reason (not traced).
- **The pocket guard compares containers wrongly.** It ranks by the slots left in
  each pose's own container, so on a multi-container board it prefers the floor
  of the emptier container to a soft top in the fuller one. That happened in 21 of
  the 228 floor placements. In all 20 measured cases the soft top cost fewer
  slots.
- **Replays break between machines.** The local PyBullet build moves soft boxes
  by centimetres against the CI's. Recorded late poses fail the sweep (4 of the
  long episodes), and near-threshold outcomes swing by ±1-3 items with the board
  (c-s0006: −5 to +1 from neighbouring steps of one record). Any "a single move
  crosses it" claim on a −1 board needs a noise reference like §0's.


## 7. Open questions

- **The shadow world and soft-on-soft.** Why does it veto soft-top poses that the
  official simulator keeps (c-s0006 steps 16, 19, 20; all 9 "rescue floor"
  boxes)? This is a measurement of its soft contact model, not done here.
- **c-hard2-s0068's decline** with 9,848 legal capped soft-top poses: what do
  the physics resort and the grid rescue try? `decline_probe.py` is written and
  was not run.
- **The guard as a ranking.** It ranks by absolute slots per container and breaks
  ties to the floor. Its 41-item prior stands it down on long streams, and its
  0.8 s window cuts it on multi-container boards. Each is a measured mechanism.
  Whether fixing any of them crosses boards was not branched as a rule (only as
  single moves). The cross-container case is the cleanest test: rank by slots
  lost.
- **The shelf ceiling.** A two-high column under the back shelf leaves a soft box
  on edge (0.30 m) without a third layer, where three flat layers (0.75 m) would
  fit. Whether the flat orientation would change the floor count was not measured.
- **B coverage.** The probes stopped on b-s0068 and b-s0043 (census too slow).
  B replays break early (b-s0036 at step 35 of 79), so the B reason counts cover
  the first half of the B episodes.
- **Shipped-form baseline records** (`ship-hard2`, `ship-hard2-b`) were not on
  the branch yet. The shipped confirmations here are branch-against-baseline on
  this machine only.
- Everything here is one deterministic run per branch on one local PyBullet
  build. With the noise of §0, a single +1 is not evidence. Only the c-s0004 pair
  (two k, two arms, against 12 identical baselines) and the c-s0006 k = 20/21 pair
  (two arms) repeat.

## Scripts and data (`reports/wedge/hard2-D-carpet/`)

- `common.py`: board reconstruction, floor tracker, the taxonomy's v50 D lists.
- `course.py`: per-step course of every hard2 episode in the 7 records
  (`data/course_summary.json`; steps in the scratch directory).
- `d_table.py`: the episode table of §1.
- `physbranch.py`: replay the record's actions in the official simulator, then
  let the agent play; `state_at`, `replay_check`.
- `instrument.py`: the decision probe (opt-in wrappers, no edits to `rule_alpha`).
- `archaeology.py`: walks a record and probes every step (`--resume` substitutes
  the agent's pose where a recorded pose fails); `arch_summary.py` gives the rows
  in `data/arch_*.json`.
- `reasons.py`: the floor-reason counts (`data/reasons.json`); `guard_xctr.py`:
  the guard's cross-container comparison.
- `alts.py`: the alternative moves and the compaction wrapper; `cf.py` runs a plan
  (`data/cf_results.jsonl`); `cf_table.py` gives the tables (`data/rescues.json`).
- `shape.py` (`data/shape.json`) and `compact_slots.py`
  (`data/compact_slots.json`): slots against the compact bound.
- `make_plan.py`: branch plans from the archaeology rows; `decline_probe.py`: the
  rescue stages at a declining call (not run).
- `arms/arm_ship_{c,b}.txt`: the shipped-form arms (from
  `origin/claude/rl-packing-policy-ftogt3` at 9e4ada85).

