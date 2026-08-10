# Retained-only structured selector negative control

Status: measured; passed the physical negative control.

Actions run: `31358020306` (45/45 episodes plus aggregate succeeded).

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

## Result

Treatment activation was confirmed on 283 of 286 decisions. At fixed work,
scalar and retained paths matched action, ordered Top-K, float-hex score and
attempts exactly at budgets 128 and 512.

In the deadline-bound Linux run, every per-case treatment difference remained
inside the pooled `base` + `base_null` spread for every reported component.
This includes placed/fill, CoM telemetry, all shake metrics, priority/soft
cleanliness, terminal inclusion/valid/safe, and policy time. Search attempts
per decision were 8,116 for treatment versus 8,292 and 8,329 for the two
controls, so no reduced-search regime was observed.

The aggregate treatment means (placed 18.067, fill 20.582) are not interpreted
as an improvement because both sit inside the per-case runtime floor. The
result establishes measurement non-interference, not policy quality.

Decision: the retained-only portfolio is the admissible integration boundary
for the next multi-axis shadow selector. Eager per-candidate materialization
remains rejected and the scalar live default remains unchanged.
