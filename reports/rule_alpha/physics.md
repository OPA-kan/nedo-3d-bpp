# rule-alpha in the official PyBullet environment

Each scenario replayed through `GroundHandlingEnv`: real `check_inclusion`, real transport sweep, real 300-step settle.

`accepted / attempted` counts placements the validator took. The run ends when rule-alpha declines, because Layer 1 has no home for the single visible item and this prototype has no Layer 2 — the official environment has no way to skip an item.

| scenario | accepted / attempted | fill_score | items placed | seconds |
|---|---|---|---|---|
| 01-normal-no-shelf | 5/5 | 0.00 | 0.192 | 2.67 |
| 02-normal-with-shelf | 5/5 | 0.00 | 0.192 | 2.1 |
| 03-priority-plus-normal | 13/13 | 0.00 | 0.325 | 11.4 |
| 04-soft-heavy | 4/4 | 0.00 | 0.154 | 1.64 |
| 05-priority-heavy-no-priority-uld | 7/7 | 0.00 | 0.269 | 4.21 |
| 06-soft-priority-heavy | 18/18 | 7.60 | 0.529 | 20.15 |
| 07-elongated-heavy | 13/13 | 0.00 | 0.591 | 17.23 |
| 08-slope-exploitation | 9/9 | 0.00 | 0.300 | 8.93 |
| 09-mixed-random | 5/5 | 0.00 | 0.147 | 3.01 |
| 10-awkward-holes | 7/7 | 0.00 | 0.269 | 4.81 |
| 11-lookahead-3 | 5/5 | 0.00 | 0.147 | 3.39 |
| 12-large-hard-only | 4/4 | 0.00 | 0.200 | 0.75 |

A `fill_score` of 0.00 next to accepted placements is not a packing failure. `Evaluator.calculate_fill_rate` re-tests the *settled* pose against `inclusion_margin = -0.005`, and a box resting on the floor sits micrometres *inside* the floor plane, so its volume is discarded.

The table demonstrates this on its own: the only scenario with a non-zero score is the only one that got cargo onto a **shelf**. Its floor-resting items scored nothing either — the shelf items are raised well clear of the floor plane, so they survive the margin. See the finding in `docs/rule_alpha/README.md` section 1.
