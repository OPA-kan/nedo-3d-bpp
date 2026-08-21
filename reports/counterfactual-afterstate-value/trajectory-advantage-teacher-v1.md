# Trajectory-advantage teacher v1

Status: implemented; awaiting a fresh physical H3/B3 corpus.

## Question

Can the counterfactual DAG supervise the relative trajectory value of a
candidate directly, without adding the hand-written immediate ranking score to
a residual-space prediction?

## Frozen target

For every branching physical source state, `a0` is exactly the retained
rank-zero behaviour-policy action and `a` is another retained action from the
same candidate portfolio:

`A_H(s,a;a0) = G_H(s,a) - G_H(s,a0)`.

`G_H` is the source-to-leaf physical outcome, including the first action and
the searched suffix. Suffix paths use the declared distribution that chooses
uniformly among retained children at every future node. It is a bounded-search
distribution, not an arrival-stream probability.

## Independent heads

- placed count and fill proxy;
- CoG and surface variation;
- priority and soft violations;
- post-shake physical and attribute axes when the graph measured them;
- survived steps, horizon survival, physical-failure rate, and terminal-failure
  rate.

Every head records candidate/incumbent mean return, pessimistic return, raw
advantage, direction-normalized advantage, and relation. No weighted sum is
formed.

## Leakage and distribution contracts

- `immediate_score` is absent from both candidate action tensors and every
  target. It is not reconstructed as an additive reward.
- Candidate and incumbent share source state, future stream, physics settings,
  horizon, branch budget, and suffix search policy.
- `split_group_id` combines policy generation, future stream, case, and
  scenario axes. Multiple roots from one physical trajectory cannot cross
  evaluation folds, even if their step indices cross the regime boundary.
- `policy_generation` identifies the behaviour policy that supplied `a0`.
  Later agent-generated data must append a generation; old roots are not
  overwritten or silently relabelled.
- Soft/priority and physics remain independent constraint heads and are not
  traded against placed/fill by a scalar label.

## Admission gate

The workflow fails unless the corpus has at least one row, all rows have both
action and afterstate tensors, no action tensor contains `immediate_score`, all
trajectory groups are fold-consistent, and placed/fill/horizon-survival heads are
present.

Passing this gate establishes only a valid teacher corpus. Model learning,
online H3 physics rollout, shadow selection, and episode improvement each need
their own later gate on unseen physical roots.
