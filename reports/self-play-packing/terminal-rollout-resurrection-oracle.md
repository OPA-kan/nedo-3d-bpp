# Terminal-rollout resurrection oracle

Status: implemented instrument; no Linux/PyBullet matrix has run yet.

The first physical pilot is wired through
`.github/workflows/terminal-resurrection-oracle.yml`: six preregistered Phase-4
cells, two roots per cell by default, and paired `measured` / `rollout` arms.
The aggregate refuses the comparison unless root ids, root candidate ids and
all one-step measured vectors are identical between the two arms.

## Question

Before adding `V_sa` or Pareto-PUCT, establish whether the environment
contains root actions that look dominated after one physical step but are
non-dominated under a frozen-policy genuine-terminal continuation, and whether
the current search actually deepens or recovers those actions.

This is an oracle/reference arm, not an execution policy and not a training
label licensed for the existing acceptance-head pipeline.

## Invocation

`scripts/run_vector_mcts.py` now accepts:

```text
--leaf-eval measured|rollout
--rollout-top-k 3
--rollout-max-steps 40
```

`measured` preserves the v0 search-teacher contract
`vector_mcts_search_pareto_v1`. `rollout` uses the separate
`pareto_tree_search_terminal_oracle_v2` contract, so an oracle result cannot be
silently consumed as the old search-Pareto teacher.

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

## Frozen boundaries

- no `V` is loaded;
- v0 allocation remains Pareto-frontier-first;
- tree-interior candidate support remains unchanged;
- Pareto-PUCT edge statistics are not part of this slice;
- dominance uses the existing frozen dominance heads. Terminal shake metrics
  are recorded in terminal metrics/evaluation but are not silently added to the
  Pareto space.

## Required first physical run

Run paired `measured` and `rollout` arms on the same fresh roots, including the
standing future-sensitive positive-control root or its single-agent analogue.
Validate deterministic replay and require complete genuine-terminal sibling
sets before quoting resurrection prevalence or recall. The first output remains
draft until that instrument check passes.
