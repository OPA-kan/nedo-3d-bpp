# rule-alpha in the official PyBullet environment

Each scenario replayed through `GroundHandlingEnv`: real `check_inclusion`, real transport sweep, real 300-step settle.

`accepted / attempted` counts placements the validator took. The run ends when rule-alpha declines, because Layer 1 has no home for the single visible item and this prototype has no Layer 2 — the official environment has no way to skip an item.

| scenario | accepted / attempted | fill_score | items placed | seconds |
|---|---|---|---|---|
| 01-normal-no-shelf | 8/8 | 2.55 | 0.308 | 14.31 |
| 02-normal-with-shelf | 6/6 | 1.49 | 0.231 | 6.25 |
| 03-priority-plus-normal | 19/19 | 1.47 | 0.475 | 49.83 |
| 04-soft-heavy | 13/13 | 13.87 | 0.500 | 27.05 |
| 05-priority-heavy-no-priority-uld | 6/6 | 0.00 | 0.231 | 8.17 |
| 06-soft-priority-heavy | 21/21 | 9.78 | 0.618 | 31.49 |
| 07-elongated-heavy | 14/14 | 2.06 | 0.636 | 20.61 |
| 08-slope-exploitation | 11/11 | 2.23 | 0.367 | 23.95 |
| 09-mixed-random | 5/5 | 1.01 | 0.147 | 7.23 |
| 10-awkward-holes | 10/10 | 1.23 | 0.385 | 13.46 |
| 11-lookahead-3 | 7/7 | 1.60 | 0.206 | 13.16 |
| 12-large-hard-only | 3/3 | 0.00 | 0.150 | 1.21 |

A `fill_score` of 0.00 next to accepted placements is not a packing failure. `Evaluator.calculate_fill_rate` re-tests the *settled* pose against `inclusion_margin = -0.005`, and a box resting on the floor sits micrometres *inside* the floor plane, so its volume is discarded.

The table demonstrates this on its own: the only scenario with a non-zero score is the only one that got cargo onto a **shelf**. Its floor-resting items scored nothing either — the shelf items are raised well clear of the floor plane, so they survive the margin. See the finding in `docs/rule_alpha/README.md` section 1.
