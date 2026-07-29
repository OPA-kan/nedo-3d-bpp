# Mode B starvation diagnostics

**Status:** Accepted / diagnostics implemented

**Scope:** Measurement only. This specification does not change item ordering,
candidate ranking, class quotas, lookahead selection, or fallback behavior.

## Goal

Determine why priority and soft items are not placed before a scene ends,
without attributing the public aggregate score to Mode B before scene-level
evidence exists.

The diagnostic must distinguish:

1. exclusion by the ten-item online evaluation cap;
2. search units not started before the deadline;
3. no accepted candidate observed during the bounded search;
4. an accepted candidate generated but excluded from the immediate top-K;
5. a top-K item evaluated but not selected;
6. a validated placement-core action selected;
7. a fixed-fallback target, which is not counted as a successful selection.

## Audience

Developers comparing Mode B item-selection policies on reproducible simulator
runs and offline replays.

## Online data contract

When `NEDO_POLICY_TRACE_PATH` is set, every decision event adds:

```text
selection_stages:
  visible_item_indices
  item_cap_item_indices
  search_started_item_indices
  candidate_generated_item_indices
  candidate_topk_item_indices
  future_probe_item_indices

item_lifecycle[]:
  item_index
  item_class
  first_visible_step
  visible_steps
  search_included_steps
  search_started_steps
  candidate_generated_steps
  candidate_topk_steps
  future_probe_steps
  selected_step
  selected_action_source
  starvation_observation
```

`item_class` is `priority`, `soft`, or `normal`; priority takes precedence if
both flags are present.

`candidate_generated` means that the existing deadline-bounded placement
search yielded at least one accepted candidate for the item. It is not an
oracle feasibility claim. The provisional `starvation_observation` therefore
describes only what the online search observed.

`future_probe` is not a current-item selection gate. It records which visible
items were used to probe the next-step value after each immediate top-K
candidate. A top-K current item remains eligible even when it is not itself in
the future-probe set.

The lifecycle is cumulative for one agent episode and resets in
`get_init_states`.

## Offline shadow regret contract

True before/after feasibility and regret are computed offline from a
pre-action snapshot. They are not recomputed inside the 6.5-second policy
budget.

For a candidate action \(a\), record losses and gains separately:

\[
L_i(s,a)=[u_i(s)-u_i(T(s,a))]_+,
\qquad
G_i(s,a)=[u_i(T(s,a))-u_i(s)]_+.
\]

Class profiles remain vectors:

\[
(L_{\mathrm{priority}},L_{\mathrm{soft}},L_{\mathrm{normal}})
\]

and are not used as a lexicographic hard decision rule until correlation with
placement count, rule scores, and physical validity has been measured.

The first version may use binary \(u_i\). Later versions may use oracle-safe
candidate area, supported candidate count, available container count,
transport margin, or support margin.

## Runtime and compatibility constraints

- With `NEDO_POLICY_TRACE_PATH` unset, no lifecycle bookkeeping is performed.
- Existing item order, top-K, inner-pool limits, rank keys, and returned action
  remain unchanged.
- No full-pool feasibility search is added to `policy`.
- Candidate IDs are collected only from work the placement search already
  performs.
- A fixed fallback is marked `fixed_fallback_target`, not `selected`.
- A failed action cannot establish `feasible_at_termination`; that value must
  be evaluated from the last valid pre-action snapshot.

## Non-goals

- class-aware quotas;
- Mode B regret ranking;
- diversity beam;
- release risk gate;
- inference of hidden leaderboard weights;
- claiming that Mode B starvation caused the aggregate public score.

## Acceptance criteria

1. A priority item outside the ten-item cap is reported as
   `excluded_by_item_cap`.
2. An item with an accepted candidate outside immediate top-K is reported as
   `generated_but_low_rank`.
3. Selection stages are separately visible in the JSONL decision event.
4. A placement-core selection records its first selected step.
5. A fixed fallback does not record a successful selected step.
6. Existing policy-trace fields remain available.
7. The trace-disabled submission path avoids lifecycle bookkeeping.
8. Focused trace tests and the complete CPU unit suite pass.

## Decision after measurement

- Frequent `excluded_by_item_cap`: implement class quota first.
- Frequent `search_not_started`: make search scheduling class-aware.
- Frequent `generated_but_low_rank`: evaluate regret/diversity ranking.
- Frequent `no_candidate_observed`: run the offline candidate oracle.
- Frequent `topk_not_selected` followed by later loss: add Mode B shadow regret.
- Items remain feasible at the last valid snapshot: address termination or
  selection starvation rather than geometry.
