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
