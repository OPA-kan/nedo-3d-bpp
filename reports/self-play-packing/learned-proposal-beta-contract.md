# Learned proposal beta contract (Phase 3)

Status: frozen 2026-08-23 after design review. Supersedes the earlier
three-head sketch in two technical points recorded below.

## Goal

A proposal beta that eventually surfaces the actions search finds
Pareto-promising — without narrowing the human-given action domain,
without scalarizing objectives, and without baking the current behavior
policy into the proposal distribution.

## Primitive: paired difference, not dominance probability

The learned pairwise primitive is the **paired outcome difference
vector**

    DeltaY(s, a, a') = Y(a') - Y(a)

learned from same-state (and, where worlds exist, same-world) sibling
measurements. Antisymmetry `DeltaY(s,a',a) = -DeltaY(s,a,a')` is
enforced architecturally (an odd map over the difference of action
embeddings), not by a symmetrization loss.

Two earlier design errors are corrected here, on record:

- Dominance probability is **not** antisymmetric (world randomness
  allows P(a' beats a)=0.3 and P(a beats a')=0.2 simultaneously), so a
  Siamese-antisymmetric dominance head was wrong. Antisymmetry belongs
  to DeltaY.
- `frontier(a) ~ prod(1 - D)` smuggles an independence assumption:
  domination events across competitors correlate strongly (one shared
  weakness loses to everyone). It is not a frontier probability.

## Set-level quantities are frequencies over realizations

No closed-form dominance is ever computed. For a candidate set C, each
ensemble member (later: each world sample) m yields realized vectors,
and

    PF_m(C) = ParetoFrontier({Yhat_m(a) : a in C})
    p_PF(a | C) = (1/M) * sum_m 1[a in PF_m(C)]

Frontier membership stays set-dependent because the concept is; only
the primitive DeltaY is support-independent. This is the same
member-wise realization machinery the paired evaluator already uses,
and it extends unchanged when stream-suffix worlds become real.

## Heads

    Head 1: F(s,a)          = P(safe)            — feasibility
    Head 2: DeltaY(s,a,a')  paired difference    — shadow until Phase 4+
    Head 3: Yhat(s,a)       component vector     — auxiliary grounding

Teachers are environment outcomes only: safe/unsafe flags, measured
component vectors, paired differences. Legacy provider rank/score never
appears as a target (evaluation baseline only); legacy actions
participate as actions-with-outcomes.

## Phase discipline (the deepest correction)

Using dominance to weight beta before Vector MCTS exists would teach
`Q^{pi_rank0}`: the value of an action **under rank-0 continuation** —
locking today's behavior policy into the proposal distribution even
with no legacy targets. Therefore:

- **Phase 3A — feasibility proposal.** Only F(s,a) weights proposals:
  coverage emits M points, soft resampling by w = F, never a hard
  prune, and the raw coverage floor is permanent. The learning problem
  is crisp: raise safe yield from the measured 5.4% manifold rate,
  with the safe manifold discovered from PyBullet experience, not
  taught.
- **Phase 3B — paired Pareto head in shadow.** DeltaY is trained and
  evaluated but does not touch proposal weights. Its PoC metrics:
  per-head sign accuracy, within-root Kendall tau, same-world dominance
  classification, and **incomparability recognition** (pairs where
  neither dominates, labeled from measured data).
- **Phase 4 — Vector MCTS** produces Q_search(s,a): discoveries of the
  form "bad under rank-0, good when the future is searched".
- **Then beta is Pareto-ized**: its strategic teacher is the
  search-discovered frontier — propose candidate sets that contain the
  search-Pareto frontier with high probability. The loop
  NN_t -> MCTS_t -> NN_{t+1} closes here and not earlier.

## Honest provenance for resampled proposals

Halton points are deterministic, not iid draws from a density; no
continuous beta(a|s) density is claimed. What is recorded is exactly
what is true:

    coverage_seed
    coverage_sequence_index
    candidate_set_id                  (the generated finite set C)
    acceptance_model_id
    conditional_resampling_probability   w_i / sum_j w_j  within C

## Gates for 3A (no single-number target)

A safe-yield number alone is gameable by proposal collapse into narrow
safe regions. The gate is the conjunction:

- safe yield strictly above the coverage baseline;
- action diversity maintained (stratum entropy of proposals vs
  coverage at equal budget);
- coverage-only discoveries not lost (novel safe strata rate vs pure
  coverage at equal budget);
- recall of the measured comparison support maintained.

## Out of scope

Proposal weighting by any outcome head (until Phase 4+), scalarization
(Phase 10), replacing the coverage floor (never).
