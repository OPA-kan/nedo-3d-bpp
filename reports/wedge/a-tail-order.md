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

A first cut of the flag left the plan's own trailing items ahead of the
tail and changed nothing (the dry-run's plan holds 8, 30 and 14 after the
hard boxes, and 8 is what fails): the plan's trailing run of soft and
priority items now joins the tail.  On the sample itself (local, physics,
budget 4.5 s) the shipped form then places 27 of 41 (fill 44.9) instead
of 25: two soft boxes in the pockets, then nothing again.

### The sample-a suite

A shuffle of the sample's items gives Task A the same episode (the agent
orders the manifest itself), so a seed above 0 of the `sample` layout
resamples the manifest instead: 41 items drawn from the sample's 41 with
replacement (24-30 hard, 7-16 soft).  CI records (physics, 4.5 s, offline
budget 140 s), priced with `bench.platform_score` against the shipped form
(`ship-sample-a`: 59.23, 12 of 12 counted, placed 25.8, fill 41.5, cog
74.5, placement 49.3, soft 28.3):

| arm | delta [95 % CI] | up / down | fill | cog | placement | soft | placed |
|---|---|---|---:|---:|---:|---:|---:|
| dry-run alone (`adry`) | -8.31 [-13.19, -3.62] | 0 / 6 | +2.6 | -6.6 | -35.4 | -18.2 | -0.1 |
| planner alone (`aplan`) | **+6.75 [+2.28, +11.32]** | 6 / 0 | -5.8 | +8.8 | +26.4 | +17.4 | -1.8 |
| tail soft-first (`atail`) | -1.14 [-4.02, +1.22] | 5 / 5 | +0.4 | -0.9 | -18.1 | +10.5 | +0.8 |
| tail soft-first, priority last (`atailp`) | -1.14 [-4.02, +1.22] | 5 / 5 | +0.4 | -0.9 | -18.1 | +10.5 | +0.8 |

On core-a the tail orders read -0.60 [-1.74, +0.46] and -0.10 [-1.24,
+1.04] (soft +8 to +10, placement -10).  The tail order trades the
priority boxes for soft ones: more items, more soft credit, the placement
component down by more.  It is not a lever.

The reading that matters is the planner alone.  On the sample's kind of
manifest the race picks the dry-run's plan on 6 of 12 episodes (the ones
where the planner's plan sits at or under the threshold), and that plan
holds no soft and no priority box: fill 2-3 points higher, placement and
soft zero.  The platform prices a counted episode's placement and soft at
0.143 and 0.141 of 100 each; the dry-run's fill is worth about a point.
Where the planner's plan is chosen it carries 4-7 soft and 1-6 priority
boxes.  So on this suite the planner alone is +6.75, and the dry-run study
(reports/wedge/a-count-secure.md section 7) reads the planner alone as
never worse on the generated suites at 140 s (core-a +0.93 [+0.12,
+2.09], dense-a +1.26 n.s., hard-a +0.15 n.s.) and -2.48 n.s. on hard-a at
20 s, where the dry-run rescues sub-threshold planner plans.

The candidate that keeps both: the race with the planner's plan preferred
(`plan_prefer_planner=true`, arm `aprefer`): the planner's plan unless it
is under the count threshold and the dry-run's is not.  On the sample
itself that is still the dry-run (the planner plans 20 of 41, the
threshold is 21); on the other sample-a episodes it is the planner.
Measured on sample-a, core-a, dense-a, hard-a at 140 s and on sample-a and
hard-a at 30 s, with the planner alone and the shipped form at 30 s on
sample-a beside it (records `aprefer*-*`, `aplan30-sample-a`,
`ship30-sample-a`; section 4 below when they land).

## 4. The prefer-planner race, priced: v53

`bench.platform_score` against the shipped form at the same offline
budget (physics, policy budget 4.5 s; records `aprefer*-*`,
`aplan*-*`, `ship30-sample-a`):

| suite, budget | prefer-planner race (`aprefer`) | counted | planner alone (`aplan`) |
|---|---|---:|---|
| sample-a, 140 s | **+4.12 [+0.56, +8.41]** (4 up / 0 down) | 12 / 12 | +6.75 [+2.28, +11.32] |
| sample-a, 30 s | +4.12 [+0.56, +8.41] (the records identical) | 12 / 12 | +6.75 |
| core-a, 140 s | **+0.80 [+0.06, +1.90]** (5 / 1) | 48 / 48 | +0.93 [+0.12, +2.09] |
| dense-a, 140 s | +0.98 [-0.18, +3.14] (1 / 1) | 11 / 48 (+1) | +1.26 [-0.12, +3.63] |
| hard-a, 140 s | +1.72 [-0.09, +4.95] (12 / 8) | 27 / 48 (+1) | +0.15 [-3.20, +3.61] |
| hard-a, 30 s | +0.24 [-3.11, +3.68] (11 / 7) | 26 / 48 | -0.30 [-3.73, +3.30] |

The preference is positive on every suite and significant on the two
that resemble the platform's counted A episodes (sample-a, core-a); on
hard-a it beats the planner alone by keeping the dry-run's rescue of the
sub-threshold planner plans (27 counted against 26), and it holds at the
30 s budget that stands for the platform's time regime.  What moves is
the placement and soft credit of the counted episodes (sample-a +14.6 /
+11.8, core-a +2.7 / +2.3) and the centre of mass (cog +1.5 to +5.3),
against a point or three of fill.  Shipped as v53 (`plan_prefer_planner`
in `submission/agent.py`'s Task A overrides); the sample check reads as
v50's, since on the sample itself the planner's plan is under the
threshold.  At the platform's task shares (A 9 of 23) the bench's
reading is worth about +0.3 (core-a's) to +1.6 (sample-a's) total points.
