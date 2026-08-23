# Joint outcome scorer teacher contract (PoC-2)

Status: active contract for the first PoC-2 slice.
Depends on: `multi-head-branch-teacher-contract.md` (JointOutcomeSample v2),
`paired-exogenous-physical-audit-20260823.md` (instrument audit).

## Question this model answers

Can a neural scorer predict the measured bounded joint physical outcome of
a root candidate well enough that candidate ordering, pairwise dominance
and Pareto structure on **held-out roots** match the paired physical
measurements — i.e. can it replace part of the expensive physical rollout
budget?

## Target semantics

The model estimates

`F(s, a) ~ Y_{0:H} = raw joint outcome vector of JointOutcomeSample v2`,

the bounded root-to-leaf outcome under the behavior continuation policy.
It is explicitly:

- not `V*`;
- not a terminal outcome model (`Y_T`): horizon-bounded, matching
  `target_semantics = root_action_bounded_outcome_not_leaf_value`;
- not a leaf-state value (`V^pi_behavior(s_H)` stays the separate
  behavior-value Set Transformer contract).

The eventual terminal structure remains
`observed root->leaf joint delta + leaf->terminal joint V`; this contract
covers the first summand's predictor.

## Inputs

- root state set tensors (`observed_set_tensors_no_step_no_future_labels`):
  container, packed-item and visible-item sets;
- the commanded root action: acting item's visible feature row, container
  index, local place position, orientation index.

Forbidden inputs (same reason as the behavior-value protocol — the scorer
must value actions independently of who proposed them):

- provider rank, score, pool index, prior, selection or provenance fields;
- `mixture_weight`, proposal probabilities, coverage metadata.

Provenance and `candidate_set_id` are carried through the dataset for
splitting and audit only, never as features.

## Targets, masks, jointness

- Targets are the nine branch-measured heads (maximize/minimize plus the
  diagnostics; the three post-shake stability heads are structurally
  unmeasured in branch rollouts and are excluded, per the physical audit).
- `head_eligibility` masks supervision; censored heads are never zero
  filled. Samples censored on every head (non-horizon termination) carry
  no joint loss.
- The model output is a joint Gaussian over the head vector: mean plus a
  full lower-triangular Cholesky factor, trained with masked joint NLL.
  Per-head conditional means alone cannot express joint events such as a
  placed-gated expectation; the joint covariance keeps the predictive
  distribution usable for dominance estimates. A richer distributional
  family (mixtures, autoregressive heads) is a v2 decision, not this
  slice.
- Epistemic uncertainty: 3+ independently initialized ensemble members on
  bootstrap-resampled root groups; disagreement is variance across
  members.

## Known gap (declared, not hidden)

The model receives no exogenous world coordinates, so it predicts the
outcome distribution marginal over worlds. Model-based dominance
probabilities therefore lack the same-world coupling that the paired
physical estimator exploits; they are computed by independent sampling
from the two predictive distributions and are expected to be conservative
(variance overestimated). The held-out comparison must report this as
model-vs-paired-measurement agreement, not as an unbiased estimate of the
same quantity.

## Split and evaluation

- Split unit: collection cell (scenario x stream x game seed). Held-out
  cells never contribute training roots. A secondary root-held-out split
  inside training cells is reported for contrast.
- Held-out metrics, all computed per root then aggregated:
  1. per-head candidate ordering: Kendall tau between predicted means and
     measured paired means;
  2. pairwise dominance agreement against measured same-world joint
     dominance point estimates;
  3. Pareto recovery: precision/recall of the measured point-estimate
     frontier membership;
  4. rollout-saving proxy: regret of executing the model's top pick versus
     the measured best candidate, per head.
- No gate on the live agent is licensed by this PoC. It only decides
  whether the physical-budget reduction direction is worth pursuing.
