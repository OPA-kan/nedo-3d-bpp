# Prior art positioning and the Pareto-PUCT design brief

Date: 2026-08-24. Survey credit: project owner; the multi-objective
bandit/MCTS mapping below adds the implementation basis.

## Where this project sits (owner's survey, recorded)

- **Puche & Lee, IROS 2022** adapts AlphaGo to single-player 3D-BPP:
  PUCT edge statistics (Q, N, prior, exploration term), visit
  distribution pi_MCTS proportional to N, and the full
  NN -> MCTS -> pi_MCTS -> NN retraining loop. The question "does this
  closed loop work in 3D-BPP at all" already has a published Yes.
  Notably they found *rollouts beat a learned value* in 3D-BPP
  (CUT-1: 83.4% vs 64.7%) — a standing caution for V at leaves that
  matches our own depth-ladder result (a weak V degraded H1 ordering).
- **Zhao et al., AAAI 2021** evaluates lookahead paths as
  `sum of rewards + V(s_H)` — the scalar ancestor of our
  head-semantic `DeltaY + V_sa` composition.
- **PCT line (ICLR 2022; planning extension)**: receding-horizon
  planning over packing configuration trees with leaf V — same family
  as our v1 target.
- **Fang et al. (owner-reported, KDD 2026)**: standard PUCT
  over-trusts the learned prior under distribution shift; their
  Shift-Aware PUCT mixes `alpha * P_learned + (1-alpha) * P_random`.
  Independent support for our coverage-floor principle, extended into
  the tree prior.
- **Zhu et al., CIKM 2021**: NN-pruned tree search — a warning: hard
  NN pruning is exactly what our permanent coverage floor exists to
  prevent.
- Unclaimed intersection (as far as surveyed): 3D-BPP x hard physics
  authority x continuous broad support x **vector/Pareto search** x
  the closed loop. The scalar-to-vector move is our genuine
  difficulty and our genuine novelty.

## Depth-vs-outcome evidence (owner's survey 2026-08-24, recorded)

Does deeper reading improve *final* space utilization in 3D-BPP? The
literature answer is yes — conditionally:

- **Zhao et al., AAAI 2021, Fig. 8**: BPP-k lookahead with MCTS,
  x = lookahead k, y = average space utilization. Utilization rises
  with k, and MCTS tracks the k! brute-force permutation search at a
  fraction of the cost. Their stated mechanism is ours: reserve space
  for future items — avoid the locally good move that kills the
  corridor.
- **Zhao et al., "Learning Practically Feasible Policies" (follow-up),
  Fig. 9(b)**: k = 1..8; "the performance of MCTS improves with the
  number of lookahead" — for *parallel* MCTS. The same figure shows
  **serial MCTS degrading beyond k > 5**: fixed budget over an
  exploding tree stops finding the good branches. Depth adds
  information; it can still subtract search quality.
- **Fang et al. (owner-reported, KDD 2026)**: "only the performance of
  MPC-PCT improves consistently as N increases" — a *well-allocated*
  MCTS is the arm whose utilization is monotone in horizon; at their
  production N=4 it beats plain DRL, and >15% over the PCT baseline
  under distribution shift.

So the licensed claim is not "deeper always fills more" but:

> **horizon ↑ improves final utilization iff allocation/budget keeps
> search quality up.** Zhao already measured the failure branch.

This maps exactly onto our own artifacts: the H3 fill advantage that
vanished at H4 (`reports/paired-search-follow/run-32469901132.md`) is a
measured false depth-preference; the one future-sensitive root where H3
value inverts immediate fill and wins
(`reports/counterfactual-dag-search/decision-32447121770.md`,
`m-dual-shelf-mixed` step 12: rank-0 loses H1 fill 11.25 vs 11.51 but
wins H3 fill 14.07 vs 13.33) is our single in-repo positive control for
"a distant consequence flips the right move". Both poles of the
literature result already exist here at n=1 each; the ladder's job is
to measure their rates under a search that can actually explore.

### The decisive event to hunt: frontier resurrection

The evidence the program actually wants is not "H=8 beat H=3 on
average" but the per-action event:

    a not in PF_{H=shallow}  and  a in PF_{H=deep}  and,
    under terminal probes,   a in PF_{terminal}

— deep search resurrecting an action that shallow evaluation discards,
confirmed by realized terminals. Its evil twin, **false resurrection**
(`a in PF_deep` but `a not in PF_terminal`), is the Zhao serial-MCTS
degradation made measurable per action. The depth ladder counts both;
the ratio is the direct test of whether added depth is buying signal
or noise at the current allocation quality. Preregistered in
`pareto-search-ablation-program.md`.

## The bottleneck, restated

Pareto Tree Search v0 has **no exploration principle**: frontier-first
allocation is exploitation-only. Scalar MCTS gets "bad now, unexplored,
dig anyway" for free from `Q + c P sqrt(N)/(1+n)`. The vector version
of that term is the missing piece — not depth.

## Pareto-PUCT v1 design brief

Foundations: Drugan & Nowe 2013 (Pareto UCB1, multi-objective bandits
— per-arm optimistic vectors, uniform selection over their
non-dominated set, logarithmic Pareto regret) lifted to trees as in
Chen & Liu (RSS 2019, Pareto MCTS).

- Edge statistics: `N(s,a)`, running mean vector `Qbar(s,a)` (achieved
  frontier sets retained for labels), per-head empirical dispersion.
- Optimistic vector, one bonus for every head:

      U(s,a) = Qbar_std(s,a)
             + c * P(a|s) * sqrt(sum_b N(s,b)) / (1 + N(s,a)) * ONES

- Selection: uniform (or least-visited) among children whose `U`
  vectors are Pareto-non-dominated within the sibling set.
- Prior with a floor, per Shift-Aware PUCT and our own principle:
  `P = alpha * P_beta + (1 - alpha) * uniform` — the coverage floor
  lives inside the tree prior too.
- Backup: iterated select -> expand -> evaluate (head-semantic
  `DeltaY + V_sa`) -> backup of mean vectors and visits. This is the
  step that makes it an actual MCTS.

### Contract question to settle before implementing (flagged, not
### decided here)

Dominance is scale-free; an additive bonus is not — it needs per-head
units. Hypervolume-style indicators are rejected: the reference point
is an implicit weighting. The candidate rule is standardization by the
**empirical dispersion of head values observed inside the search** —
a statistic, not a preference. Whether dispersion-standardization is
admissible under the no-exchange-rate contract must be decided
explicitly and recorded before Pareto-PUCT lands.

## Visit-distribution teacher fixes the fat-frontier label

The closed-loop null traced to a binary `in_search_pareto` label with a
61% positive rate. Once Pareto-PUCT produces visit counts, the beta
teacher becomes `pi_search proportional to N(s,a)` — Puche's visit
distribution, vectorized: graded even when the frontier is fat, because
visits concentrate where optimistic non-dominance persists under
scrutiny, not merely where a point sits on a wide frontier.

## Placement in the ablation ladder

The frozen ladder gains one stage, still one change at a time:

    v0 -> v0+V -> v1 (learned interior) -> **v2: Pareto-PUCT
    allocation replaces frontier-first** -> depth ladder on v2

Depth stays last: both Puche and the shift-aware line say search
strength comes from allocation before it comes from depth.
