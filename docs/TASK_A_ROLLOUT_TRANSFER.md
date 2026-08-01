# Task A rollout transfer

## Question

Task B pool-40 improved under the graded rollout while the all-pool policy
regressed. Task A sees the complete item set before execution and has a
separate optimization budget, so it is a plausible target, but the online
Top-K tie-break cannot be copied directly.

## Existing Task A mechanism

`Agent.optimize` already evaluates complete item orders with
`DryRunEvaluator`, using the common placement core and the lexicographic
objective `(placed count, placed volume, fill, stability, -CoG height)`.
Therefore Task A does not need the three-step visible-pool value as another
score. The transfer seam is the number and ordering of complete-order rollouts
that fit inside the offline budget.

The first local probe exposed two serial budget sinks. With a five-second
offline budget, legacy evaluation tested only the constructive seed because
the first unplaceable item consumed the remaining global deadline. After
bounding each item by 64 deterministic anchor attempts, the seed evaluation
finished in 1.82 seconds, but pair-macro generation consumed the remaining
3.18 seconds. Both stages must be bounded before order search can begin.

## Experiment

The feature is default-compatible:

- `OFFLINE_DRY_RUN_ATTEMPTS_PER_ITEM=0` preserves the legacy global deadline.
- A positive value uses the deterministic breadth-first candidate work budget
  for every item in an offline rollout.
- `OFFLINE_PAIR_MACRO_BUDGET_SECONDS=0` preserves the legacy remaining-budget
  behaviour; a positive value caps macro construction independently.

The first physical screening compares `base` with `bounded64`, using 30
internal optimization seconds, a 0.5-second macro cap, two source item sets
converted to Task A (`look_ahead=1`, `optimize=true`), and three repeats. This
is a transfer screen, not an adoption run. If it improves physical placed/fill
and evaluates multiple orders, rerun the winning setting at the official
150-second internal budget. If the offline proxy improves but physical
execution regresses, the dry-run/online placement-policy mismatch is the next
diagnostic boundary.
