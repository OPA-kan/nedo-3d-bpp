# The hard2 misses: a taxonomy

Deep-dive over the recorded hard2 runs (nothing rerun). The 53 v50 C misses and
48 v50 B misses sort into seven causes. A quarter of them are volume misses: the
scene needs more fill than any crossing ever reached, so no placement change
recovers them. The rest are geometry misses, and the largest group is boards
that end with the floor in strips and no level surface left.

Scripts, extracted data and the full per-episode tables are in
`reports/wedge/hard2-miss-taxonomy/` (`extract.py`, `classify.py`,
`course.py`, `nextfit.py`, `validate_reach.py`; `tables.md` holds every table
including a row per v50 C and B miss, `course.md` the course statistics by
cause).

Records read:
- **v50:** `gate0-hard2` (C), `gate0-hard2-b` (B) and its replicate `gate0-hard2-b-r2`.
- **v49:** `bandnt-hard2` and `bandnt-hard2-b`.
- **Deterministic pair:** `bandntdet-hard2` (v49) against `gate0det-hard2` (v50).

Every board was rebuilt from the settled poses in `final_items`, with the scene
rebuilt by `make_scene`.

## Summary

- **Volume misses: 25 % of the misses, 55-60 % of the missing items.** "Need" is
  the volume of the first threshold items divided by the simulator's container
  volume (the `fill_volume` basis). The highest need any crossing met in any
  record is 0.506 (c-hard2-s0083). Above it are 13 C episodes (all 8 fill-only
  scenes and 5 of the 8 edge scenes), short by 14-204 items (mean -45, 583 items
  in total). B has 12 (536 items).
- **Geometry misses: the other 40 C and 36 B episodes (381 and 453 items).**
  They stop at a fill of 0.35 with 65 % of the volume free. The volume still
  needed to cross was only 0.07 of the container (medians). At the end they all
  look alike:
  - 30-36 % of the floor is free, but in strips: the largest empty rectangle is
    0.19-0.35 m wide.
  - 0.5-1.0 m² of the free floor lies in pieces narrower than 0.3 m.
  - Usable top surface is 0.00-0.05 of the floor.

**Ranked causes (v50; "within 3" means a margin of -1 to -3):**

| rank | cause | C episodes (items short) | B episodes (items short) | within 6 C / B | within 3 C / B | where | lever |
|---:|---|---|---|---|---|---|---|
| 1 | **H no level patch: floor in strips, tops closed** | 14 (60) | 7 (27) | 12 / 6 | 6 / 4 | C: 10 of 14 stretch; 9 of 14 need 0.44-0.506 | Packing density. The board packs to about 0.38 and closes. These are the cheapest crossings (mean margin -4.3 C, -3.9 B). |
| 2 | **G a level patch is left but sealed from the door** | 9 (79) | 14 (137) | 5 / 7 | 2 / 4 | sample, stretch, 2 edge | The travel path from the door to every spot that would hold a visible item is blocked (door-side sealing). |
| 3 | **D soft carpet** (soft boxes cover ≥ 40 % of the floor) | 10 (149) | 8 (125) | 3 / 1 | 3 / 0 | small-first or soft-first order: C 9 of 10, B 8 of 8 | Where soft cargo goes in the soft-early orders. The soft-edge rung makes the largest usable-surface drop in 6 of 10 C and 8 of 8 B carpets. |
| 4 | **B ended by the simulator** (settle or transport) | 3 (29) | 4 (130) | 1 / 0 | 0 / 0 | C: sample; B: mostly stretch | The 3 on C all cross in the deterministic run, so they are clock noise. On B, b-hard2-s0037 settles at step 9 of 33 in all three B records; C crosses that scene by +11. |
| 5 | **C a container left under-used** (C only) | 2 (38) | 0 | 0 / 0 | 0 / 0 | sample | See below. |
| 6 | **E/F a reachable patch left untaken** | 2 (26) | 3 (34) | 1 / 1 | 1 / 0 | | Generators or time; small. |
| 7 | **A volume out of reach** | 13 (583) | 12 (536) | 0 | 0 | fill-only 8, edge 5 (C) / 4 (B) | None by placement. |

On c-hard2-s0005 (cause C), the priority container holds 11 items at fill 0.13
with 68 % of its floor still usable, while soft carpets fill the other two
containers. On the same scene B puts 30 items in that container. Soft cargo
enters the priority container only through the last resort's any-container
stage, which the 4.5 s declining call did not reach. The other cause-C
episode, s0042, crosses in the deterministic run.

- **Almost nothing is recoverable by the requested test** (within 3 and a
  legal-looking, reachable spot for a visible item). Only c-hard2-s0036 (D) and
  c-hard2-s0043 (F) qualify on C, none on B (2 in the B replicate).
  - The near misses end on closed boards: 12 on C (H 6, D 3, G 2, F 1) and 8 on
    B (G 4, H 4).
  - On the H boards the declining C call takes 0.6 s (median): there is nothing
    left to try.
  - One more item needs a different board, not a better search at the last call.
- **What the pool buys** (same seeds, v50):
  - 35 scenes cross on both tasks, 13 miss only on C, 8 only on B. B nets +5
    crossings (sample +2, stretch +3) and +0.65 items a scene.
  - C-only misses: G 5, H 5, the 2 clock-noise settle endings, and s0042
    (container under-used). On 7 of the 14 C boards that end with no level
    patch, one of the next ten stream items does have a reachable spot, so a
    pool would have helped there.
  - B-only misses are mostly G (6 of 8). At its final decline B usually still
    holds level patches it cannot reach: 26 of the 48 B crossings end that way,
    against 6 of 40 on C.
  - On the 40 scenes both tasks miss, B places 1.05 items fewer than C.
- **Noise and attribution:**
  - **Clock noise (C).** 5 misses occur only in the time-faithful run: the 3
    settle endings, s0036 and s0042. One occurs only in the deterministic run:
    s0048. So about 5 of the 15 v50 C sample misses are course noise under the
    clock.
  - **B replicate.** It swaps 2 crossings for 2.
  - **The gate (v49 to v50, deterministic pair).** It gains 4: s0010, s0014 and
    s0036 (all soft carpets) and s0021. It loses 5: s0004 (carpet), s0007,
    s0040 and s0076 (strips), and s0059. Soft-carpet misses go from 16 to 14,
    so the carpet survives the gate.

## 1. How far, and volume or geometry

Margin histogram (episodes, with items short in brackets):

| record | -1 | -3..-2 | -6..-4 | -15..-7 | <= -16 |
|---|---:|---:|---:|---:|---:|
| `gate0-hard2` | 8 (8) | 4 (11) | 10 (48) | 10 (107) | 21 (790) |
| `gate0-hard2-b` | 5 (5) | 3 (6) | 7 (34) | 12 (144) | 21 (800) |
| `gate0det-hard2` | 5 (5) | 6 (15) | 8 (37) | 9 (94) | 21 (762) |
| `bandntdet-hard2` | 5 (5) | 3 (9) | 10 (46) | 9 (93) | 21 (784) |

Need is about 1.18 times the spec's `demand` because it uses the simulator's
container volume. The B and C scenes have identical items, so the need is the
same for both. Crossing rate by need:

| need | <0.34 | .34-.38 | .38-.40 | .40-.42 | .42-.44 | .44-.46 | .46-.48 | .48-.50 | .50-.55 | ≥.55 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| C v50 | 14/17 | 12/18 | 8/13 | 3/5 | 0/4 | 1/7 | 4/13 | 0/4 | 1/6 | 0/9 |
| C v50 det | 15/17 | 16/18 | 7/13 | 3/5 | 0/4 | 1/7 | 4/13 | 0/4 | 1/6 | 0/9 |
| B v50 | 15/17 | 15/18 | 5/13 | 4/5 | 1/4 | 2/7 | 4/13 | 1/4 | 1/6 | 0/9 |

- **The volume line.** The agent's final fill reaches p90 0.46 and a maximum of
  0.56. No crossing had a need above 0.506 (b-hard2-s0087 tops B at 0.500).
- **Fill at the threshold.** On C it is the placed volume plus the next items up
  to the threshold. On B it is the smallest choice within the pool window.
  Above 0.506 the miss is a volume miss.
- **Geometry misses.** They end at a fill of 0.35 with 0.07 still needed (C
  medians; B 0.33 and 0.075), and 0.65 / 0.67 of the volume free.

## 2. The rules (applied in order; the first match is the cause)

| code | cause | rule |
|---|---|---|
| A | volume out of reach | fill at the threshold > 0.506 |
| B | ended by the simulator | `end_reason` is settle or transport |
| C | container left under-used | more than one container, and some container has usable tops ≥ 0.25 of its floor while its fill is ≤ 0.6 of the fullest container's |
| D | soft carpet | soft footprints on the floor (bottom < 0.10 m) cover ≥ 0.40 of the total floor area |
| E | reachable patch, call ran out of time | some visible item has a reachable spot, and the declining call took ≥ 5.0 s (C) or ≥ 7.0 s (B), i.e. into the extra time past the 4.5 s budget |
| F | reachable patch, not taken | the same, with a shorter call |
| G | patch sealed from the door | some visible item has a level spot, but no spot has a clear travel path |
| H | no level patch | no level spot for any visible item |

- **Visible items.** On C, the next item. On B, the first `pool` unplaced items.
- **Level spot.** The usable-surface model in `rule_alpha/surface.py`, applied
  to the item's own footprint and height in all orientations. It needs:
  - a support level within 2 cm (hard tops, floor or shelf);
  - room for the footprint plus 3 cm, and the height plus 3 cm free above it;
  - the chamfer limit respected.
  - For a soft item, soft tops also count as support as long as the result
    stays under 0.7 m.
- **Reachable.** The spot is level, and the simulator's travel path is clear of
  packed boxes. That path is:
  - a move inward from the door at transport height (bottom +0.08 m, or
    +0.02 m on the floor or a shelf, capped under the ceiling);
  - plus a sideways move when the target is in the chamfer pocket.
- **Secondary tags** (these do not change the cause): vol-stretched (need
  0.44-0.506), soft-early (small-first or soft-first order), big-first,
  time-cut, early-collapse (one placement drops the usable surface by ≥ 0.2 of
  the floor with ≥ 10 placements still to come), ctr-underused,
  patch-reachable, patch-sealed.

**How strict the spot checks are** (`validate_reach.py`). Run against 336 items
the agent actually placed (the last 10 placements of every third episode, seeds
1-49, C and B):
- The level check finds a spot for 79 % of them and the reachable check for
  65 %.
- For the ladder's rungs it finds one about 100 % of the time. For the rescue
  stages it is 30-70 % (count-mode 13 of 45, grid-rescue-cover 6 of 21),
  because they place with less than full support or less than 3 cm clearance.
- So a spot found means a comfortable pose exists, up to stability and
  clearance margins. "No spot" (G, H) does not prove there is no legal pose.

## 3. Cause counts across records (episodes, items short in brackets)

| cause | C v50 | C v50 det | C v49 | C v49 det | B v50 | B v50 r2 | B v49 |
|---|---:|---:|---:|---:|---:|---:|---:|
| A | 13 (583) | 13 (560) | 13 (575) | 13 (571) | 12 (536) | 12 (520) | 12 (547) |
| B | 3 (29) | 2 (49) | 3 (38) | 1 (12) | 4 (130) | 2 (69) | 7 (207) |
| C | 2 (38) | 0 | 1 (7) | 0 | 0 | 0 | 1 (63) |
| D | 10 (149) | 9 (122) | 10 (167) | 12 (147) | 8 (125) | 7 (129) | 7 (135) |
| E | 0 | 2 (18) | 1 (32) | 0 | 1 (6) | 0 | 0 |
| F | 2 (26) | 2 (37) | 0 | 2 (80) | 2 (28) | 5 (42) | 2 (22) |
| G | 9 (79) | 9 (90) | 7 (52) | 7 (62) | 14 (137) | 14 (131) | 15 (108) |
| H | 14 (60) | 12 (37) | 14 (90) | 13 (65) | 7 (27) | 8 (29) | 5 (15) |
| all | 53 (964) | 49 (913) | 49 (961) | 48 (937) | 48 (989) | 48 (920) | 49 (1097) |

The mix is stable across forms, replicates and the clock: entries move by 1-3.
The exception is B's settle endings: 7 under v49, 4 and 2 under v50.

Strata by cause, v50:
- **C:** sample 15 (B 3, C 2, D 3, F 1, G 2, H 4); stretch 23 (D 7, F 1, G 5,
  H 10); edge 7 (A 5, G 2); fill-only 8 (A 8).
- **B:** sample 13 (B 1, D 4, F 1, G 5, H 2); stretch 20 (B 3, D 4, E 1, G 7,
  H 4); edge 7 (A 4, G 2, H 1); fill-only 8 (A 8).

Scenes by cause (margin):
- **C v50:**
  - A: s0085 -14, s0090 -19, s0094 -19, s0095 -23, s0096 -23, s0088 -27, s0084 -28, s0086 -38, s0092 -40, s0089 -41, s0082 -46, s0093 -61, s0091 -204
  - B: s0020 -5, s0044 -8, s0021 -16
  - C: s0042 -7, s0005 -31
  - D: s0006 -1, s0036 -1, s0004 -2, s0053 -7, s0069 -12, s0072 -17, s0049 -21, s0075 -23, s0061 -27, s0068 -38
  - F: s0043 -3, s0080 -23
  - G: s0059 -1, s0027 -3, s0013 -4, s0060 -6, s0063 -6, s0055 -11, s0081 -11, s0087 -12, s0070 -25
  - H: s0007, s0028, s0039, s0065, s0076 (all -1), s0078 -3, s0040 -4, s0051 -4, s0062 -4, s0052 -5, s0066 -5, s0077 -5, s0073 -12, s0071 -13
- **B v50:**
  - A: s0085 -16, s0094 -17, s0096 -17, s0090 -19, s0084 -24, s0095 -25, s0088 -27, s0092 -44, s0089 -46, s0082 -65, s0093 -70, s0091 -166
  - B: s0063 -18, s0037 -24, s0070 -43, s0061 -45
  - D: s0036 -4, s0006 -9, s0069 -10, s0005 -15, s0072 -15, s0049 -21, s0068 -25, s0043 -26
  - E: s0053 -6
  - F: s0044 -14, s0065 -14
  - G: s0007 -1, s0009 -1, s0077 -1, s0026 -2, s0064 -4, s0004 -5, s0081 -5, s0056 -8, s0030 -9, s0055 -10, s0073 -14, s0071 -15, s0075 -18, s0086 -44
  - H: s0040 -1, s0067 -1, s0039 -2, s0083 -2, s0062 -4, s0066 -6, s0080 -11

## 4. The end and the course by cause (v50, medians)

| C cause | n | fill / fill needed | free floor | narrowest side of largest empty rect (m) | strip floor (m²) | usable tops | soft / priority floor share | level / reachable spot | largest drop / placements before end | low-phase lead | rescue share | low_steps | shadow vetoes / replaced / skipped | last call (s) | policy max (s) | over-budget steps |
|---|---:|---|---:|---:|---:|---:|---|---|---|---:|---:|---:|---|---:|---:|---:|
| A | 13 | .39/.74 | .28 | .20 | .91 | .00 | .21/.00 | 2/2 | .14/17 | 14 | .27 | 23 | 27/0/0 | 1.7 | 5.0 | 4.4 |
| B | 3 | .27/.34 | .35 | .22 | .87 | .10 | .41/.00 | 3/3 | .22/8 | 3 | .17 | 9 | 21/0/0 | 5.2 | 5.2 | 2.3 |
| C | 2 | .26/.34 | .39 | .77 | 1.29 | .26 | .33/.10 | 2/2 | .09/32 | – | .16 | 28 | 23/2/0 | 5.4 | 6.0 | 1.5 |
| D | 10 | .34/.43 | .32 | .19 | .64 | .00 | .58/.00 | 4/2 | .17/17 | 12.5 | .20 | 18 | 20.5/0/0 | 3.2 | 5.5 | 6.1 |
| F | 2 | .32/.38 | .36 | .19 | 1.88 | .00 | .35/.08 | 2/2 | .10/20.5 | 23.5 | .13 | 54.5 | 46.5/1.5/10.5 | 4.8 | 6.5 | 11.5 |
| G | 9 | .40/.46 | .30 | .30 | .75 | .04 | .05/.18 | 9/0 | .17/20 | 14 | .29 | 28 | 29/2/0 | 1.6 | 4.0 | 1.3 |
| H | 14 | .38/.46 | .30 | .22 | .62 | .00 | .08/.08 | 0/0 | .19/11.5 | 11 | .24 | 12 | 19/1/0 | 0.6 | 1.9 | 0.3 |

| B cause | n | fill / fill needed | free floor | narrowest side of LER | strip floor | usable tops | soft / priority floor | level / reachable spot | largest drop / placements before end | rescue share | low_steps | last call | policy max | over-budget |
|---|---:|---|---:|---:|---:|---:|---|---|---|---:|---:|---:|---:|---:|
| A | 12 | .36/.67 | .33 | .23 | .97 | .00 | .10/.01 | 8/1 | .15/11 | .11 | 14 | 4.1 | 6.2 | 6.8 |
| B | 4 | .17/.42 | .49 | .39 | .58 | .13 | .00/.05 | 4/3 | .16/6.5 | .00 | 4 | 4.8 | 5.6 | 5.0 |
| D | 8 | .28/.41 | .30 | .24 | .97 | .00 | .68/.00 | 8/1 | .17/13.5 | .15 | 18.5 | 4.3 | 6.3 | 5.0 |
| E | 1 | .38/.41 | .31 | .24 | 1.19 | .09 | .37/.00 | 1/1 | .12/24 | .07 | 23 | 7.2 | 7.2 | 3.0 |
| F | 2 | .28/.38 | .39 | .39 | .63 | .23 | .16/.14 | 2/2 | .14/15 | .12 | 44 | 6.4 | 6.4 | 5.5 |
| G | 14 | .34/.42 | .31 | .35 | .76 | .03 | .15/.06 | 14/0 | .15/11.5 | .15 | 36 | 5.0 | 5.9 | 4.0 |
| H | 7 | .39/.45 | .34 | .34 | .52 | .00 | .06/.00 | 0/0 | .18/29 | .15 | 25 | 3.9 | 5.2 | 2.4 |

Means against the crossings of the sample and stretch strata (`course.md`):

| group (C v50) | n | soft placed / covered | priority placed / covered | soft floor | rescue share | shade vetoes | rung of the largest drop (top) | drop at door side / standing |
|---|---:|---|---|---:|---:|---:|---|---|
| D soft carpet | 10 | 35.9 / 1.7 | 3.1 / 0.2 | .58 | .21 | 19.1 | soft-edge 6, physics-resort 2 | 6 / 2 |
| G sealed | 9 | 3.8 / 0.0 | 8.2 / 1.9 | .07 | .27 | 29.3 | max-footprint 5 | 4 / 2 |
| H strips | 14 | 8.6 / 0.3 | 5.7 / 0.9 | .10 | .25 | 19.6 | max-footprint 4, physics-resort 3, terrace-extension 2 | 8 / 2 |
| crossings | 42 | 11.6 / 1.0 | 3.9 / 0.8 | .15 | .22 | 31.4 | max-footprint 9, physics-resort 9, stack-rl 7 | 23 / 14 |

- **B:** carpet soft floor share is 0.66 against 0.09 in the crossings. The
  soft-edge rung is the largest drop in 8 of 8 B carpets. B shows no shade
  vetoes.
- **The course does not separate causes** (consistent with Phenomenon 14). The
  largest one-step drop of the usable surface is 0.15-0.19 of the floor about
  11-20 placements before the end, both in the geometry misses and in the
  crossings. The rescue share is 0.13-0.29 everywhere.
- **Time pressure is cause-specific.** Over-budget steps are concentrated in D
  (6.1 a C episode) and F. H has 0.3, so time is not what stops the H boards.

## 5. Order family and the soft carpet

Crossing rate by order: need ≤ 0.44 ; need 0.44-0.506.

| record | random | big-first | soft-first | small-first | soft-last |
|---|---:|---:|---:|---:|---:|
| C v50 | 11/18 ; 1/7 | 5/6 ; 1/4 | 7/12 ; 0/1 | 4/10 ; 0/5 | 10/11 ; 4/9 |
| B v50 | 13/18 ; 3/7 | 6/6 ; 2/4 | 5/12 ; 0/1 | 5/10 ; 0/5 | 11/11 ; 3/9 |
| C v50 det | 13/18 ; 1/7 | 5/6 ; 1/4 | 8/12 ; 0/1 | 5/10 ; 0/5 | 10/11 ; 4/9 |
| C v49 det | 14/18 ; 2/7 | 6/6 ; 1/4 | 6/12 ; 0/1 | 5/10 ; 0/5 | 10/11 ; 4/9 |

Crossing rate by the soft footprints' share of the floor at the end (episodes
with need ≤ 0.506):

| record | <.10 | .10-.25 | .25-.40 | .40-.55 | ≥.55 |
|---|---:|---:|---:|---:|---:|
| C v50 | 24/37 | 8/18 | 6/10 | 3/10 | 2/8 |
| B v50 | 31/45 | 12/20 | 4/8 | 0/2 | 1/8 |
| C v50 det | 24/38 | 10/19 | 8/11 | 2/7 | 3/8 |
| C v49 det | 26/37 | 11/20 | 4/6 | 6/12 | 1/8 |

- **Small-first and soft-first are the costly orders.** In reach they cross
  4/10 and 7/12 on C, against soft-last 10/11 and big-first 5/6. Above 0.44
  they cross 0 of 6.
- **Big-first is not a cause:** it crosses in reach.
- **Mix, containers and shelves:** no clear effect beyond these. In-reach
  crossing rates are 0.6-0.8 for every mix, container count and shelf count.

## 6. Spots at the final decline: misses against crossings

| record | misses that end on a decline: level / reachable | crossings that end on a decline: level / reachable |
|---|---|---|
| C v50 | 18 / 7 of 49 | 6 / 1 of 40 |
| B v50 | 32 / 5 of 43 | 26 / 1 of 48 |
| C v50 det | 17 / 6 of 46 | 9 / 1 of 45 |

- **On C, a sealed spot is specific to misses.** On B it is the normal late
  state of the board.
- **What a pool would offer C** (`nextfit.py` on the 49 C boards that end on a
  decline):
  - Classes declined: 0.65×0.45×0.25 ×9, 0.55×0.4×0.24 ×8, 0.8×0.6×0.5 ×6,
    soft 0.65×0.35×0.23 ×5, priority 0.65×0.45×0.25 ×4, then smaller counts.
  - One of the next 10 stream items has a reachable spot on 21 boards; the
    declined item itself has one on only 7.

## 7. C against B, and attribution

**v50, same seeds:**

| stratum | both cross | C-only miss | B-only miss | both miss | placed B−C (all) | (both-miss) |
|---|---:|---:|---:|---:|---:|---:|
| sample | 29 | 6 | 4 | 9 | +0.88 | −2.78 |
| stretch | 6 | 6 | 3 | 17 | +0.03 | −1.53 |
| edge | 0 | 1 | 1 | 6 | −0.88 | −2.83 |
| fill-only | 0 | 0 | 0 | 8 | +3.25 | +3.25 |
| all | 35 | 13 | 8 | 40 | +0.65 | −1.05 |

**C-only misses (B result in brackets):** s0013 -4 (+2) G; s0020 -5 (+20) B;
s0021 -16 (+3) B; s0027 -3 (+6) G; s0028 -1 (+5) H; s0042 -7 (+18) C;
s0051 -4 (+2) H; s0052 -5 (+5) H; s0059 -1 (+0) G; s0060 -6 (+0) G;
s0076 -1 (+2) H; s0078 -3 (+0) H; s0087 -12 (+2) G.

**B-only misses (C result in brackets):** s0009 -1 (+10) G; s0026 -2 (+0) G;
s0030 -9 (+7) G; s0037 -24 (+11) B; s0056 -8 (+2) G; s0064 -4 (+0) G;
s0067 -1 (+2) H; s0083 -2 (+2) H.

Most causes stay the same from C to B on the scenes both miss: A→A 12, D→D 6.
The main moves are H→G 4 and H→H 4.

**Simulator endings:**
- **b-hard2-s0037** settles at step 9 in all three B records. The
  terrace-extension pose was kept after the shadow check saw a wobble of 5 cm
  and 4°.
- **b-s0061** settles at 74 of 119 in all three (a soft carpet anyway).
- **b-s0063 and b-s0070** vary across runs: -1 and -20 in the replicate.
- **On C**, s0020 and s0021 are fallback-after-veto plays and s0044 a
  physics-resort pose. All three cross in the deterministic run (+9, +3, +2).
- **c-hard2-s0091** ends on transport at 92 of 296 in every C record.

**C time-faithful against deterministic (v50):**
- Both cross 42, time-faithful-only misses 5, deterministic-only 1, both miss 48.
- The time-faithful-only misses are s0020, s0021 and s0044 (cause B), s0036 (D)
  and s0042 (C). The deterministic-only miss is s0048 (D).

**B replicate:** 46 both cross, 2 and 2 swaps; the replicate places +0.89 items
a scene.

**The gate (`bandntdet-hard2` to `gate0det-hard2`):**
- Gained: s0010 (-1 to +6), s0014 (-5 to +1), s0036 (-1 to +5), all soft
  carpets, and s0021 (-5 to +3).
- Lost: s0004 (0 to -2, carpet), s0007 (+2 to -1, strips), s0040 (0 to -4,
  strips), s0059 (0 to -2), s0076 (0 to -1, strips).
- Net -1 crossing, +0.39 placed a scene. Soft-carpet misses go from 16 to 14;
  the median soft floor share among scenes both miss goes from 0.19 to 0.16.

## 8. The near misses (margin -3 to -1)

| scene | margin | stratum | need | order | cause | next item | free floor / largest empty rect | soft floor | last call (s) | crosses in |
|---|---:|---|---:|---|---|---|---|---:|---:|---|
| c-hard2-s0006 | -1 | sample | .39 | small-first | D | 0.65×0.45×0.25 | .28 / 0.1×1.38 | .70 | 2.6 | – |
| c-hard2-s0007 | -1 | sample | .39 | soft-first | H | 0.8×0.6×0.5 | .33 / 1.14×0.16 | .35 | 0.4 | v49 det |
| c-hard2-s0028 | -1 | sample | .31 | soft-last | H | 0.8×0.6×0.5 | .32 / 0.44×0.62 | .00 | 0.4 | B |
| c-hard2-s0036 | -1 | sample | .34 | soft-first | D | soft 0.6×0.3×0.25 | .27 / 0.18×0.96 | .73 | 3.8 | v50 det |
| c-hard2-s0039 | -1 | sample | .38 | random | H | 0.75×0.56×0.27 | .23 / 0.28×0.58 | .15 | 0.4 | – |
| c-hard2-s0059 | -1 | stretch | .41 | big-first | G | 0.55×0.4×0.24 | .27 / 1×0.24 | .14 | 1.6 | B, v49 det |
| c-hard2-s0065 | -1 | stretch | .42 | random | H | priority 0.75×0.56×0.27 | .28 / 1.08×0.22 | .10 | 1.7 | – |
| c-hard2-s0076 | -1 | stretch | .46 | random | H | soft priority 0.4×0.4×0.6 | .30 / 1.32×0.16 | .15 | 0.6 | B, v49 det |
| c-hard2-s0004 | -2 | sample | .39 | small-first | D | soft 0.5×0.4×0.4 | .32 / 1.24×0.14 | .44 | 0.3 | v49 det |
| c-hard2-s0027 | -3 | sample | .36 | random | G | 0.55×0.4×0.24 | .30 / 0.3×0.72 | .00 | 2.1 | B |
| c-hard2-s0043 | -3 | sample | .31 | small-first | F | 0.55×0.4×0.24 | .40 / 1.52×0.16 | .37 | 4.8 | – |
| c-hard2-s0078 | -3 | stretch | .45 | soft-last | H | 0.65×0.45×0.25 | .26 / 0.8×0.22 | .00 | 0.9 | B |
| b-hard2-s0007 | -1 | sample | .39 | soft-first | G | soft 0.5×0.4×0.4 | .24 / 0.76×0.14 | .16 | 6.0 | – |
| b-hard2-s0009 | -1 | sample | .33 | soft-first | G | soft 0.65×0.35×0.23 | .32 / 1.06×0.22 | .21 | 5.6 | C |
| b-hard2-s0040 | -1 | sample | .39 | random | H | 0.55×0.4×0.24 | .26 / 0.4×0.26 | .07 | 3.8 | – |
| b-hard2-s0067 | -1 | stretch | .47 | soft-last | H | 0.75×0.56×0.27 | .27 / 0.58×0.34 | .00 | 4.2 | C |
| b-hard2-s0077 | -1 | stretch | .48 | random | G | soft 0.5×0.4×0.4 | .32 / 0.36×0.82 | .11 | 3.3 | – |
| b-hard2-s0026 | -2 | sample | .39 | random | G | soft 0.5×0.4×0.4 | .50 / 0.72×0.6 | .04 | 4.2 | C |
| b-hard2-s0039 | -2 | sample | .38 | random | H | 0.65×0.45×0.25 | .34 / 1.24×0.2 | .12 | 2.1 | – |
| b-hard2-s0083 | -2 | edge | .51 | soft-last | H | 0.8×0.6×0.5 | .40 / 1.1×0.48 | .00 | 3.9 | C |

## 9. Caveats

- **Existing tool defects.** `scratchpad/surface_traj.py` (the Phenomenon 14
  tool) marks every box as hard. It also reads the world x from `final_items`
  for containers 1 and 2 without subtracting the container offset (2.64 m on
  c-hard2-s0002). Those boxes fall off that container's grid, so Phenomenon
  14's ratios on multi-container episodes are really container 0's. The
  trajectory here uses the true soft flags, the offset recovered from
  `pos_local`, and the total usable area over the total floor area.
- **B's visible pool** is approximated as the first `pool` unplaced items of
  the stream.
- **End states include settle drift,** since they are rebuilt from settled
  poses.
- **"No spot" (G, H) is a lower bound** on what is left (see the check against
  real placements in section 2).

## Scripts and outputs (`reports/wedge/hard2-miss-taxonomy/`)

- `extract.py`: per-episode extraction. It rebuilds the boards and computes the
  usable-surface trajectory, floor state, largest empty rectangle, strips,
  pieces, the level and reachable spot checks, and the volume measures. Output
  is `data/<record>.json` (not kept in the repo; rerun from `reports/bench/`).
- `classify.py`: the rules, all the tables and the pairs. Output is
  `tables.md`, which includes every miss row for v50 C and B.
- `course.py`: course statistics by cause against the crossings (`course.md`).
- `nextfit.py`: reachable spots for the next 10 stream items on the C miss
  boards (`nextfit_gate0-hard2.txt`).
- `validate_reach.py`: false-negative rate of the spot checks on real
  placements.
