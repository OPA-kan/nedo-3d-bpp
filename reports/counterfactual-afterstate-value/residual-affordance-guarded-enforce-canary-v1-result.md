# Guarded-enforce canary v1 result

Run `32438901241` at commit `4061c56` is a valid **FAIL** of the frozen
guarded-enforce protocol. All 30 episodes completed and the aggregate was
persisted before gate enforcement failed. Do not retune the v1 threshold or
reinterpret this wave as a pass.

## Frozen gate result

- causal reach: PASS, 101 guarded actions executed; zero guarded
  soft/priority contract regressions;
- trajectory value: FAIL, placed -2.333, fill -3.429, and completed steps
  -2.333 versus simultaneous base;
- special attributes: PASS, priority-clean +0.011 and soft-clean unchanged;
- physical safety: FAIL, shake peak kinetic energy +47.899, although the other
  four shake means did not worsen;
- terminal validity: PASS, included unchanged and valid +0.467.

The guard did its job: it preserved the five local special-attribute
contracts. The frozen residual-affordance ranking did not improve trajectory.

## Mechanism exposed by the executed traces

Of the 101 enforced actions, only two had a non-negative immediate-score
delta. The other 99 traded away immediate score. This follows the model's
frozen contract: its action tensor intentionally excludes `immediate_score`
and predicts searched residual-affordance Pareto direction, not a calibrated
trajectory return or action value.

The contrast between source-001 cases isolates the missing quantity. In the
worst case `b001-k20`, the mean model-utility gain at enforced steps was
`+0.268`, but mean immediate-score delta was `-0.206`; the trajectory lost
5.333 placed and 3.426 fill. In `b001-k30`, mean utility gain was similar at
`+0.242`, while immediate-score delta was only `-0.034`; placed was unchanged
and fill gained 1.061. Residual utility alone therefore does not price the
present cost of reaching the predicted future.

## Decision

Reject global guarded enforcement of `action-ridge-32351615182-v1`. Do not
submit or replicate it. Do not add a post-hoc hand-tuned coefficient or phase
threshold from this wave.

The next learning target must represent trajectory action value in observable
outcome units: candidate-conditioned suffix placed/fill and survival, while
retaining soft/priority and physical channels as independent constraints.
Equivalently, learn the advantage of choosing an action over the live
incumbent, including both immediate cost and future residual value. A new
model and canary require a new preregistration and unseen cases.

Compact official evidence is under
`reports/residual-affordance-enforce/history/32438901241/`; step-level evidence
remains in the run artifacts for GitHub Actions run `32438901241`.
