# Observed-state swap optimizer

## Question

The safe-split replay dataset builds a positive-transition portfolio and then
compares it against an independently drawn paired safe-random control. The
comparison the acceptance guard actually reports is the **mean** observed
nearest-neighbour distance of the two arms, rescaled by the range of their
union.

Up to run `31380879143` the portfolio was not built to that statistic. It was
built by maximizing semantic coverage first and then greedily maximizing the
**minimum** observed nearest-neighbour distance. The two are not the same
objective, and the matrix showed the gap directly: single-empty-noshelf step 9
(-0.004446) and single-empty-shelf step 15 (-0.017559) lost mean distance while
their minimum distance stayed positive (+0.002102 and +0.002309) and their item
and item-orientation coverage did not regress.

Those two cells later turned out to be the runner-variable ones — see the
ablation section below, where the same greedy construction passed them. Read
the paragraph above as what one run showed, not as a reproducible failure.

The question this instrument answers is therefore narrow: does removing the
mismatch — optimizing the statistic that is measured, from a seed that is
already feasible — recover those cells without giving up the semantic coverage
the earlier stages were built to guarantee?

## Contract

`scripts/observed_state_swap.py` replaces the final safe-positive selection in
`residual_diversity_safe_split`. Nothing else moves: candidate enumeration, the
overdraw, the per-candidate official replay, the safe/unsafe split, the
negative-risk arm, and the paired control draw are unchanged.

**Seed.** The paired safe-random control is the initial point. Control rows are
pinned into the safe union up to the stratum capacity the genuinely forced rows
(the real selected action and the shadow-rerank selection) leave free; the
remaining capacity is filled by the existing v3 global item/orientation
matching. When the control saturates the quota the two arms start as the same
set, so the initial measured delta is exactly `0.0`.

**Moves.** One row swapped for another inside the same stratum. Stratum sample
counts, forced rows, and the safe-only population are therefore invariants of
the search rather than properties to re-verify afterwards.

**Acceptance.** A swap is applied only when

1. `unique_items` and `unique_item_orientations` over the observed rows do not
   fall, and
2. the exact paired mean-nearest-neighbour delta — the same number the guard
   reports — strictly increases.

Because both arms are rescaled by the range of their union, moving one positive
row also moves the control's reported distance. Candidate swaps are therefore
*ordered* with a cheap fixed-basis distance matrix and *accepted* only on a
full re-derivation of the scales. The screening approximation can mis-rank; it
cannot mis-accept.

**Diagnostics.** The trace records the initial and final objective (mean and
minimum, both arms), the applied swaps with their before/after deltas, the
semantic coverage before and after, the evaluation counts, and the termination
reason. Minimum nearest-neighbour distance is a diagnostic: the search neither
optimizes nor constrains it, so a mean gain bought with a minimum loss stays
visible.

## What this cannot claim

- It is a local search. It does not certify that no better admissible
  portfolio exists.
- It does not guarantee a positive delta. Whenever the control cannot fill the
  stratum quota, the seed does not start at `0.0`, and no admissible swap is
  obliged to exist.
- A larger positive arm is compared against a smaller control on a
  size-sensitive statistic; mean nearest-neighbour distance falls as a
  portfolio grows. The arm sizes stay in the trace (`portfolio_size`,
  `control_size`) so this confound is readable rather than assumed away.
- It is a dataset-coverage instrument. A positive delta means the sampled
  observed settle afterstates are more dispersed. It is not evidence about the
  live policy, placed count, fill, or the official score.
- **The objective it maximises had two measured defects.** The metric spanned
  two coordinate frames -- commands are container-local, settled `x_plus` is
  world, and the containers sit 2.5 m apart against item extents of tens of
  centimetres -- and it averaged two different questions into one sum: where
  the item landed, and which item left the pool. Neither defect explains the
  margin. Re-scoring 454 retained boards with both arms collapsed into a
  single frame moves the mean delta from +0.074200 to +0.071780, positive on
  every one of the 294 multi-container boards in both frames, and bit-identical
  on the 160 single-container boards, which is the control on the correction.
  Split into components, the delta is +0.049909 on occupancy (452 wins, 0
  ties, 2 losses) and +0.095786 on consumption (294 wins, 81 ties, 79 losses),
  so the optimizer is not winning one axis by giving up the other. The corpus
  grows with every matrix run, so re-run the script rather than quoting these
  numbers; the conclusion has held from 363 boards to 454. See
  `scripts/measure_residual_metric_defect.py` and
  `reports/residual-metric-frame/summary.md`.

## The frame fix, and what it invalidates

`settled_proxy_record` now takes `container_offsets` and the dataset builder
passes them, so the search, the guard and the coverage report all read one
frame. `container_frame_offsets` shifts x and y only: a commanded z of 0.227
settling to 0.175 is the item dropping five centimetres, and subtracting a
container's z would turn that physical fact into a frame error.

Omitting the argument still reproduces the world-frame descriptor, because
every measurement recorded before 2026-08-11 read it that way and those
ledger entries have to stay readable. The offline measurement uses that
default for its `as reported` column and the offsets for its `single frame`
column, so it exercises the shipped path on both sides rather than
reimplementing the shift.

What this invalidates: guard deltas from runs before the fix are in the old
frame and must not be compared directly against later ones on
multi-container boards. Single-container boards are unaffected by
construction. The acceptance guard now also reports
`mean_nearest_neighbor_occupancy` and `mean_nearest_neighbor_consumption`
beside the single sum; the search still maximises the sum, which remains a
weighting nobody chose.

## The acceptance rule, and the shadow arm that measures it

The search accepts a move whenever the single Gower ΔNN rises. That sum
averages occupancy and consumption, nobody chose the weights, and it can
therefore pay for one with the other. `pareto_gate` keeps the same ordering
but refuses a move that degrades either component.

Which rule is better is not settleable by argument, so the dataset builder
runs both on every board and keeps the second one's trace only. Same pool,
same seed, same forced keys; the acceptance rule is the only difference, and
nothing downstream reads the shadow portfolio. The pairing is the point: the
policy is deadline-limited, so two runs of one scenario do not reach the same
board, and the earlier greedy-versus-seeded verdict turned out to be
runner-variable for exactly that reason. Cost is about 85 ms per step against
minutes of replay.

The number that decides whether the question is live at all is
`component_degrading_swaps` on the shipped arm: accepted swaps that raised
the sum while a component fell. Zero everywhere would mean the two rules
cannot disagree and the sum rule is fine as it stands.

The name is deliberately `pareto_gate` and not `pareto`. It is not a
total-free search -- the sum still orders the admissible moves. It only
removes the moves the sum was allowed to buy at a component's expense. That
keeps the contrast to one variable, which is what makes the shadow
attributable; a rule that also changed how ties are broken would confound
the two.

`scripts/measure_swap_acceptance.py` aggregates the pairs, and the matrix
workflow runs it into the step summary.

### What the pairs said, and what changed

Run `31491047020`, 44 boards, both rules on each. The question was live:
the sum rule accepted 171 swaps that raised the sum while a component fell,
on 40 of the 44 boards.

| gate − sum | mean | win/tie/loss | sign test | call |
|---|---:|---:|---:|---|
| Δ consumption | +0.029919 | 25/15/4 | p=0.0001 | gate better |
| Δ occupancy | +0.001921 | 24/7/13 | p=0.0989 | indistinguishable |
| single Gower ΔNN | −0.005548 | 2/6/36 | p<0.0001 | sum better |

Consumption is a real gain, raising the mean delta from 0.095 to 0.125.
Occupancy is **not** a win: a +0.0019 mean with 24 boards better and 13
worse reads like one, and an exact two-sided sign test says otherwise. The
sum falls by construction, because the gate refuses moves the sum rule
takes; that row checks the arms differ rather than reporting a result.

So `pareto_gate` is the default from commit `3ba4653`'s successor, on the
grounds that it improves a component nobody was watching, does not
measurably move the one they were, and pays in a number whose weighting
nobody chose. Adoption is safe on the guard, which reads that number: its
minimum over the 44 boards falls only from 0.035931 to 0.030851, with no
board at or below zero under either rule.

`--observed-swap-acceptance sum` restores the old rule. Whichever is chosen
runs as the shipped arm and the other becomes the shadow, so the comparison
that justified the change keeps being measured in reverse.

## Ablation

`--observed-swap-rounds 0` disables the seed and the swaps together and
reproduces the run-`31380879143` construction, so the two arms can be built
from the same snapshot and compared directly.

## Condition-matrix result

*Superseded in interpretation by the ablation section that follows: the pass
below is real, but it is not attributable to the optimizer on its own.*

Actions run `31388832646`, same frozen 3x overdraw and the same steps 3/9/15
as the failing run `31380879143`, passed all four cells and produced 307
safe-positive and 134 negative-physical-risk rows.

| scenario | ΔmeanNN before (`31380879143`) | ΔmeanNN after (`31388832646`) | verdict |
|---|---:|---:|---|
| m-dual-empty | +0.059554 | +0.073926 | pass |
| m-dual-shelf-mixed | +0.022782 | +0.070353 | pass |
| m-single-empty-noshelf | +0.004947 (**fail**) | +0.049806 | pass |
| m-single-empty-shelf | +0.024874 (**fail**) | +0.064257 | pass |

The two "before" failures are scenario verdicts, not small scenario means:
the guard is per step, and those cells averaged positive while step 9
(-0.004446) and step 15 (-0.017559) were negative. Scenario means are never
pooled to hide a step.

Three of the four guards are structural once the control fills the stratum
quota, not outcomes of the search: the seed is the control, so the measured
delta starts at exactly `0.0`; the seeded portfolio is a superset of the
control, so the unique-item and item-orientation deltas cannot be negative and
the swap constraint keeps them there; and both arms are all-safe and the same
size, so the placed-safe delta is `0`. Only the strict `> 0` mean-NN guard
depends on an improving swap existing.

## The ablation arm, and what it took away

`--observed-swap-rounds 0` was then dispatched on the same commit as run
`31389892147`, and a second seeded run landed as `31389471561`. Four matrix
runs now exist:

| run | arm | dual-empty | dual-shelf | 1c-noshelf | 1c-shelf | verdict |
|---|---|---:|---:|---:|---:|---|
| `31380879143` | greedy | +0.059554 | +0.022782 | +0.004947 | +0.024874 | **fail** |
| `31389892147` | greedy (ablation) | +0.059554 | +0.022782 | +0.024663 | +0.031070 | pass |
| `31388832646` | seeded + swap | +0.073926 | +0.070353 | +0.049806 | +0.064257 | pass |
| `31389471561` | seeded + swap | +0.083348 | +0.084649 | +0.061929 | +0.081494 | pass |

**The ablation passed.** The same greedy construction that failed two cells in
`31380879143` cleared all four in `31389892147`. So "the optimizer made the
matrix pass" is not a claim this evidence supports: a greedy run can pass on
its own, and the guard verdict is runner-variable for that arm.

Two things do survive:

- The variance is localized and the ablation is self-verifying. The greedy
  deltas are **bit-identical** across the two greedy runs on both
  two-container cells (`0.059554000212093394` and `0.0227817794889502`) and
  differ only on the two single-container cells — the ones that failed. That
  the two-container numbers reproduce exactly also confirms the dispatch
  really ran with rounds 0, since the seeded arm moves them.
- Every seeded per-scenario delta, in both seeded runs, exceeds the ablation's
  corresponding delta in all four cells; and the seeded arm cannot report a
  negative delta at all while the control fills the stratum quota.

The optimizer's established contribution is therefore **a structural floor and
a consistently larger margin**, not the difference between pass and fail on any
one run. Cite the delta ordering and the floor, not the verdict, when
comparing the arms.

## Local paired measurement

Both previously failing cells were rebuilt locally on the same frozen 3x
overdraw configuration, once with the optimizer and once with
`--observed-swap-rounds 0`. Not a runner-comparable substitute for the Actions
matrix — one step per run, single local machine — but a direct paired check of
the mechanism on the exact cells that failed.

See `reports/observed-state-swap/local-paired.md`.
