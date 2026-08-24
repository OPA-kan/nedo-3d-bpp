# Pareto search ablation program (frozen 2026-08-24)

Status: frozen experimental program for the next work cycle. Governs
how Pareto Tree Search v0 evolves toward a true vector search. The
essence, fixed up front:

> **Make the search see the right future before making it deeper.**
> Depth without terminal-connected evaluation and without freed
> interior support just mixes two confounds.

## The ladder — one change at a time, always against v0

| stage | change | held fixed |
|---|---|---|
| **v0 (baseline, frozen)** | none — depth 3, Pareto-frontier-first allocation, root union legacy ∪ coverage ∪ beta, interior legacy top-k, no leaf V | everything |
| **v0+V** | leaf evaluation becomes `Q_H = DeltaY_{0:H} (+) V_sa(s_H)` with head-semantic composition (below) | depth, allocation, supports |
| **v1 = (v0+V) + learned interior** | interior expansion support becomes `A_learned ∪ A_coverage`; legacy/rescue kept as audit arms only | depth, allocation, leaf V |
| **v2 = v1 + Pareto-PUCT** | allocation becomes Pareto-PUCT (optimistic vectors, non-dominated selection, floor-mixed prior, iterated backup — see `prior-art-and-pareto-puct-notes.md`); beta teacher becomes the visit distribution | depth, supports, leaf V |
| **v2(H = 3, 5, 8)** | depth ladder on v2 | everything else |

Depth stays last on purpose: the prior art (Puche 2022; the
shift-aware PUCT line) says search strength comes from
exploration/exploitation allocation before it comes from depth, and
our v0 has no exploration principle at all.

Never combine stages in one comparison: a joint improvement with mixed
changes attributes nothing.

### Prerequisite for v0+V: retrain V on the single-agent distribution

The frozen two-player V is unusable here twice over: it consumes game
features (player_to_move, block_length, handoff_count) that the
single-agent state does not have, and its behavior distribution is the
two-player scaffold. The required `V_sa` trains on the **single-agent
suffix value targets already collected** (P3A: 126 genuinely-terminated
roots with component returns and terminal stability, schema
`single_agent_v1`). No new physics needed to start.

## Head-semantic-aware composition (never a blind vector add)

`(+)` above is per-head, by semantics:

| head | composition | reason |
|---|---|---|
| fill, placed | `Delta_{0:H} + V_return(s_H)` | measured prefix + predicted remaining suffix, additive |
| soft/priority counters | `Delta_{0:H} + V_return(s_H)` | event counts are additive |
| surface TV, CoM | `Delta_{0:H} + V_return(s_H)` | suffix deltas, additive (diagnostic heads stay diagnostic) |
| terminal_stability_* | `V(s_H)` **replaces** — nothing measured to add | terminal-only quantity; adding a branch delta would double count |
| stream_completed | `V(s_H)` alone | terminal-only |

## Depth-ladder metrics (v1, H = 3/5/8)

Frontier thinning is *secondary*. The primary questions are:

- `tau(search root ordering, terminal truth)` — terminal probes
  (rank-0 continuations, the standing reference arm) supply the truth;
- **terminal-Pareto recall** — does the search frontier contain the
  actions whose realized terminal vectors are non-dominated?

Only if deeper search moves these does depth earn its physics budget.

## Generative closed-loop evaluation (replaces recall-on-prevalidated)

The last cycle's recall@4 re-ranked a finite set the search had already
validated. The next evaluation is generative: fresh state ->
`beta_t` proposes K from scratch -> search judges. Compare beta_0 vs
beta_1 on: safe yield, novel discovery, search-Pareto recall,
terminal-Pareto recall, and the terminal outcome vector. Episode
execution (true PoC-3: `a_t^search` vs rank-0 on fresh episodes) comes
only after that.

## Breakthrough criterion (unchanged)

The first held-out `NN_1 > NN_0` under the generative evaluation is
the moment the self-improving agent starts. Nothing before that is
claimed as self-improvement.
