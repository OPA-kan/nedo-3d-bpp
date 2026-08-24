# Phase 4 + closed loop: the machinery works, the signal is not yet sharp

> **Assessment corrections (2026-08-24 review, on record).**
> 1. *Naming*: what ran is **Pareto best-first Tree Search v0**, not an
>    MCTS — there are no visit statistics N/Q/U, no Monte Carlo
>    sampling, no iterated select/expand/evaluate/backup updating edge
>    statistics. File names and the `vector_mcts` contract string stay
>    as committed artifact ids; the honest name is this one.
> 2. *Structural limit*: below the root the tree expands **legacy
>    top-k only** — beta can discover new entrances but not new deep
>    continuations. The interior must eventually take
>    `A_learned ∪ A_coverage`.
> 3. *Null-cause priority*, reordered: (1) no terminal information in
>    the labels — the teacher is bounded `G_{0:H}` and omits the
>    `DeltaY_measured + V(s_H)` composite that won the depth ladder,
>    which is exactly why the frozen V-MCTS-0 interface was kept;
>    (2) legacy interior support; (3) few active objectives;
>    (4) depth 3. "Because depth 3" alone is not the diagnosis.
> 4. *Evidence weight in Phase 3*: the strong result is held-out AUC
>    0.930; the 10.9%->15.1% yield gain (192 proposals per arm) is
>    supporting, not conclusive, at this sample size.
> 5. *Closed-loop eval limitation*: recall@4 re-ranks a finite set the
>    search had already validated as safe. The next evaluation must be
>    generative — fresh state, beta proposes K from scratch, search
>    judges — comparing frontier recall, safe yield, discovery and
>    terminal outcome.
>
> Verdict labels: **closed-loop architecture PASS · self-improvement
> NOT YET · true vector MCTS PARTIAL.** The breakthrough criterion is
> fixed: the first held-out `NN_1 > NN_0`.

Date: 2026-08-24 (Linux, PyBullet 3.2.7)
Data: `reports/self-play-paired-physical/p4-vector-mcts-20260823/`
Instruments: `run_vector_mcts.py`, `build_acceptance_dataset.py`,
`evaluate_loop_recall.py`

## What ran — the first full NN -> MCTS -> NN cycle

1. **Vector MCTS** on 35 roots across 6 cells (4 training, 2 held-out):
   additive component-vector backup, Pareto-frontier-first allocation,
   10 expansions per root to depth 3, root unions of legacy + measured
   coverage + **beta_0 proposals** (F-resampled). All runs clean.
2. **Search-Pareto labels**: 135 safe root candidates labeled by
   whether their explored subtree contributed a vector to the global
   achieved frontier — the strategic teacher the beta contract reserves
   for search.
3. **A head** trained on the training cells' labels
   (135 rows, train AUC 0.713), then **beta_1 = F x A** ranked held-out
   candidates against beta_0 = F and raw coverage order.

## Closed-loop verdict: honest null

Search-Pareto recall@4 on 12 held-out roots:

| arm | recall@4 |
|---|---|
| coverage order | 0.576 |
| beta_0 (F) | 0.569 |
| beta_1 (F x A) | 0.569 |

No arm separates. The loop executed end to end — proposals entered
search, search labeled them, the labels trained a new proposer — but
the strategic signal did not yet improve proposal ranking.

## Why, precisely

The label is not discriminative at this depth and scale:

- Of 228 safe root vectors, `soft_violation` was nonzero in 2 and
  `priority_covered` in 1: the dominance space is **effectively 2-D**
  (fill gain, surface TV) in these scenarios at depth <= 3.
- A 2-D frontier over ~6.5 candidates per root keeps **53%** of
  candidates on it (83/135 labeled positive). When more than half the
  class is positive, recall@4 near 0.57 is close to the ceiling for
  any ranking, and A has almost nothing to learn (135 rows, 61% base
  rate).

This mirrors every depth lesson so far: shallow bounded futures do not
separate candidates. The corridor-blocking divergences that search
exists for live deeper than 3 placements and in richer objectives.

## What this licenses and what it demands

- **Licensed:** the full loop machinery — vector backup, frontier-first
  allocation, search labels, acceptance training, recall evaluation —
  is real, tested, and cheap enough to iterate (each cell minutes, not
  hours).
- **Demanded before the next cycle:** a sharper teacher. The concrete
  levers, in expected-value order:
  1. deeper search budgets (depth 5-8, more expansions) so subtree
     futures actually diverge;
  2. richer active dimensions — terminal-connected stability via the
     Phase 9 V retrain, and scenarios/streams where soft/priority
     events actually fire;
  3. more roots (the entire loop above consumed ~35).
- The beta contract's phase discipline held: proposal weighting by the
  search teacher happened only after Vector MCTS existed, and the null
  is measured on held-out cells, not narrated.

## Loop status

`NN_0 -> MCTS_0 -> NN_1` has been executed once, with every artifact
committed. The cycle is now a runnable pipeline; making its teacher
sharp is the next phase of work, not more plumbing.
