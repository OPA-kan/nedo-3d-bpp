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

That seam turned out to be the whole problem: at the official budget the
legacy default evaluated 3.0 of its allowed 1000 complete orders, because a
single dry run cost about 35 seconds. The search was starved, not disabled --
one neighbour was adopted, but only on a lower-priority lexicographic key.

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

## Adoption

Run `30717998654` is the adoption run: bundled source 000, official budgets,
three repeats per arm.

| arm | placed | fill | evaluated orders | optimization s |
|---|---:|---:|---:|---:|
| base | 20 / 20 / 20 | 29.298 | 3.0 | 112.1 |
| bounded128 | 25 / 25 / 25 | 34.949 | 51.3 | 147.3 |

`bounded128` is adopted as the shipped Task A default (ADR-002): placed +25%,
fill +19.3%, centre-of-mass height 0.753 -> 0.735 m, near-misses 0 in both
arms, policy time held at about 6.51 s, optimization inside the 150 s
internal budget. The bounded arm's fill has min = max across the three
repeats, so its order and its physical outcome were identical every time; the
base arm's fill varied 27.541 to 30.176 while always evaluating 3 orders.

The defaults are now `OFFLINE_DRY_RUN_ATTEMPTS_PER_ITEM=128` and
`OFFLINE_PAIR_MACRO_BUDGET_SECONDS=0.5`. Setting them to `0` and `0.0`
restores the legacy behaviour. Because the shipped default is now the
treatment, `scripts/run_task_a_rollout.py` pins the `base` arm to the legacy
values explicitly instead of unsetting the variables -- an arm that merely
unsets them would measure the treatment and report a null result. The runner
also gained a `default` arm, which unsets everything and therefore measures
exactly what a submission does.

The flip itself was verified by re-running both arms once locally on 4 vCPU
before changing the default, with the `default` arm setting no `OFFLINE_*`
variable at all. Both reproduced CI bit-for-bit: fill 34.94904885879026 for
`default` (the CI bounded128 constant) and 27.540718986088258 for `base` (the
CI base minimum). So the shipped path, not just the forced one, produces the
adopted result. Per-repeat numbers and the local reproduction table are in
`reports/task-a-rollout/history/30717998654/analysis.md`.

Task B and Task C are unaffected. Both constants are read only by
`DryRunEvaluator` and `Agent.optimize`, and the official harness calls
`optimize` only when the case sets `agent.optimize`, which is Task A alone.
`test_offline_budget_never_reaches_the_online_policy` pins that scope.

Two limits carry forward, and neither is closed by this run.

- The offline proxy is a **relative order selector, not an absolute score.**
  The adopted arm's proxy predicted 23 placements where physical execution
  achieved 25. Do not report or target proxy values.
- The **fallback problem is untouched.** Both arms end with `is_valid` and
  `is_placed_safe` false — base at step 21, the adopted arm at step 26 — so
  neither is a passing episode under the repository's own rule. This work
  made the order search run; it did not fix late-episode action supply. The
  gain is that the failure arrives five placements later.

Scope: one bundled case, two attempt budgets measured (64 rejected, 128
adopted). Other cases, budgets at 256 and above, and an item-count-adaptive
budget are all unmeasured.
