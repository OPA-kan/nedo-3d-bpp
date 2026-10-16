# Task A on the bench: the sample's kind of manifest, and the order's tail

The question after v52 (reports/wedge/stability-lattice.md, a-count-secure.md):
the platform counts 5 of its 8-10 Task A episodes, the bench's suites did
not say why, and every Task A form judged on them (count-secured re-plan,
typed standing, soft floor) came back level or negative on the platform.
This note makes Task A's quantity (the count) and quality (the components)
improvable on the bench: a suite of the platform's own kind of manifest,
checked against the platform's result, and the first lever it exposes.

## 1. The official sample as a bench layout

`bench/scenes.py` now has the layout `sample`: seed 0 is the official
sample's scene of the task (`reports/submission/abc_config.json`, 000 for
A, 001 for B, 002 for C), item order and all; a seed above 0 keeps the
same items and shuffles their order.  Suites `sample-a`, `sample-b`,
`sample-c` are the sample and eleven shuffles (12 scenes a task).

The sample's Task A manifest: 41 items, 25 hard boxes (12 of 0.55x0.40x0.24,
9 of 0.65x0.45x0.25, 4 of 0.75x0.56x0.27), 13 soft, 3 priority (hard), the
manifest 0.557 of the container's box volume (hard 0.37, soft 0.14,
priority 0.05).  The count threshold is 21.

### The bench reproduces the platform on it

Run locally (`python -m bench run --scene A:sample:0 --sim physics
--budget 4.5`, 30 s a run), against the official sample check
(`reports/submission/official-sample-abc-*.json`, `scripts.run_test` on
the simulator):

| Task A form | bench placed | sample check placed | fill (bench volume) |
|---|---:|---:|---:|
| shipped (v50: planner, then the dry-run, the race) | 25 / 41 | 25 / 41 | 43.6 |
| the dry-run alone (`offline_planner=`) | 25 / 41 | 25 / 41 | 43.6 |
| the row planner alone (`offline_dry_run=false`) | 21 / 41 | 21 / 41 | 31.1 |

The same three counts, so what the bench says about this manifest is what
the platform says.  (On the generated suites the planner alone is level
or better than the shipped race: core-a +0.93 [+0.12, +2.09] platform
points, dense-a +1.26 n.s., hard-a +0.15 n.s., `reports/bench/aplan-*`;
the dry-run alone is far under: core-a -26.69, dense-a -9.46, hard-a
-7.36.  On the sample the dry-run's plan is the one that crosses and the
planner's sits exactly on the threshold.  The generated suites and the
sample disagree about the two plans, which is why `sample-a` exists.)

## 2. Where the shipped form stops on the sample

The shipped form's order on the sample (`plan_source` dry-run; the
dry-run planned 28 items on the analytic board):

- steps 1-25: the 25 hard boxes, all placed (fill 43.6, tops at 1.05-1.36
  m of 1.61);
- step 26: priority box 8 (0.65x0.45x0.25), **no pose**, in 0.69 s; the
  episode ends;
- untried: the two other priority boxes and all 13 soft boxes, with 56 %
  of the container's volume free.

A probe at that board (scratchpad `probe_decline.py`: the live agent asked
for a pose for each untried item, one at a time, on the board as it
stood) found a pose for **11 of the 16**: none of the three priority
boxes and none of the two 0.50x0.40x0.40 soft boxes, a pose for every
other soft box (the 0.65x0.35x0.23 ones by the physics resort at z 0.23,
the 0.60x0.30x0.25 and 0.45x0.30x0.20 ones by the stack option at z
0.36 / 0.16: floor pockets the hard rows left).  The tail's order, not
the board, ended the episode: the dry-run had placed items 8, 30 and 14
on its analytic board, the live board settled differently, and the order
put the priority boxes first.

## 3. The lever: the order's tail

`config.plan_tail_order` (default empty): after the chosen plan's items,
the order's tail is rearranged -- `soft-first` (the soft boxes by volume
ascending, then the priority boxes, then the hard ones),
`soft-first-prio-last`, `small-first`.  Arms `arm_atail_a` /
`arm_atailp_a` / `arm_atails_a` are the shipped form with the flag.

### Local measurement (sample-a, physics, budget 4.5 s)

(filled in below from `scratchpad/tail_exp.py`: the shipped form's
optimize, the tail rearranged after it, one episode a seed)
