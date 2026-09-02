# The arena now measures all three tasks, and what the agent is actually doing

Date: 2026-09-01.

## Task A is measurable after all

`docs/BLOCKED_WORK.md` records `task-a-second-case` as blocked: "ケースが
無い。配布は 000/001 のみで、両方とも既に使用済み". That is true of
*distributed* cases and false of Task A instances.

`constructive_order` is **not permutation-invariant** — 0 of 5 shuffles
of the same 41 items reproduce its output order, because only **10
distinct item types** occupy those 41 slots and the composite score ties
constantly, leaving input order to break them. So permuting the stream,
which `build_scenario_matrix` already does 234 ways, yields genuinely
different Task A episodes.

That matters because the standing Task A conclusions rest on two cases.
F8 — the finding that the offline evaluator optimises against a
*pre-risk greedy* policy while the shipped runtime is risk-on, and that
matching them made things worse — was decided on **2 cases × 3
repeats**. After watching six arena cells invert the sign of an effect
this morning, two cases is not a number to close a question on.

## The arena takes `--task a|b|c`

Task A and C configs are derived from the scenario's Task B config, Task
A through the shipped `build_task_a_config` so a cell here is the same
object the Task A workflow runs. Episode caches are keyed by task, and
the existing 200-cell Task B corpus was migrated rather than discarded.

One Task A cell costs about 64 s including the offline pass, so a
full Task A arena is roughly the price of a Task B one.

## Correction: pool 1 does not mean "nothing to rank"

Written earlier today: on Tasks A and C the online pool is 1, so the
candidate set holds one entry and a learned ranker has no choice.
**Measured, that is wrong.**

| Task A, `single-empty-noshelf`, `permute-000-809` | candidates/state |
|---|---|
| `agent` — generic provider only | 1.28 (max 2) |
| `champ-all` — plus rule-alpha and the current-agent advisor | **2.18 (max 3)** |

With a single visible item the union still supplies alternatives,
because rule-alpha and current-agent propose *different placements for
that same item*. So Tasks A and C are exactly where "which placement"
is the only question — and the union is what makes the question askable
at all.

Which is also the axis the learner has never been trained on. Every
distillation to date learned to choose an item, because at pool 10 the
generic provider offers one placement per item and nothing else.

(Both arms scored 26.89 on that cell, n = 1.)

## What the shipped agent actually does

Worth writing down plainly, because it is not what the surrounding
machinery suggests.

**The submission contains no learned component.** `agent/agent.py`
imports no torch, loads no weights. The champion ensemble, the
advantage model, the value function — none of them ship.

`policy(observation)` is a cascade of fallbacks: `_closed_loop_choice`,
then `PlacementCore.choose`, then a conditional retry, then
`rescue_choose` under a reserved slice of the budget, then
`last_resort_relaxed_action`.

And the choice itself, `Ranker.score` (`agent.py:4517`), is one
weighted sum over every (visible item × container × orientation ×
candidate pose) the attempt budget affords:

    12.0 · volume                    prefer placing large items
   +  2.0 · support_ratio            prefer a well-supported footprint
   + (-0.55·y if priority else 0.35·y)   priority items forward, others back
   -  0.12 · |x|                     prefer the lateral centre
   -  0.18 · z · mass                do not lift mass high
   +  routing                        priority item into priority bay +8.0;
                                     non-priority into it -2.5
   +  zone                           0 by default (ZONE_ORDER=off)

then a risk adjustment. Task A's offline ordering runs the same
`PlacementCore.choose` inside `DryRunEvaluator`, so these six terms
decide the order as well as the placements.

**Those six numbers are hard-coded literals**, duplicated between
`Ranker.evaluate` and `Ranker.score` and kept in sync by hand. They are
not knobs; nothing in the repository can vary them.
`BLOCKED_WORK.md` names this the weakest point in the ledger —
"`RANKER_WEIGHTS` は役割のみ文書化、値の根拠なし … ノブ化は数行" —
and it has stayed open because there was no instrument able to resolve
what a change to them does.

There is one now. The arena resolves a 0.3 fill-point difference over
200 cells and runs all three tasks. Making the weights configurable is
a few lines; sweeping them is one night.

That is also where today's two other findings meet. The learner never
chose a placement because these six terms already had; and the 70.5%
self-termination rate is these six terms selecting moves that physics
rejects.
