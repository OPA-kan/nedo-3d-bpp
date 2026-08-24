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
| **v0+R (oracle/reference only)** | genuine-terminal frozen-rank0 rollout at every reached leaf; record `PF_H1`, measured/evaluated `PF_search`, `PF_terminal` and resurrection recall | v0 allocation, supports, no V; never an execution policy |
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

`v0+R` is the oracle layer, not a candidate policy. It is deliberately placed
before `v0+V`: first measure whether terminal frontier resurrection exists and
whether v0 deepens or recovers it without model error. Only after the oracle is
validated may `V_sa` be judged as an approximation to that terminal reference.
The implementation contract is
`reports/self-play-packing/terminal-rollout-resurrection-oracle.md`.

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

## Depth-ladder metrics (v2, H = 3/5/8)

Frontier thinning is *secondary*. The primary questions are:

- `tau(search root ordering, terminal truth)` — terminal probes
  (rank-0 continuations, the standing reference arm) supply the truth;
- **terminal-Pareto recall** — does the search frontier contain the
  actions whose realized terminal vectors are non-dominated?
- **frontier resurrection vs false resurrection** (preregistered
  2026-08-24; literature basis in
  `prior-art-and-pareto-puct-notes.md`). Per root, per action:
  - *resurrection*: `a not in PF_{H=3}`, `a in PF_{H=5 or 8}`, and
    the terminal probe confirms `a in PF_terminal` — deep search
    found a distant-consequence action that shallow evaluation
    discards. This is the event the whole program exists to produce.
  - *false resurrection*: `a in PF_{H=5 or 8}` but
    `a not in PF_terminal` — Zhao's serial-MCTS degradation (deeper
    horizon, starved allocation) measured per action.
  - Report both counts and their ratio at each H. Depth earns its
    physics budget only if resurrections appear and the ratio does
    not collapse toward false resurrections as H grows. A rising
    false-resurrection share at fixed budget is the preregistered
    signature of budget starvation, not of "depth doesn't matter".

The expectation from prior art (Zhao AAAI 2021 Fig. 8; the
practically-feasible follow-up Fig. 9(b); Fang's monotone-in-N
MPC-PCT) is: utilization improves with horizon **iff** allocation
keeps search quality up — which is why this ladder runs on v2
(Pareto-PUCT) and not on v0's exploitation-only allocation. Serial
MCTS degrading beyond k>5 in Zhao is the published version of our own
run `32469901132` (an H3 fill advantage that vanished at H4).

Standing regression root: `m-dual-shelf-mixed` step 12
(`counterfactual-dag-search/decision-32447121770.md`) — the one
measured root where immediate fill inverts the H3-best action. Any
depth-ladder run should include it (or its single-agent analog) as a
positive control: a working deep search must keep rank-0 there.

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
