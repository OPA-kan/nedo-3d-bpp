# bench core run — is the measurement base sound, and what does it say?

Arm `ladder` (rule-alpha, shipped config).  Suite `core`: 48 Task C scenes,
12 seeds × 4 layouts (c1, c1s, c2, c2p), 41 items per container.  Four runs:
physics twice (`ladder-core`, `ladder-core-repeat`), the analytic model once
(`ladder-core-analytic`), and the agreement probes (`agree-core`, 3 survivors
+ 3 perturbed candidates per decision).  Four processes shared four cores, so
wall-clock columns are inflated and are never used as evidence.

## 1. The bench itself: negative control passes on all 48 scenes

`ladder-core` vs `ladder-core-repeat`: identical step for step, every
physical metric identical on every scene (`ladder-core-control.md`).  The
official environment is deterministic under the flow the bench uses, so a
paired difference between two arms is attributable to the arms.

## 2. Baseline under Task C

| metric | mean over 48 scenes |
|---|---:|
| placed_count | 20.67 (41 or 82 items offered) |
| fill_volume | 22.76 |
| fill_evaluator_tolerant (+0.005) | 20.61 |
| fill_evaluator_shipped (−0.005) | 13.12 |
| com_z_above_floor_ratio | 0.32 |
| soft_covered | 0.15 per scene; priority_covered 0; misrouted 0 |
| shake_topples | 0.19 per scene; mean shift 3.1 cm |
| end_reason | declined 43, **settle 5** |

The five `settle` endings are the planner's own pick being rejected by the
physics.  All five are `terrace-extension` placements on top of packed items
that toppled (45°–90°) when released.  The analytic model never ends an
episode this way, so it cannot see one episode in ten dying.

## 3. Analytic model vs official validator (5 582 probes)

| | physics accepts | physics rejects |
|---|---:|---:|
| analytic accepts | 4 005 | 10 |
| analytic rejects | 839 | 728 |

* **False accepts 10 / 4 015 (0.2 %).**  All ten are `terrace` placements on
  item supports: 5 chosen or surviving candidates, 5 perturbed.  Same failure
  as §2.  Everything else the analytic model accepts, the physics accepts.
* **False rejects 839 / 1 567 (53.5 %).**  `no-support` 724/736 accepted by
  physics (a released box drops onto its support), `outside-container`
  48/48 (the analytic 16 mm clearance against the official 5 mm),
  `centre-of-mass-outside-support` 31/34, `overlaps-packed-item` 28/295,
  `transport-hits-packed-item` 1/20, `settled-pose-outside` 6/424,
  `overlaps-main_shelf` 0/9.

The analytic model is a safe *validity* oracle except for tall terrace poses,
and a very conservative one: half of what it forbids the competition allows.

## 4. Analytic episode vs physics episode, same scenes, same rules

`ladder-core-analytic-vs-physics.md`.

| | value |
|---|---:|
| leading placements identical (pose within 2 cm) | mean 6.6 steps, median 6 |
| placed_count, analytic − physics | +1.42, 95 % CI [+0.35, +2.44] |
| fill_volume, analytic − physics | +1.69, CI [+0.53, +2.86] |
| per-scene placed_count correlation | 0.88 (0.91 excluding the 5 settle deaths) |
| mean absolute per-scene placed difference | 2.96 items |

The analytic outcome tracks the physics outcome only loosely: it is
optimistic on average and the per-scene error is about three items on a
mean of twenty.  Of the 48 scenes, 38 diverge on an **orientation** choice
for the same item (often the same archetype), 9 on a position, 1 not at all.

## 5. Why they diverge: the ladder's choice is decided by float noise

Scene `c-c1s-s0006`, second decision (item 1, `max-footprint`), with item 0
already placed.  Only item 0's recorded pose changes:

| item 0 pose handed to the planner | decision for item 1 |
|---|---|
| analytic pose, exact floats | orientation 3 at (0.709, 0.369) |
| analytic pose, y − 1.2e−8 m | orientation 3 at (0.709, 0.369) |
| analytic pose, z − 0.012 m (soft sink) | orientation 3 at (0.709, 0.369) |
| simulator pose as observed (x + 5.7e−9, y − 1.2e−8, z − 0.0116) | **orientation 0 at (0.383, 0.469)** |
| simulator pose rounded to 4 decimals | orientation 3 at (0.709, 0.369) |
| analytic pose without the `layer` key | orientation 0 at (0.609, 0.469) |

Three different placements for the same board, separated by changes of
10⁻⁸ m and by a bookkeeping key.  The lexicographic comparators compare
exact floats, so equally good candidates are ordered by whichever anchor
happens to be a nanometre deeper.  Sub-millimetre settle drift is therefore
enough to send two runs of the same rules down different trajectories after
a handful of steps, which is what §4 measures.

This is a property of the ranker, not of the bench: the bench reproduces
itself exactly (§1).  Any ranker that is to be trained on analytic rollouts
and evaluated in physics has to break ties on quantities with a real margin
(bucketed, or learned), or the rollout trajectories will not be the physics
trajectories.

## 6. What this settles for the learning plan

* The bench is sound: deterministic, paired, with a passing negative control.
* The analytic model can label validity (0.2 % false accepts, all tall
  terrace poses), so candidate features and one-step feasibility can be
  computed off-physics.  It cannot yet stand in for the physics *episode*:
  trajectories diverge within ~6 steps and one episode in ten ends in a
  topple it does not model.
* Before rollouts on the analytic model mean anything, the ranker must be
  made insensitive to noise below the geometry's own tolerance, and the
  terrace topple must be either modelled or excluded.  Both are measurable
  here: the prefix length and the settle-death count are the numbers to
  move.
* The candidate space the analytic model offers is half the size the
  competition allows.  Released drops and 5 mm wall clearances are legal and
  unexplored.
