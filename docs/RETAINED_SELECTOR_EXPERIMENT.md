# Retained-only structured selector negative control

Status: preregistered, not yet measured.

## Question

Can the explicit placement evaluation contract be attached after scalar
selection, without perturbing a deadline-bound episode?

`structured_retained` keeps candidate generation, scalar ranking and heap /
incumbent updates on the shipped fast path. Only the final selected decision
or selected Top-K portfolio is converted to `PlacementProposal`, named
`RankEvaluation`, `RiskAdjustment`, `CandidateEvaluation` and
`PlacementCommand` objects.

## Arms

- `base`: shipped scalar path.
- `base_null`: byte-identical runtime control.
- `structured_retained`: scalar streaming plus retained-only enrichment.

The same five Task B development configurations and three repeats used by the
failed eager control are retained. No final holdout is opened.

## Pass rule

The treatment must emit structured records on non-fallback decisions while
remaining within the pooled `base` + `base_null` noise floor for the complete
proxy vector: placed, fill, CoM telemetry, all shake metrics, priority/soft
cleanliness, terminal inclusion/valid/safe and failure channel. Policy time
and search attempts must not show a changed deadline regime.

No weighted total is formed. A placed/fill gain cannot override a regression
in the other components.

If this control passes, multi-axis selector work may operate only on the
retained portfolio. The first selector should be shadow-only and use
constraint/Pareto or lexicographic bands rather than guessed official weights.

## Execution

GitHub Actions workflow:
`.github/workflows/retained-selector-negative-control.yml`.
