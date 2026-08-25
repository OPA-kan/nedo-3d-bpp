# Learned checkpoint comparator v1 — fails the paired gate at n=94

Date: 2026-08-25. Instrument: `train_checkpoint_comparator.py`.
Training data: checkpoint-oracle run `32813542928` (24 wave-2 cells, 94
hard roots, 34 interventions, H1+H3 checkpoint vectors for every safe
branch) joined with the wave-2 trigger dataset (state snapshots +
candidate geometry). Group-OOF by cell, 4 folds × 3 repeats × 3-member
ensembles, identical training recipe to the geometry selector. Inputs
are strictly decision-time: state, branch geometry, and the branches'
already-measured H ≤ 3 checkpoint vectors. The gate is a **paired
decision comparison on identical checkpoint vectors** against the
hand-written Pareto switch rule.

## Result — the Pareto rule wins decisively

| decision population | Pareto rule | comparator (geometry+checkpoint) | comparator (checkpoint only) |
|---|---:|---:|---:|
| ranker-pair IV conversion | **17/25** | 9/25 | 6/25 |
| ranker-pair keeper reproduction | **57/60** | 49/60 | 55/60 |
| full-support IV conversion | **23/34** | 13/34 | 4/34 |
| full-support keeper reproduction | 50/60 | 47/60 | **52/60** |
| overall top-1 (full support) | 0.777 | 0.638 | 0.596 |

- The geometry+checkpoint model trades keeper reproduction away without
  buying conversion. The checkpoint-only model degenerates toward
  "always keep the incumbent" (high keeper reproduction, almost no
  conversions) — the base-rate strategy.
- Offline note: the full-support H3 Pareto rule reaches 23/34 (0.676)
  intervention recall — the production budget-2 restriction, not the
  rule, is what costs recall down to 16-17/25.

## Diagnosis

At 94 roots / 34 positive decisions, the learner cannot rediscover the
inductive structure the Pareto dominance rule supplies for free. This
mirrors the geometry selector's history exactly: at wave-1 scale it was
miscalibrated and beaten by rank order; at wave-2 scale it drew level.
The comparator is one wave behind on data.

## What happens next (preregistered)

1. **Data scaling** (already collecting): checkpoint oracle re-runs on
   the 36-cell wave-3 cohort; the comparator retrains on the enlarged
   corpus. Expectation set honestly: the current gap (9 vs 17) is
   large; doubling data alone may narrow but not close it.
2. If wave-3 data does not close the gap, the next legitimate design is
   a **residual comparator** — keep the Pareto decision as the prior
   and learn only the deviation (when to overrule it) — preserving the
   rule's inductive bias instead of relearning it. Not implemented
   until the data-scaling result is in, one change at a time.
3. The production default is unaffected: incumbent + ranker next-best
   with the Pareto rule remains the measured best decision stack.
