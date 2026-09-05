# bench core run — the stabilised ladder

Arm `ladder-stable` = rule-alpha with four opt-in fixes on (`anchor_slack`
0.5 mm + `anchor_clamp`, `key_quantum` 5 mm with an explicit tie-break,
`settle_sink_allowance` 2 cm, `compaction_keeps_support`).  Same 48 Task C
scenes as `core-findings.md`.  Three runs: physics twice, analytic once.
The shipped `ladder` arm was re-run on the smoke suite after the edits and is
identical step for step (`ladder-smoke-after-stability-control.md`), so the
default behaviour is untouched.

## 1. Negative control

`stable-core` vs `stable-core-repeat`: identical step for step on all 48
scenes (`stable-core-control.md`).

## 2. Does the analytic episode now track the physics episode?

`stable-core-analytic-vs-physics.md`, against the shipped ladder's numbers
from `core-findings.md`:

| | ladder | ladder-stable |
|---|---:|---:|
| leading placements identical (pose within 2 cm), mean | 6.6 | **12.9** |
| same, median | 6 | 12 |
| scenes identical to the end | 1 | **13** |
| placed_count, analytic − physics | +1.42 [+0.35, +2.44] | **+0.00** [−0.85, +0.79] |
| per-scene placed correlation | 0.88 | **0.93** |
| mean absolute per-scene placed difference | 2.96 | **1.62** |
| physics episodes ending in a topple | 5 | **2** |

The analytic model is no longer optimistic on average, tracks twice as far
into the episode, and reproduces the physics episode exactly on 13 scenes.
The remaining divergence is real settle drift (centimetres, not nanometres)
plus the two topples below.

## 3. Does stabilising cost anything in the physics?

`ladder-vs-stable-core.md`, paired on 48 scenes:

| metric | ladder | ladder-stable | diff, 95 % CI | evidence |
|---|---:|---:|---|---|
| placed_count | 20.67 | 21.77 | +1.10 [−0.10, +2.29] | none |
| fill_volume | 22.76 | 23.80 | +1.04 [−0.31, +2.40] | none |
| fill_evaluator_shipped | 13.12 | 14.40 | +1.29 [+0.35, +2.24] | b-better |
| com_z_above_floor_ratio | 0.322 | 0.336 | +0.015 [+0.004, +0.026] | b-worse |
| priority_covered | 0 | 0.06 | +0.06 [0, +0.15] | none |
| soft_covered | 0.146 | 0.125 | −0.02 | none |
| shake_topples | 0.19 | 0.15 | −0.04 | none |
| settle deaths | 5 | 2 | | |

No loss.  The placed count moves up by about one item on average, 24 scenes
better against 13 worse, but the interval touches zero so it is not claimed.
The centre of mass sits about 1.5 % of the container height higher, which is
what one more item on top of the stack does.  Three scenes acquire one
covered priority item each; that is worth watching, not yet acting on.

## 4. The two topples that remain

`c-c1-s0005` and `c-c2p-s0005`, both step 16, both `terrace-extension`,
same stream in the first container (`terrace-deaths-stable.json`).  Replayed
to the fatal step: a 0.40 × 0.55 × 0.24 box with 99.7 % of its underside on
one hard top at z 1.19, centre-of-mass margin 0.20 m, not moved by
compaction, the support itself resting on hard cargo.  Statically there is
nothing wrong with it; the physics still topples it 45° or more.  The
compaction guard removed the three deaths that were caused by sliding a box
off its support; what is left is the case the static criterion cannot see —
a sound box high on a stack that yields when loaded.

## 5. What this settles

* Decisions no longer depend on float noise; the bench's tolerant prefix went
  from 6.6 to 12.9 steps and one scene in four is reproduced to the end.
* Rollouts on the analytic model are now unbiased in placed count against
  the physics.  A learned ranker can be trained on them and evaluated here.
* The remaining physics-only failure mode is the loaded-stack topple.  It is
  rare (2/48) and the bench counts it; modelling it is a separate item.
