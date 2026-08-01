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

The first physical screening compared `base` with `bounded64`, using 30
internal optimization seconds, a 0.5-second macro cap, two source item sets
converted to Task A (`look_ahead=1`, `optimize=true`), and three repeats. This
is a transfer screen, not an adoption run. If it improves physical placed/fill
and evaluates multiple orders, rerun the winning setting at the official
150-second internal budget. If the offline proxy improves but physical
execution regresses, the dry-run/online placement-policy mismatch is the next
diagnostic boundary.

Run `30717533328` confirmed the structural transfer but rejected 64 attempts:
the evaluator expanded from one complete order to 58 orders for source 000
and 102 for source 001, yet it severely under-estimated the executable prefix.
Physical placed changed 20.0 to 19.33 for source 000 and 13.0 to 14.33 for
source 001, with lower fill in both. A 30-second local probe at 128 attempts
evaluated three orders per source and improved the offline proxy from 19 to 21
and from 12 to 18 respectively. The second physical screen therefore compares
`base` with `bounded128`; the simultaneous base arm remains necessary even
though Task A is more deterministic than Task B.

Run `30717848749` was positive at 30 seconds. Source 000 improved from 20 to
23 physical placements and fill 29.171 to 33.124 in every repeat, while the
number of evaluated complete orders increased from 1 to 13.7. The synthetic
Task-A conversion of source 001 improved mean placed 14.33 to 17.0 and fill
23.164 to 24.340, though its base retained timing variance. The adoption run
therefore freezes `bounded128`, uses only the real bundled Task A source 000,
and restores the official 150-second internal / 180-second external
optimization budgets with three repeats.

## Official-budget result

Actions run `30717998654` confirmed the transfer on the bundled Task A case.
All three repetitions agreed on the physical outcome:

| arm | placed | fill proxy | complete-order evaluations | offline proxy placed | optimization seconds |
|---|---:|---:|---:|---:|---:|
| base | 20.0 | 29.298 | 3.0 | 21.0 | 112.1 |
| bounded128 | **25.0** | **34.949** | **51.3** | **23.0** | 147.3 |

Thus bounded complete-order rollout added five physical placements (+25%)
and 5.651 fill points (+19.3%) while staying inside both the 150-second
internal and 180-second external optimization budgets. The optimized order
was deterministic across the three bounded repetitions. Mean final CoM
height also moved from about 0.753 m to 0.735 m, and neither arm recorded a
5--30 degree near miss or a rotation above 30 degrees.

The absolute dry-run proxy remains imperfect: it predicted 23 placements for
the order that physically placed 25. This does not invalidate its use for
relative order selection, but it does rule out treating the proxy as a
calibrated physical score. Both arms eventually returned an action that was
included but not valid/placed-safe, so terminal candidate/fallback behaviour
remains a separate limitation.

## Verdict

Task A transfer is positive, but the transferable object is not Task B's
online three-step tie-break. It is a Task-A-specific increase in deterministic
complete-order rollouts under the offline budget. `bounded128` is an adoption
candidate for Task A only. The environment defaults remain legacy-compatible
(`OFFLINE_DRY_RUN_ATTEMPTS_PER_ITEM=0`) until an explicit adoption/merge
decision; Task B and Task C behaviour is unchanged.
