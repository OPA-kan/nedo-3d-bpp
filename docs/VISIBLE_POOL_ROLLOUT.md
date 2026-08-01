# Visible-pool rollout shadow

This experiment replaces the degenerate `q + gamma*q` diagnostic with a
graded, bounded rollout over the currently visible Task B pool. It does not
model unknown future arrivals and therefore is not a general state value.

## Contract

For each immediate candidate under comparison:

1. apply the candidate to a copied container state;
2. remove its item from the visible pool;
3. greedily apply at most `depth - 1` additional **settled** candidates;
4. cap every future search by an anchor-attempt count, not wall time;
5. report the lexicographic value
   `(placed_count, added_volume, -sum(P_rot), -sum(P_slide))`.

The rollout proxy policy deliberately does not use `Q_live` as its primary
key. It prefers settled candidates, then support quality and low height;
`Q_live` is only the final deterministic tie-break. This prevents the new
measurement from recursively reproducing the Ranker error it is testing.

An immediate release candidate is applied through the existing
`settled_proxy_candidate` and marked `initial_release_proxy=true`. If a later
rollout transition would be a release, the branch stops before applying it
with `terminal_reason=release_transition_uncertain`. The output must not be
read as a PyBullet counterfactual.

## Offline command

```bash
python3 scripts/analyze_visible_pool_rollout.py \
  --snapshot reports/replay-dataset/<dataset>/step-009-state.json \
  --divergence-report reports/ranker-divergence/<run>/report.json \
  --output-dir reports/visible-pool-rollout/<run> \
  --top-k 8 --depth 3 --attempts-per-step 512
```

The observed left/right divergence actions are forced into the comparison
even when a full-population immediate rank would place them outside Top-K.
This makes the saved b000-k20 step 9 regression directly testable without
claiming that the offline population is identical to either deadline-limited
live search.

## Live shadow

Set `VISIBLE_POOL_ROLLOUT_MODE=shadow`. The live search is unchanged, but an
observer retains its best accepted candidate for every stable item. Before
the bounded Top-K is evaluated, candidates are diversified by the item class
`(sorted dimensions, mass, is_soft, is_prioritized)` so duplicate baggage
instances cannot fill the entire comparison set. The default is `off` and
there is deliberately no `enforce` mode yet.

Live shadow bypasses (and therefore does not warm) the global analytic
container-Z interval cache. This prevents telemetry from making later
deadline-limited searches deeper merely by pre-populating production cache
entries.

On the saved b000-k20 step-9 state, the non-diverse immediate Top-3 consisted
of three identical 0.65 x 0.45 x 0.25 items and all rollout values were equal.
Class diversification exposed items 5, 17 and 28 and graded them 2, 1 and 0
future settled placements respectively. The one-decision shadow added about
0.15 seconds locally and returned the same item-5 action.

Linux screening run 30708961145 measured 79 shadow decisions across five
development configurations: 39 were non-degenerate, 17 proposed another
item, average shadow cost was 102.8 ms/step and the maximum was 398.3 ms.
The arm aggregate was slightly above base, but the independently executed
base was unstable across consecutive screening runs, so no score effect is
claimed. This establishes discrimination and feasible cost only; enforcement
needs a separate repeated ablation.
