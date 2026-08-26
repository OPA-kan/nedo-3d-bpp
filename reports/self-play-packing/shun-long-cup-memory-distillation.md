# Preregistration: Cup memory distillation into シュンロング

Date: 2026-08-26. Direction set by the project owner before this training
run. This is the separately preregistered training step required by the
Diversity Cup contract; it does not alter season matrices, the registry, or
the frozen evaluation set.

## Question

Can verified counterfactual memories found by the diverse studs be carried
across episodes without erasing the promoted preference policy?

The resulting lineage is **シュンロング**: プリフヒバリ's frozen Set
Transformer ensemble is the base, while the same final-head adapter used by
シュンヒバリ becomes persistent after learning from offline strict physical
forks. Unlike the exhibition clone, its memory does not reset after an
episode.

## Frozen Cup 003 distillation card

- Base model: プリフヒバリ `pi2-pref-w6`, learning run **32890092906**,
  artifact `rollout-policy-model`.
- Memory source: Diversity Cup 003 run **32935678296** only.
- Eligible examples: all **56** strict genuine-terminal actor-vs-champion
  pairs under the current 4-head rule (fill, soft, priority-covered,
  priority-misrouted). Cup 001/002 are excluded from this first run because
  their historical verdict contracts straddle the removed surface-TV veto.
- Input: pre-action state sets and action geometry only. Terminal outcomes
  are labels and never inference features.
- Update: one ordered pass; final scoring-head delta only; learning rate
  0.05, two logistic steps per pair, hard per-member trust radius 1.0. These
  are the already frozen シュンヒバリ settings, not tuned on Cup results.
- Leakage boundary: leave one complete Cup course cell out. All stud views
  of the same scenario/stream remain in one group.
- Output: a load-compatible frozen ensemble artifact plus pre/post
  leave-one-cell-out AUC, average precision, accuracy, and log loss.

This run is a **capability/distillation run only**. It must not dispatch a
league match or touch promotion state. Same-corpus improvement proves only
that memory was written; held-out movement estimates transfer within the Cup
distribution.

## Formal validation after this run

If the artifact is structurally valid, the first causal test will be
preregistered separately: frozen シュンロング versus the unchanged frozen
プリフヒバリ on the standard paired league harness, with **no race-time
forks**. That isolates carried memory from the fork's decision authority.
Only after that comparison may a second arm add online adaptation again.

## Value lineage (prospective, not part of Cup 003 training)

A future value horse should not claim to compute perfect board value. Its
first target is narrower and measurable: predict the terminal-rollout
preference or expected value-of-computation for a candidate, then spend
physics only where the prediction is uncertain. It remains a separate
lineage and must beat an equal-budget rollout baseline before entering a
formal challenge.
