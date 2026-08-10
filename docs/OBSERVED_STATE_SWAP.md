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

## Ablation

`--observed-swap-rounds 0` disables the seed and the swaps together and
reproduces the run-`31380879143` construction, so the two arms can be built
from the same snapshot and compared directly.

## Condition-matrix result

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

The `--observed-swap-rounds 0` ablation arm has **not** been dispatched in
Actions. The seeded-versus-greedy contrast rests on the single matched local
pair below.

## Local paired measurement

Both previously failing cells were rebuilt locally on the same frozen 3x
overdraw configuration, once with the optimizer and once with
`--observed-swap-rounds 0`. Not a runner-comparable substitute for the Actions
matrix — one step per run, single local machine — but a direct paired check of
the mechanism on the exact cells that failed.

See `reports/observed-state-swap/local-paired.md`.
