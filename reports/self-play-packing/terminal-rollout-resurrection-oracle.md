# Terminal-rollout resurrection oracle

Status: oracle validated on Linux/PyBullet; allocation-separated Pareto-PUCT
benchmark implemented and pending its physical matrix.

The physical pilot is wired through
`.github/workflows/terminal-resurrection-oracle.yml`: six preregistered Phase-4
cells and two roots per cell by default. The current workflow pairs measured
v0 frontier-first with measured Pareto-PUCT. Genuine-terminal rollouts score
root actions in both arms but are never exposed to allocation. The aggregate
refuses the comparison unless root ids, candidate ids, H1 vectors, terminal
vectors, censoring and terminal resurrection truth are identical.

## First oracle result

Actions run `32682204705` completed all six cells and aggregate. Ten roots and
45 safe root actions had exact paired H1 evidence, 10/10 roots reached complete
genuine-terminal sibling sets, and no root was censored. Eleven actions across
6/10 roots were outside `PF_H1` but inside `PF_terminal`.

The run's rollout-guided allocation deepened 11/11 resurrection actions and
kept 10/11 on its evaluated frontier. A cross-arm audit of the independent
measured arm found that v0 deepened 8/11 but kept 0/11 on its bounded measured
frontier. The 90.9% number is therefore evidence that terminal information can
recover the actions, not an unbiased estimate of search discovery: rollout had
also guided that arm's allocation. This is why allocation and terminal scoring
are now separate contracts.

## Question

The original oracle gate, before adding `V_sa` or Pareto-PUCT, was to establish
whether the environment
contains root actions that look dominated after one physical step but are
non-dominated under a frozen-policy genuine-terminal continuation, and whether
the current search actually deepens or recovers those actions.

This is an oracle/reference arm, not an execution policy and not a training
label licensed for the existing acceptance-head pipeline.

## Invocation

`scripts/run_vector_mcts.py` now accepts:

```text
--leaf-eval measured|rollout
--terminal-audit
--allocation frontier|pareto-puct
--c-puct 2.0
--rollout-top-k 3
--rollout-max-steps 40
```

`measured` preserves the v0 search-teacher contract
`vector_mcts_search_pareto_v1`. `rollout` uses the separate
`pareto_tree_search_terminal_oracle_v2` contract, so an oracle result cannot be
silently consumed as the old search-Pareto teacher.

`measured --terminal-audit` uses
`pareto_search_terminal_audit_v3`. Terminal rollouts run only for safe root
actions; `evaluation_vector` remains measured at every tree node. Changing the
allocation to `pareto-puct` therefore cannot see terminal truth.

Pareto-PUCT keeps incoming-edge visits, online mean vectors and empirical
dispersion. Sibling means are standardized by their observed per-head range;
the count-confidence bonus is added equally to all standardized heads. This
uses scale but no objective exchange rate. The optimistic non-dominated set is
formed first; uniform prior and low visits choose within it. Learned prior
mixing remains out of this slice.

For every newly reached search node, rollout mode reconstructs the root prefix,
forces that node's action path, then follows the frozen legacy rank-0 policy
through the same exact fresh-replay physical legal filter. A terminal vector is
eligible only for:

- `stream_exhausted`;
- `no_retained_candidate`;
- `no_safe_retained_candidate`.

Continuation caps, truncation and physical failure censor the terminal vector.
No partial delta is converted to a terminal target.

## Per-root outputs

The result keeps these concepts separate:

- `h1_pareto_candidates`: one-step measured root vectors;
- `measured_search_pareto_candidates`: all bounded measured vectors reached by
  the tree;
- `evaluated_search_pareto_candidates`: vectors used by the configured leaf
  evaluator;
- `terminal_pareto_candidates`: one frozen-policy genuine-terminal vector per
  root action;
- `terminal_frontier_resurrection_candidates`:
  `PF_terminal \\ PF_H1`;
- `deepened_candidates`: root actions for which the search reached depth > 1.

Each root action also records all membership flags and maximum explored depth.
If any safe sibling lacks a genuine terminal, `terminal_truth_complete=false`
and the complete-root terminal frontier and resurrection claim are withheld.

The aggregate `resurrection_summary` reports action-count denominators and
three deliberately distinct recalls:

1. resurrection actions actually deepened;
2. resurrection actions recovered by the measured bounded-search frontier;
3. resurrection actions recovered by the configured evaluated frontier.

This avoids calling a root action "found" merely because every root action was
initialized once.

## Current allocation-benchmark boundaries

- no `V` is loaded;
- v0 remains Pareto-frontier-first and the comparison arm changes allocation
  only to Pareto-PUCT;
- tree-interior candidate support remains unchanged;
- terminal audit runs only at root actions and never enters allocation;
- current priors are uniform; no learned proposal preference enters PUCT;
- dominance uses the existing frozen dominance heads. Terminal shake metrics
  are recorded in terminal metrics/evaluation but are not silently added to the
  Pareto space.

## Required allocation run

Run paired measured v0 and measured Pareto-PUCT arms on the same fresh roots.
The aggregate must validate identical H1 and terminal evidence and require
complete genuine-terminal sibling sets before quoting allocation recall.
Primary metrics are resurrection deepening recall, resurrection frontier
recall, terminal-Pareto recall, false-frontier count and physical steps.
