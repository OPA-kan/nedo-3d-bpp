# Task C re-baseline after merging the stride-endgame branch

Date: 2026-08-02. Same box, same `--parallel 3`, 3 repeats per cell. The only
deliberate change is the merged allocation: `ANCHOR_FIRST_PASS_ATTEMPTS`
64 -> 256 (and deep pass 256).

| case | arm | placed @64 | placed @256 | fill @256 | terminal source @256 |
|---|---|---|---|---:|---|
| c001-k1 | base | 18, 18, 18, 18, 18 | 18, 18, 18 | 23.560 | fixed fallback 3/3 |
| c001-k1 | anchor_fallback | 19, 19, 20, 20, 20 | 19, 19, 19 | 25.366 | fixed fallback 3/3 |
| c000-k1 | base | 18, 19, 21, 21, 21 | 18, 18, 20 | 13.311 | **placement_core 3/3** |
| c000-k1 | anchor_fallback | 21, 21, 21, 21, 21 | 20, 20, 20 | 16.477 | **placement_core 3/3** |

## The generator blindness survives the allocation change

c001-k1 base still dies at step 18 on the fixed coordinate, with
`units_completed` at or past `units_total`: support_plane still exhausts its
whole space and accepts nothing. More attempts per unit cannot fix a space
that does not contain a solution, which is what the class predicted.

The fallback still fires there in every repeat and still buys a placement:
18 -> 19, fill 23.560 -> 25.366, deterministic on both sides.

## But 256 costs the fallback its better outcome

At 64 attempts the fallback returned a **settled** candidate in three of five
repeats and reached placed 20. At 256 it returns a **release** candidate in
all three and stops at 19. The deeper first pass leaves less of the budget for
the fallback, so the ladder no longer reaches the settled units.

## And 256 makes the step-19 state worse, not better

Step 19 is the depth/budget class: the oracle found 42 physically safe settled
placements there, four of them inside the shipped support_plane space, and the
search accepted none.

| first pass | units visited at step 19 |
|---|---|
| 64 | 4 of 12 |
| **256** | **2 of 12** |

Deeper per unit means fewer units. On the state that needs unit coverage, the
merged default moves in the wrong direction. This is a Task C endgame
observation and not a criticism of the branch's own result: its depth
measurements are on the Task B development suite, where the trade evidently
goes the other way.

It also sharpens what to try next. `LIVE_SEARCH_INTERLEAVE` permutes anchor
order *within* a unit, so an exhausting unit still sees every anchor -- it does
not address unit coverage, which is what step 19 lacks. The step-19 fix has to
be about which units get visited, not about how a visited unit is scanned.

## c000-k1's death channel changed

At 64 every c000-k1 episode ended on the fixed-coordinate fallback (5 of 5).
At 256 none do (0 of 6 across both arms): the terminal action is now a real
candidate from `placement_core` that fails physically. The poison pill is no
longer this case's failure mode.

Placed did not improve on this box (base 20.00 -> 18.67, fallback 21.00 ->
20.00), but both arms are the same code path here -- the fallback never fires
or even attempts on c000-k1 -- so those means are run-to-run variance and the
comparison carries no information about the fallback. Whether 256 is good or
bad for c000-k1 is a question for the runner the branch measured on, not for
this box.

## Status

The fallback's justification survives: the blindness class is real at 256 and
the fallback still converts it into a placement. Its ladder does not survive
unexamined -- it now under-delivers relative to 64, and the merged branch's own
distinction between striding and interleaving says the ladder is using the
wrong one under a deadline.
