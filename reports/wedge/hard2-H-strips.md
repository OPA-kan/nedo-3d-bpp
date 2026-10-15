# The H boards (no level patch): where the floor goes, and what one move changes

Investigation of cause H of `hard2-miss-taxonomy.md`: boards that pack to
about 0.38 and close with the floor in strips and no usable top. 14 C and 7 B
episodes in v50 (`gate0-hard2`, `gate0-hard2-b`). Every board was replayed in
the official simulator (PyBullet), every placement of the run-in dumped, and
counterfactual branches were played to the end with the agent.

Scripts, compact data and generated tables: `reports/wedge/hard2-H-strips/`
(see the last section). Heavy output (per-step dumps, branch logs):
`/home/user/inv-H-scratch` (not in git).

STATUS: draft; sections marked (pending) are being filled by runs in progress.

## Summary

- **The strips are not what separates H from the crossings.** On the records
  (commanded boxes, `strip_stats.md`) the crossings make the same strips by
  the same means:
  - floor killed (usable floor turned dead without being covered) per m^2
    covered: H 0.54 (C and B), crossings 0.53 / 0.52;
  - the dead floor at the end has the same geometry: 56-58 % narrow in y
    (strips lying along x, the depth left in front of or behind a row),
    about half bounded wall-box and half box-box, widths 0.1-0.3 m;
  - the floor is gone at the same coverage (0.66-0.69 of the floor covered);
  - the step that takes the last usable floor is placed by the same stages:
    on the reference runs ladder 8 / last resort 4 / physics resort 4 /
    stack option 3 of 19 H boards against 8 / 4 / 4 / 1 of 17 crossings
    (`arch_stats.md` §2b).
- **What separates them is how many items are still missing when the floor
  is gone.** The stacking phase after the floor is gone places the same
  number of items in both groups (records: C 10 vs 9, B 8 vs 12; reference
  runs 8 vs 8), but the H boards are 15 (C) / 11 (B) items short at that
  moment and the crossings 2 / 4 (`gone_stats.md`).
  - The H scenes ask more items per m^2 of floor: the threshold count is
    13.1 (C) / 14.8 (B) items per m^2 against 9.7 / 9.5 for the crossings,
    and their items are smaller (mean 65 / 59 l against 74 / 76 l). The floor
    phase itself holds about the same number of items per m^2 (C 8.2 vs 9.2,
    B 9.5 vs 8.6).
  - Crossing rate by the count asked per m^2 of floor (volume misses
    excluded), C: < 8: 10/10; 8-10: 16/24; 10-12: 4/8; 12-14: 8/18;
    > = 14: 5/31. H, G and D misses all sit at >= 8.
  - Hence at the same fill the H boards have less usable floor left
    (at fill 0.30, C: 0.29 vs 0.61 m^2) and lose the floor at a lower fill
    (C 0.27 vs 0.34): many small low boxes cover the floor before the volume
    is in.
- **One move can still cross, but only before the floor is gone, and the
  sensitivity is two-sided.** (pending: complete table) On the four C near
  misses at margin -1 every board has a single change that crosses; none at
  the last 1-3 placements except c-hard2-s0028 (the last placement took the
  only spot the next, large item needed). The decisive moves are 1-3
  placements before the floor is gone (c-hard2-s0007: lead 8; s0039:
  lead 11-15; s0076: lead 8-12). On B only b-hard2-s0039 has a rescue (lead 7
  and 11); b-s0040, s0067, s0083 have none in the steps branched.
- **The typical "why" of the decisive move** (c-hard2-s0007, step 12): the
  max-footprint rung ties on footprint between the B box lying across
  (0.65 x 0.45) and the same box turned (0.45 x 0.65); the tie is broken by
  the row-waste bucket, 3 against 4 (0.058 vs 0.074 m^2 of free floor
  stranded _in the box's own x-rows_, `row_waste_axes=x`). The turned box
  leaves the depth in front of it that the next 0.75 x 0.56 needs; the
  shipped pick leaves a front band the C box cannot lie in, its ladder pick
  stands at the door and is refused by the shade veto (0.37 m^2 walled off),
  and the physics resort, which orders by shade first, stands it in the
  middle of the free floor: usable floor 0.74 -> 0.00 in one step. Turning
  the box at step 12 crosses by +3 (5 of 8 alternatives; confirmed on the
  shipped arm).

## 1. Method

**Replays must use full-precision actions.** The bench records round actions
to 0.1 mm. In the official simulator that moves the settled poses: replaying
`gate0det-hard2`'s c-hard2-s0039 with the agent's own full-precision actions
reproduces every settled pose to 0.0 m; the same actions rounded to 4
decimals move the first box by 2.4 mm and the board by up to 5 cm by step 18
(`round_test.py`). Forced replays of the time-faithful B records fail on
recorded actions (b-hard2-s0039 step 19 transport, b-hard2-s0040 step 23
settle; `replay_check.py`).

**Reference runs (`ref.py`).** Each H scene was played from the start with
its record's v50 arm plus `deterministic_budgets=true` (the clock-dependent
budgets inside a call lifted; the shadow and the physics resort keep their
own clocks): C with `gate0det-hard2`'s arm, B with `gate0-hard2-b`'s. The
full-precision actions are kept, so every branch forces the reference's
boards exactly. At every step `ref.py` dumps the agent's answer and stage
(the reason string distinguishes the main ladder from the last resort's
relaxed ladder; the record's `archetype` does not), the call's trace (every
shadow verdict and shade reading in order), the ladder recomputed on the
agent's board (candidates, veto counts, rung orders, the best poses with
their key terms, shade and a shadow verdict from a private ShadowSim), and
the floor before the step with a 4 cm map.

Reference against record (placed): C equal on 11 of 14 (s0040 34 vs 38,
s0065 66 vs 61 ending on a settle, s0071 48 vs 47, s0073 89 vs 94); B equal
on 3 of 7 (s0040 40 vs 41, s0066 26 vs 30, s0067 68 vs 70, s0080 70 vs 96).
All 21 still miss. The deterministic run is not fully deterministic (resort
and shadow clocks), and B is the most clock-sensitive.

**Branches (`cf.py`).** At step k the reference actions are forced for steps
< k (the pocket guard's stream statistics are fed, the one piece of
cross-call state that changes decisions), the placement at k is changed and
the agent plays to the end. Kinds:

| kind              | what is played at k                                                                                                                                                                                                                                                                                             |
| ----------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `null`            | the agent's own answer (the replay's baseline; equals the reference up to the clocks)                                                                                                                                                                                                                           |
| `veto<j>`         | the agent's (j+1)-th acceptable answer: the first j poses its shadow check would accept are turned into hard vetoes, so the agent goes on as on a real veto (shadow alternatives, stack option, last resort, physics resort, grid rescue). The agent-consistent "next candidate" whatever stage placed the box. |
| `rung<r>`         | the r-th distinct pose of the ladder's chosen rung (`rung1` = the ladder's own pick when a downstream veto replaced it: the shade veto let through)                                                                                                                                                             |
| `other:<rung>`    | the best pose of another rung                                                                                                                                                                                                                                                                                   |
| `vetoed:<reason>` | a shortlisted pose the ladder's vetoes removed (legal for the analytic validator)                                                                                                                                                                                                                               |
| `maxsurf<1,2>`    | hand-picked: of every legal pose of the item (all orientations, floor, shelf, tops, all containers; generator and validator, no vetoes) the two that leave the most usable surface (the taxonomy's 0.40 x 0.55 x 0.24 window over every level)                                                                  |

Pose alternatives are applied without the agent's shadow check ("fails" in
the tables = the simulator refused the pose at k). Branch steps: near misses
(reference margin >= -3) the last 1 and 3 placements, the step that takes the
last usable floor ("floor gone") and 1, 2, 4 before it; the farther misses
the floor-gone step and 1, 2 before it.

## 2. Decision archaeology

(see §2 of the generated `arch_stats.md` and the per-episode run-ins from
`arch_report.py`)

(pending: final text)

## 3. Counterfactuals

(pending: final table from `cf_stats.md`)

## 4. Strip formation in general

(pending: final text from `strip_stats.md`, `need_stats.md`, `gone_stats.md`, `arch_stats.md`)

## 5. Orientation as a lever

(pending: `orient.py`)

## 6. The shade veto -> rescue stage path

(pending)

## 7. Shipped-form confirmation

(pending: `ship_confirm.py`)

## 8. Surprises and evidence against the labels

(pending)

## 9. Open questions

(pending)

## Scripts and outputs

(pending)
