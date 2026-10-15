# The H boards (no level patch): where the floor goes, and what one move changes

Investigation of cause H of `hard2-miss-taxonomy.md`: boards that pack to
about 0.38 and close with the floor in strips and no usable top (14 C and 7 B
episodes in v50, `gate0-hard2` / `gate0-hard2-b`). Every H board was replayed
from the start in the official simulator (PyBullet) with full-precision
actions, every placement dumped with the ladder's candidates, and
counterfactual branches were played to the end with the agent. 17 crossings
were run the same way as a control.

Scripts, compact data and the generated tables are in
`reports/wedge/hard2-H-strips/` (list at the end). Heavy output (per-step
dumps, branch logs) stays in `/home/user/inv-H-scratch`.

## Summary

**Measured**

- **The strips do not separate H from the crossings.** The crossings make
  the same strips by the same means (records, `strip_stats.md`; reference
  runs, `arch_stats.md`):
  - usable floor killed (turned dead without being covered) per m^2
    covered: H 0.54 (C and B), crossings 0.53 (C) / 0.52 (B);
  - the dead floor at the end: 56-58 % narrow in y in both groups (strips
    lying along x: the depth left in front of or behind a row); about half
    bounded wall-box and half box-box; widths mostly 0.1-0.3 m;
  - the floor is gone at the same coverage, 0.66-0.69 of the floor;
  - the step that takes the last usable floor is placed by the same stages:
    ladder 8, relaxed last resort 4, physics resort 4, stack option 3 of 19
    H reference runs, against 8 / 4 / 4 / 1 of 17 crossings.
- **What separates them is how many items are still missing when the
  floor is gone.**
  - After that step the stacking phase places the same number of items in
    both groups (records: C 10 vs 9, B 8 vs 12; reference runs 8 vs 8).
  - At that step the H boards are 15 (C) / 11 (B) items short of the
    threshold, the crossings 2 / 4 (`gone_stats.md`).
  - The H scenes ask more items per m^2 of floor: 13.1 (C) / 14.8 (B)
    against 9.7 / 9.5 for the crossings. Their items are smaller (mean 65 /
    59 l against 74 / 76 l).
  - The floor phase holds about the same number of items per m^2 in both
    groups (C 8.2 vs 9.2, B 9.5 vs 8.6).
  - So at the same fill the H boards have less usable floor left (at fill
    0.30, C: 0.29 vs 0.61 m^2) and lose it at a lower fill (C 0.27 vs
    0.34). Many small, low boxes cover the floor before the volume is in.
  - Crossing rate by the count asked per m^2 of floor (volume misses
    excluded), C: < 8: 10/10; 8-10: 16/24; 10-12: 4/8; 12-14: 8/18; >= 14:
    5/31. B has the same shape. H, G and D misses all sit at >= 8.
- **One changed placement can cross, but the sensitivity cuts both ways.**
  - All four C near misses at margin -1 have a single change that crosses
    (c-hard2-s0007, s0028, s0039, s0076), and so does s0078 (-3). Every C
    rescue is reproduced exactly on the shipped arm (§7).
  - On B only b-hard2-s0039 has one (lead 7-11). On the shipped arm its
    baseline drops to -4, and one branch still reaches the threshold.
  - b-s0040, s0067 and s0083 have no rescue in the steps branched.
  - The same branching on crossings (margin 0 to +2) breaks them about twice as
    often as it rescues H: 27 % of distinct alternatives turn a crossing
    into a miss, 14 % turn an H miss into a crossing (`cf_flip.md`). Near
    the threshold the count moves by an item or more with almost any change.
- **Where one move helps, it is before the floor is gone.**
  - The last 1-3 placements rescue nothing, except on c-hard2-s0028, whose
    last box took the only spot the next, large item (0.8 x 0.6 x 0.5)
    needed.
  - The rescuing steps are 1-4 placements before "floor gone" (lead 8-15 on
    C).
  - The move that rescues is a box turned or put elsewhere on the floor (or
    on the shelf), not a better rescue pose at the end.
- **Orientation is not a separate lever.**
  - At the hard floor placements the agent stands the box as often on H as
    on the crossings: 42 % of 200 against 47 % of 113.
  - It lays the box while a standing pose survives the vetoes equally often
    (20 % and 20 %).
  - Those standing survivors would all stand in the shadow check (no tips).
    They lose on the max-footprint key's first term, the footprint.
  - In the branches, lying-to-standing rescues 3 of 12 distinct poses, and
    a lying box turned by 90 degrees 7 of 15 (`cf_orient.md`).
- **The shade veto -> rescue stage path** kills more floor per placement
  than the ladder's own picks, but is about as frequent on the crossings.
  - Floor killed per floor placement: 0.21 m^2 on H and 0.15 on the
    crossings, against 0.09 / 0.10 for a ladder pick that was played.
  - It happens on 22 of 237 H floor placements and 17 of 167 crossing floor
    placements.
  - It takes the last usable floor on 4 of 19 H boards (c-hard2-s0007,
    s0040, s0051, s0052) and 2 of 17 crossings.
  - Letting the shade-vetoed pick through at that step does not rescue:
    s0007 -1 -> -2, s0051 -4 -> -4, s0040 -12 -> -12 (§6).

**The typical "why" of a decisive move** (c-hard2-s0007, step 12, the
step before the floor is gone):

1. The max-footprint rung holds the B box (0.65 x 0.45 x 0.25) lying
   across and the same box turned (0.45 x 0.65). Both have footprint
   0.293.
2. The tie goes to the next key term, the row-waste bucket: 3 against 4
   (0.058 vs 0.074 m^2 of free floor stranded in the box's own x-rows). The
   shipped `row_waste_axes=x` does not see the depth left in front of the
   box.
3. The shipped pick leaves a front band in which the next box, a 0.75 x
   0.56, cannot lie. The ladder offers it standing at the door, and the
   shade veto refuses that (0.37 m^2 walled off). The stack option's poses
   on the tops are refused too (0.40).
4. The physics resort, which orders its poses by shade first, stands the
   box in the middle of the free floor. Usable floor goes 0.74 -> 0.00 in
   one step.
5. Turning the B box at step 12 crosses by +3. Five of the 8 alternatives
   at that step do, and all of them are reproduced on the shipped arm.

**Not established**

- That any rule would capture these rescues: the alternatives that rescue
  an H board break a crossing at a comparable or higher rate (§3).
- Whether "items per m^2 of floor" is a cause or a proxy for the small-item
  mixes and orders. It overlaps with the volume need, and the sample is
  small (§4).
- The farther misses (margin <= -4) were branched only around "floor
  gone".

## 1. Method

**Replays must use full-precision actions.** The bench records round
actions to 0.1 mm, and in the official simulator that moves the settled
poses.

- Replaying c-hard2-s0039 (`gate0det-hard2`) with the agent's own
  full-precision actions reproduces every settled pose to 0.0 m.
- The same actions rounded to 4 decimals move the first box by 2.4 mm, and
  the board by up to 5 cm by step 18 (`round_test.py`).
- Forced replays of the time-faithful B records fail on the recorded
  actions: b-hard2-s0039 at step 19 (transport), b-hard2-s0040 at step 23
  (settle) (`replay_check.py`).

**Reference runs (`ref.py`).** Each scene was played from the start with
its record's v50 arm plus `deterministic_budgets=true`: C with the arm of
`gate0det-hard2`, B with the arm of `gate0-hard2-b`. The full-precision
actions are kept, so every branch forces the reference's boards exactly.

At every step `ref.py` dumps:

- the agent's answer and its stage. The reason string separates the main
  ladder from the last resort's relaxed ladder; the record's `archetype`
  does not;
- the call's trace: every shadow verdict and shade reading, in order;
- the ladder recomputed on the agent's board: candidates, veto counts and
  rung orders, with the best poses' key terms, shade and a shadow verdict
  from a private ShadowSim;
- the floor before the step, with a 4 cm map.

Reference against the v50 record (placed):

- C: equal on 11 of 14. The exceptions are s0040 (34 vs 38), s0065 (66 vs
  85, ends on a settle) and s0073 (89 vs 93).
- B: equal on 3 of 7. The exceptions are s0040 (40 vs 41), s0066 (26 vs
  30), s0067 (68 vs 70) and s0080 (70 vs 96).
- All 21 still miss. The physics resort and the shadow keep their own
  clocks, so a deterministic run is not fully deterministic, and B is the
  most clock-sensitive.

**Branches (`cf.py`).** At step k:

1. the reference actions are forced for steps < k, and the pocket guard's
   stream statistics are fed (the one piece of cross-call state that
   changes decisions);
2. the placement at k is changed;
3. the agent (the same arm) plays to the end.

| kind              | what is played at k                                                                                                                                                                                                                                                                                             |
| ----------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `null`            | the agent's own answer: the baseline at that k (the reference up to the clocks)                                                                                                                                                                                                                                 |
| `veto<j>`         | the agent's (j+1)-th acceptable answer. The first j poses its shadow check would accept become hard vetoes, so the agent goes on as on a real veto (shadow alternatives, stack option, last resort, physics resort, grid rescue). This is the agent-consistent "next candidate", whatever stage placed the box. |
| `rung<r>`         | the r-th distinct pose of the ladder's chosen rung. `rung1` is the ladder's own pick when a downstream veto replaced it (for example the shade veto let through).                                                                                                                                               |
| `other:<rung>`    | the best pose of another rung                                                                                                                                                                                                                                                                                   |
| `vetoed:<reason>` | a shortlisted pose the ladder's vetoes removed (legal for the analytic validator)                                                                                                                                                                                                                               |
| `maxsurf<1,2>`    | hand-picked: of every legal pose of the item (all orientations; floor, shelf and tops; every container; the generator and validator, no vetoes), the two that leave the most usable surface (the taxonomy's 0.40 x 0.55 x 0.24 window over every level)                                                         |

Pose alternatives are applied without the agent's shadow check. "fails" in
the tables means the simulator refused the pose at k.

Branch steps:

- near misses (reference margin -3 to -1): the last 1 and 3 placements,
  the step that takes the last usable floor ("floor gone"), and 1, 2 and 4
  placements before it;
- farther misses and the control crossings: "floor gone" and 1 and 2
  placements before it.

"Usable floor" throughout means free floor covered by a free 0.58 x 0.43 m
window (the smallest hard box, 0.55 x 0.40, plus 3 cm). "Dead floor" is free
floor that is not usable.

## 2. Decision archaeology

**What places the floor boxes** (reference runs, `arch_stats.md` §1):

| group     | stage                    | floor placements | usable floor killed per floor placement |
| --------- | ------------------------ | ---------------: | --------------------------------------: |
| H         | ladder (its pick played) |              173 |                                   0.091 |
| H         | relaxed last resort      |               15 |                                   0.208 |
| H         | physics resort           |               15 |                                   0.163 |
| H         | stack option             |                9 |                                   0.142 |
| H         | shadow alternative       |                7 |                                   0.119 |
| crossings | ladder                   |              105 |                                   0.106 |
| crossings | physics resort           |               17 |                                   0.131 |
| crossings | relaxed last resort      |               10 |                                   0.127 |
| crossings | stack option             |               18 |                                   0.101 |

**The step that takes the last usable floor**, H reference runs
(`arch_stats.md` §2b). Item classes are as in `strips.py`: A = 0.55 x 0.40
x 0.24, B = 0.65 x 0.45 x 0.25, C = 0.75 x 0.56 x 0.27, H = 0.8 x 0.6 x 0.5.

| scene (margin) | step / of | item        | placed by                           | the ladder's own pick | usable floor lost (killed) |
| -------------- | --------- | ----------- | ----------------------------------- | --------------------- | -------------------------- |
| c-s0007 (-1)   | 13 / 20   | C           | physics resort, standing            | shade-vetoed          | 0.74 (0.53)                |
| c-s0039 (-1)   | 10 / 21   | prio-B      | ladder priority-edge                | played                | 0.61 (0.31)                |
| c-s0076 (-1)   | 13 / 21   | soft-prio F | stack option, standing              | none                  | 0.49 (0.41)                |
| c-s0078 (-3)   | 36 / 46   | C           | last resort any-container, standing | none                  | 0.37 (0.22)                |
| c-s0040 (-8)   | 18 / 34   | A           | relaxed last resort                 | shade-vetoed          | 0.77 (0.54)                |
| c-s0051 (-4)   | 14 / 20   | C           | physics resort, standing            | shade-vetoed          | 0.39 (0.25)                |
| c-s0052 (-5)   | 26 / 37   | C           | stack option                        | shade-vetoed          | 0.64 (0.23)                |
| c-s0062 (-4)   | 15 / 27   | B           | physics resort, standing            | none                  | 0.32 (0.21)                |
| c-s0066 (-5)   | 20 / 31   | prio-A      | ladder priority-edge                | played                | 0.32 (0.10)                |
| c-s0071 (-13)  | 31 / 48   | soft G      | ladder soft-edge                    | played                | 0.45 (0.27)                |
| c-s0073 (-16)  | 79 / 89   | B           | last resort any-container hole-fill | none                  | 0.73 (0.44)                |
| c-s0077 (-5)   | 10 / 16   | H           | ladder max-footprint                | played                | 0.84 (0.36)                |
| b-s0039 (-2)   | 13 / 20   | soft G      | ladder soft-edge                    | played                | 0.43 (0.25)                |
| b-s0040 (-2)   | 16 / 40   | prio-B      | ladder max-footprint                | played                | 0.69 (0.40)                |
| b-s0067 (-3)   | 59 / 68   | B           | ladder max-footprint, standing      | played                | 0.36 (0.20)                |
| b-s0062 (-4)   | 24 / 27   | C           | relaxed last resort, standing       | none                  | 0.53 (0.38)                |
| b-s0066 (-10)  | 24 / 26   | soft G      | stack option, standing              | none                  | 0.46 (0.38)                |
| b-s0080 (-37)  | 63 / 70   | prio-A      | ladder priority-edge                | played                | 0.39 (0.17)                |

c-s0028 and b-s0083 keep some usable floor to the end. The reference run of
c-s0065 ends on a settle.

**The recurring chain on C**:

- The back of the floor fills first (soft boxes on the soft-first orders,
  hard rows otherwise). The last free floor is a band at the door,
  0.5-0.6 m deep.
- A box placed in that band either takes most of it or leaves pieces
  narrower than 0.43 m beside or in front of it.
- When the next box is a large one (C or H class), the ladder has few
  floor candidates. At s0007 step 13 it considered 3 and vetoed 2 with
  `seals-usable-ground-behind`.
- Its pick at the door walls off lower floor behind it, and the shade veto
  refuses it.
- The rescue stages then take the box: the physics resort (shade bucket
  first, then the lowest pose, so a standing pose with a small shade in the
  middle of the band), or the relaxed last resort (what the strict margins
  refused).
- Either way the band is cut, and the usable floor goes to zero in one
  step.
- Then come 6-10 placements on the tops (count mode, physics resort, grid
  rescue) and a decline that takes 0.2-0.9 s: there is nothing left to try.

**The archaeology corrects three readings of the records:**

- **The record's `archetype` hides the stage.** In c-hard2-s0062, steps 11,
  12, 13 and 17 read "terrace-extension" / "wedge-step" in the record, but
  the strict ladder had no candidate there. They come from the last
  resort's relaxed ladder (reason "last-resort relaxed"). Over the H
  reference runs that is 72 placements, 15 of them on the floor.
- **Compaction moves the ladder's pick.** In c-hard2-s0039 at step 10 the
  priority-edge pick sat flush to the A box at x = 0.21, and
  `build_placement`'s compaction slid it 0.35 m to the left wall
  (x = -0.14). The 0.37 m gap now lies beside the A box instead of at the
  wall. It is dead either way, since the band is 0.82 m wide and the box
  0.45 m: the row-width mismatch in its plainest form.
- **The shadow's alternatives are tried in shortlist order.** On a shadow
  or shade veto, `_emit` tries `decision.survivors` in list order, which is
  the shortlist's depth-first order, not the rung's order (the loop over
  `decision.survivors` in `rule_alpha/agent.py`'s `_emit`; its docstring
  says "in the ladder's order").

## 3. Counterfactuals

Generated tables: `cf_stats.md` (per scene and step), `cf_flip.md`,
`cf_orient.md`. Margins are against the count threshold (>= 0 crosses).
"Lead" is the number of placements before the reference run's end.

**Near misses**:

| scene (ref margin) |   n | null at every k | rescuing steps (lead): what -> margin                                                                                                                                                                                                              | last 1-3 placements                                                                  |
| ------------------ | --: | --------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------ |
| c-hard2-s0007 (-1) |  20 | -1              | k=12 (8): the B box turned (veto2, veto3, rung4, vetoed:wall-front-strip) or standing (maxsurf2) -> +3, 5 of 8. k=11 (9): the soft-edge pick the pocket guard replaced (rung1) -> 0; maxsurf1 -> +2. k=9 (11): vetoed:would-wall-off-the-back -> 0 | none (k = 19, 17)                                                                    |
| c-hard2-s0028 (-1) |  13 | -1              | k=12 (1): 7 of 9; the A box on the shelf (vetoed:overhangs-the-shelf, maxsurf) -> +3, turned -> +2. k=8 (5): 5 of 9, up to +2. k=5 (8): the C box on the shelf -> +2 / +5                                                                          | k=12 rescues: the last box took the only spot the next item (0.8 x 0.6 x 0.5) needed |
| c-hard2-s0039 (-1) |  21 | -1              | k=10 (11, floor gone): the prio-B box turned to 0.65 x 0.45 (vetoed by corridor / wall-front-strip, or maxsurf2) -> 0. k=8 (13): the soft E lying (veto1) -> +1. k=6 (15): the A box on the floor instead of on the shelf top (veto1) -> +3        | none                                                                                 |
| c-hard2-s0076 (-1) |  21 | -1              | k=13 (8, floor gone): veto2 -> 0. k=11 (10): the soft G turned (maxsurf) -> 0. k=9 (12): veto2 -> 0                                                                                                                                                | none                                                                                 |
| c-hard2-s0078 (-3) |  46 | -3              | k=36 (10, floor gone): the C box raised onto the tops (maxsurf1) -> 0                                                                                                                                                                              | none                                                                                 |
| b-hard2-s0039 (-2) |  20 | -2              | k=13 (7): veto2 / rung3 -> 0. k=11 (9): maxsurf2 -> 0. k=9 (11): maxsurf1 -> +2                                                                                                                                                                    | none                                                                                 |
| b-hard2-s0040 (-2) |  40 | -2              | none (k = 39, 37, 16, 15, 14, 12; the pose alternatives at the terraces fail at k or collapse later)                                                                                                                                               | none                                                                                 |
| b-hard2-s0067 (-3) |  68 | -3 / -4         | none (best -2)                                                                                                                                                                                                                                     | none                                                                                 |
| b-hard2-s0083 (-2) |  58 | -2              | none (k = 57, 55, 53, 50; every branch -2)                                                                                                                                                                                                         | none                                                                                 |

**Farther misses** (branched around "floor gone"; partial, the batch was
still running):
- c-hard2-s0051 (-4): no rescue at k = 14, 13 or 12.
- c-hard2-s0040 (reference -8): rescued one and two placements before
  "floor gone". At k = 17, `rung2` reaches 0 against the null's -12; at
  k = 16, `rung3` reaches 0 against the null's -7. The null baselines at
  these steps scatter (-12, -12, -7 against the reference's -8): the resort
  clock again.

So a single change can bring even a -8 board to the threshold.

**By kind of alternative** (distinct poses, `cf_flip.md`), on H:

- the hand-picked most-usable-surface poses rescue 10 of 41;
- poses the ladder vetoed: 5 of 25;
- the agent's next answer (`veto<j>`): 8 of 85;
- the shade-vetoed ladder pick let through (`rung1`): 1 of 12.

**The control: the same branching on crossings.** Crossings at margin 0
to +2 (c-hard2-s0026, s0074, s0058, s0050, s0014 and b-hard2-s0051, s0058, s0076)
were branched around "floor gone":

|                                      | distinct branches |      flips |              share |
| ------------------------------------ | ----------------: | ---------: | -----------------: |
| H: miss -> crossing | 187 | 26 | 0.14 |
| crossings: crossing -> miss | 71 | 19 | 0.27 |
| H, by lead 1-3 / 4-9 / >= 10 | 45 / 61 / 81 | 5 / 12 / 9 | 0.11 / 0.20 / 0.11 |
| crossings, by lead 1-3 / 4-9 / >= 10 | 8 / 31 / 32 | 0 / 13 / 6 | 0.00 / 0.42 / 0.19 |

- The most-usable-surface poses that rescue H boards break crossings at
  43 % (10 of 23).
- The mean margin change is near zero in both groups (H -0.77, crossings
  +0.23).
- So one changed placement near "floor gone" is a coin toss on these
  boards. It is not a correction the ladder systematically misses.

**How far back**:

- C near misses: 1 placement for c-s0028 (an item-specific end, see §8),
  8-15 for the others. In every C case the rescuing step lies within 4
  placements before "floor gone".
- After the floor is gone, changes rescue nothing on C, except where a
  usable patch was still there for the next item (c-s0028).
- B: 7 placements for b-s0039, none found for s0040, s0067 or s0083.

## 4. Strip formation in general

Sources: `strip_stats.md` (records `gate0-hard2` and `gate0-hard2-b`,
commanded boxes), `need_stats.md`, `gone_stats.md`.

**Who kills the usable floor** (usable floor turned dead without being
covered; H / crossings):

- share of the kill by rung: C max-footprint 0.46 / 0.33, physics resort
  0.21 / 0.19, stack option 0.08 / 0.12, soft-edge 0.05 / 0.11; B
  max-footprint 0.75 / 0.66;
- per placement each rung kills the same in both groups: max-footprint
  0.10 on C, 0.12 / 0.11 on B; physics resort 0.041 / 0.041;
- share by item class and pose: hard lying 0.43 / 0.32 (C), hard standing
  0.29 / 0.40 (C), priority lying 0.10 / 0.04 (C) and 0.17 / 0.07 (B).

**What kind of strip.** The killed strips look the same in every group
(H, G, D, crossings):

- direction: 51-58 % narrow in y (depth left over in front of or behind a
  row: the row-width mismatch), 42-49 % narrow in x (beside a box or at a
  side wall);
- bounds: wall-box 47-55 %, box-box 45-52 %;
- position relative to the new box: in front of it (door side)
  0.26-0.35, beside it 0.37-0.48, behind it 0.10-0.21;
- width: 0.3-0.45 m is the largest class (0.28-0.36 of the area), pieces
  a 0.40 m box would almost fit.

**The suspected causes, measured:**

- wall-gap leftovers: half of the dead floor is bounded by a wall, on H as
  on the crossings;
- row widths not matching the container: the narrow-in-y majority;
- mixed-depth rows: not separately measurable here (box-box strips are
  45-52 %);
- the shadow-veto fallback (the shadow's replacement pose): 0.12 m^2 per
  floor placement on H against 0.06 on the crossings, on 7 and 8
  placements;
- the physics resort's poses: 0.16 / 0.13 per floor placement.

None of them is H-specific in rate. H differs in when the floor runs out
relative to the count it needs.

**Matched need.** At the same need (the volume of the first threshold
items), H loses its floor at a lower fill: need 0.38-0.44, 0.18 vs 0.34;
need 0.44-0.51, 0.30 vs 0.41. When the floor went, the H boards had fewer
raised boxes (C 8-12 against 18-24) and lower floor boxes (mean height
0.28-0.37 m against 0.37-0.39).

## 5. Orientation as a lever

Sources: `orient.py` at every hard floor placement of the reference runs
(`orient_stats.md`), and the branches by kind of change (`cf_orient.md`).

|                                                             |         H | crossings |
| ----------------------------------------------------------- | --------: | --------: |
| hard floor placements                                       |       200 |       113 |
| the agent stood the box                                     | 83 (42 %) | 53 (47 %) |
| a legal standing floor pose existed (generator + validator) |       148 |        82 |
| a standing pose survived the ladder's vetoes                |       116 |        64 |
| the agent laid the box although a standing survivor existed | 40 (20 %) | 23 (20 %) |
| those standing survivors: shadow ok / would tip or slide    |    40 / 0 |    23 / 0 |
| their rank in the chosen rung: 2-3 / 4-10                   |    6 / 34 |    4 / 19 |

**Why standing loses.** The chosen rung is mostly max-footprint, whose key
starts with the footprint. A standing pose has the smaller footprint, so it
ranks below every lying pose of the item.

**What removes the shortlisted standing poses** (counts on H; the
crossings show the same order):

- reserved-zone 460, wall-front-strip 241, seals-usable-ground-behind 184;
- would-wall-off-the-back 107, blocks-wedge-approach 84,
  low-footprint-pose 78;
- free-standing-tipping-risk 54, front-would-stand-too-tall 29.

The tipping and standing-height vetoes remove few.

**Do standing alternatives rescue?** Distinct alternative poses of the
same item on the floor:

- lying -> standing: 3 of 12 rescue, mean margin +0.67 against the null;
- the same box turned by 90 degrees and still lying: 7 of 15, +0.60;
- the same orientation moved: 1 of 27, -0.15;
- any raised alternative: 15 of 90, -1.78.

**Topples.** A standing pose covers less floor: its usable-floor loss is
about half the lying pose's at the same step. But the agent already stands
boxes as often on H as on the crossings. The platform has priced standing
boxes before: in v13 the standing boxes on the fourth level were 9 of 15
topples, and v19 capped them. These replays score the count only, with the
shadow's settle check but not the shake.

**Reading.** The orientation choice is the same policy on H and on the
crossings. A different orientation at the decisive step can rescue (the
turned box at c-s0007 step 12, the turned prio-B at c-s0039 step 10). That
is the same two-sided sensitivity as in §3, not a lack of standing boxes.

## 6. The shade veto -> rescue stage path

**Frequency** (`arch_stats.md` §2a): floor placements where the strict
ladder's own pick was refused by the shade veto (shade > 0.15 m^2).

- H: 22 of 237 floor placements, killing 4.68 m^2 (0.21 per placement,
  0.22 per episode).
- Crossings: 17 of 167, killing 2.55 m^2 (0.15 per placement, 0.15 per
  episode).
- For comparison, a ladder pick that was played kills 0.086 (H) and 0.101
  (crossings) per floor placement.

**At the last usable floor.** The path takes it on 4 of 19 H boards
(c-hard2-s0007, s0040, s0051, s0052) and 2 of 17 crossings (c-hard2-s0067,
s0079). The box is placed by the physics resort twice, the relaxed last
resort once and the stack option once on H; by the stack option once and
the physics resort once on the crossings.

**Branch: let the shade-vetoed pick through at that step** (`rung1`, the
ladder's pick applied as is):

- c-hard2-s0007 step 13: -1 -> -2. The pick stands the C box at the front
  right and walls off the band behind it.
- Over all steps where `rung1` exists it rescues 1 of 12 distinct poses on
  H. The one rescue is c-s0007 step 11, where `rung1` is the soft-edge pick
  the pocket guard replaced, not a shade veto. It breaks 2 of 4 on the
  crossings.
- c-hard2-s0051, at the floor-gone step (k = 14) and two before it
  (k = 12): `rung1` -4 against the null's -4 at both steps (no change).
- c-hard2-s0040, at the floor-gone step (k = 18): `rung1` -12 against the
  null's -12 (this replay's baseline is 4 below the reference's -8, clock
  noise).
- So in the three boards measured, letting the shade-vetoed pick through
  at the step that takes the last floor rescues nothing (s0007 -1 -> -2,
  s0051 -4 -> -4, s0040 -12 -> -12). s0052 was still running when this was
  written; its result is in `cf_stats.md` if it finished.
  `cf_stats.md`.

The veto is doing its job: the floor it protects really would be walled
off. Its fallback, the resort's shade-first order, is what cuts the floor,
but the alternatives at that step are no better. On s0007 the board had
been decided one step earlier.

## 7. Shipped-form confirmation

The bench records and the reference runs use the v50 bench arm. The shipped
`submission/agent.py` differs in three settings:

- `stack_deadline` is on;
- `rescue_order_gate` is low+single, so the shipped B does not run the
  deep-first / sealing pass that the bench's B ran;
- `soft_headroom_volume_share` is 0.9 instead of 0.75.

Every rescuing branch was re-run, together with its baseline, from the same
prefix with `arm_ship_c.txt` / `arm_ship_b.txt` (taken from
`origin/claude/rl-packing-policy-ftogt3` 9e4ada85, plus deterministic
budgets). See `ship_confirm.py` and the last section of `cf_stats.md`.

| scene         |         k | baseline: record arm / shipped arm | rescuing branches: record arm / shipped arm                                                                  |
| ------------- | --------: | ---------------------------------- | ------------------------------------------------------------------------------------------------------------ |
| c-hard2-s0007 |        12 | -1 / -1                            | veto2, veto3, rung4, vetoed:wall-front-strip, maxsurf2: +3 / +3 each                                         |
| c-hard2-s0007 |        11 | -1 / -1                            | rung1 0 / 0; maxsurf1 +2 / +2                                                                                |
| c-hard2-s0007 |         9 | -1 / -1                            | vetoed:would-wall-off-the-back 0 / 0                                                                         |
| c-hard2-s0028 |        12 | -1 / -1                            | veto2 +2 / +2; rung2, rung3, other:front-wedge 0 / 0; vetoed:overhangs-the-shelf, maxsurf1, maxsurf2 +3 / +3 |
| c-hard2-s0028 |         8 | -1 / -1                            | veto2, rung3, other:back-corner 0 / 0; vetoed:overhangs-the-shelf, maxsurf1 +2 / +2                          |
| c-hard2-s0028 |         5 | -1 / -1                            | vetoed:overhangs-the-shelf +2 / +2; maxsurf1 +2 / +2; maxsurf2 +5 / +5                                       |
| c-hard2-s0039 |        10 | -1 / -1                            | three poses 0 / 0                                                                                            |
| c-hard2-s0039 |         8 | -1 / -1                            | veto1, vetoed:wall-front-strip +1 / +1                                                                       |
| c-hard2-s0039 |         6 | -1 / -1                            | veto1, vetoed:wall-front-strip +3 / +3                                                                       |
| c-hard2-s0076 | 13, 11, 9 | -1 / -1                            | veto2 0 / 0; maxsurf1, maxsurf2 0 / 0; veto2 0 / 0                                                           |
| c-hard2-s0078 |        36 | -3 / -3                            | maxsurf1 0 / 0                                                                                               |
| b-hard2-s0039 |        13 | -2 / -4                            | veto2 0 / -4; rung3 0 / -4                                                                                   |
| b-hard2-s0039 |        11 | -2 / -4                            | maxsurf2 0 / -1                                                                                              |
| b-hard2-s0039 |         9 | -2 / -4                            | maxsurf1 +2 / 0                                                                                              |

- On C every rescue and every baseline is identical on the shipped arm.
- On B the shipped baseline of b-hard2-s0039 is -4, not -2. That matches
  the shipped-form record (18 placed, -4). Only maxsurf1 at k = 9 still
  reaches the threshold.

**The shipped-form records** (`ship-hard2`, `ship-hard2-b`, landed on
`origin/claude/rl-packing-policy-ftogt3`; `ship_compare.md`):

- C: the 14 H scenes place exactly what v50 placed, except c-hard2-s0065,
  which crosses (87, +1). Its reference run ended on a settle at 66: it is
  a clock-sensitive scene, not an H board.
- B, against v50:
  - lower: b-s0039 (-4), b-s0040 (-4), b-s0080 (-28 against -11);
  - higher: b-s0062 (-3);
  - equal: b-s0066, b-s0067, b-s0083.

## 8. Surprises and evidence against the labels

- **The H boards are not the strip boards: every geometry miss and every
  crossing ends in strips** (§4). Strips are the normal end state of this
  ladder on these containers. The C crossings end with 1.04 m^2 of dead
  floor, H with 0.91.
- **"No level patch" is item-specific.** Some H boards still have usable
  surface for a 0.40 x 0.55 x 0.24 window at the final decline:
  - c-hard2-s0028: 0.71 m^2 of usable surface, 0.27 m^2 of usable floor;
  - c-hard2-s0052: 0.28 + 0.41 m^2;
  - c-hard2-s0039: 0.29 m^2.

  The declined item was the 0.8 x 0.6 x 0.5 box at s0028, s0052 and s0007
  (s0007 has no usable surface), and a 0.75 x 0.56 at s0039. At
  c-hard2-s0028, changing the very last placement crosses in 7 of 9
  branches. "Tops closed" holds for about 15 of the 20 reference runs, not
  all of them.

- **H is partly a count-per-floor phenomenon.** The taxonomy's "need" is a
  volume. The H scenes stand out more by the number of items the threshold
  asks per m^2 of floor (13-15 against about 9.5) and by their smaller
  items.
- **The label moves with the clock.** c-hard2-s0065 is H in the v50 record
  (-1), ends on a settle at -20 in the deterministic reference run, and
  crosses in the shipped-form record (+1). b-hard2-s0080 is -11, -37 and
  -28 in the same three runs.
- **Replay caveats found along the way:**
  - the records' rounded actions cannot replay the boards (§1);
  - the record's archetype does not tell the main ladder from the relaxed
    last resort (§2);
  - compaction can move a pick by 35 cm (§2).
- **The count threshold estimate.** The agent estimates 41 items per
  container, so a threshold of 21 per container. On most H scenes that is
  below the true threshold: c-s0040 21 against 42, c-s0065 62 against 86,
  b-s0067 42 against 71. At the end the boards are in the low phase, where
  `_under_count` returns true anyway, so it probably does not change the
  end. Not measured.

## 9. Open questions

- **A rule that keeps the rescues?** Is there a decision rule that takes the
  H rescues without paying the crossing breaks? The same alternatives break
  27 % of the crossings near the threshold, so any rule must be measured on
  whole suites, not on the misses.
- **A denser floor phase?** Can the floor hold more small items per m^2?
  - The H scenes need 13-15 items per m^2. In every group the agent holds
    about 8-9 at "floor gone" and stacks about 8-10 more after it.
  - Not tested: whether a denser floor tiling of the small classes is
    reachable online. The depth remainder of the rows is 51-58 % of the
    dead floor.
  - `row_waste_axes=xyn` was measured before and lost on B (findings,
    "The floor reservation by the stream").
- **Clock noise.** How much of the H count is it? Three of the 21 scenes
  change sign or magnitude between the time-faithful record, the
  deterministic reference and the shipped-form record (c-s0065, b-s0066,
  b-s0080).
- **Shipped B.** Do the shipped-form B boards have different decisive
  steps? From the same prefix, the shipped B baseline of b-s0039 drops by
  two items.

## Scripts and outputs (`reports/wedge/hard2-H-strips/`)

| file                                                                   | what                                                                                                                                                                  |
| ---------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `harness.py`                                                           | branching harness over the official simulator (and the analytic model): forced prefixes (record or full-precision actions), probes, alternative actions               |
| `hlist.py`, `hlist.json`                                               | the 21 H episodes from the taxonomy's tables, with the agent's own count-threshold estimate                                                                           |
| `strips.py`                                                            | per-step floor rebuild from a record: usable and dead floor, killed strips with their geometry (direction, bounds, position, width), usable surface (data in scratch) |
| `strip_stats.py` -> `strip_stats.md`                                   | strip formation by group, rung, class and pose                                                                                                                        |
| `need_stats.py` -> `need_stats.md`; `gone_stats.py` -> `gone_stats.md` | the floor phase against the need, items per m^2, "floor gone"                                                                                                         |
| `diverge.py`                                                           | the same scene where it crosses (v49 det against v50 det, C against B)                                                                                                |
| `round_test.py`, `replay_check.py`                                     | the replay-precision checks                                                                                                                                           |
| `ref.py`                                                               | reference runs with per-step archaeology dumps (scratch `ref/`)                                                                                                       |
| `arch.py`, `arch_rounded.py`                                           | dump helpers; the first archaeology on rounded record actions (superseded)                                                                                            |
| `arch_report.py`                                                       | the run-in of one reference run as a table, with floor maps                                                                                                           |
| `arch_stats.py` -> `arch_stats.md`                                     | stages, refusals of the ladder's pick, floor-gone steps, floor-killing steps, per-episode run-downs                                                                   |
| `cf.py`, `run_cf.py`                                                   | counterfactual branches (scratch `cf/`)                                                                                                                               |
| `cf_stats.py` -> `cf_stats.md`, `cf_summary.json`                      | branch tables and the shipped-form confirmation                                                                                                                       |
| `cf_flip.py` -> `cf_flip.md`; `cf_orient.py` -> `cf_orient.md`         | flips, H against the crossings; branches by the kind of change                                                                                                        |
| `orient.py`, `orient_stats.py` -> `orient_stats.md`                    | standing alternatives at the hard floor placements                                                                                                                    |
| `ship_confirm.py`, `arm_ship_c.txt`, `arm_ship_b.txt`                  | re-running the rescues on the shipped arm                                                                                                                             |
| `ship_compare.py` -> `ship_compare.md`                                 | the H scenes in the shipped-form records                                                                                                                              |
