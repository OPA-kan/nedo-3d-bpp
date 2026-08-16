# Safety-shadow calibration: preregistered protocol (Gate 1)

Committed before any calibration episode result is opened. This is the
first of the three predeclared gates on the learned safety ranker's road
from LOCO verdict (`state_model_beats_incumbent`) to a live reranker:

1. **Gate 1 (this document): live calibration.** Does the logit the
   shadow computes from live phi at decision time separate the actions
   that physically killed the episode from the actions that survived?
2. Gate 2 (only if Gate 1 passes): a rerank arm among retained top-K
   candidates, with a physical negative control and paired A/B against
   `reports/benchmarks/baseline.json` floors.
3. Gate 3: fresh-permutation confirmation under the same gates.

## Instrument

`safety-shadow-calibration.yml`: the seven guard configs
(b000-k15/k20/k40, b001-k20/k30, c000-k1, c001-k1) x replicates
{0,1,2}, single `base` arm, with `SAFETY_RERANK_SHADOW` pointing at the
committed artifact `candidate-mlp-safety-v1.json` (SHA-256
`064d0f97...`). The shadow is log-only — first contact verified
bit-identical trajectories with the knob on — so this wave measures the
unmodified policy while recording the model's opinion of every chosen
release.

## Labels (fixed before results)

Per episode, shadow events are ordered by `step`.

- Terminal channel `topple` or `slide` or `unsafe_other`: the **last**
  shadow event is labeled `fatal` (that placement failed physically);
  every earlier event is `surviving` (the episode continued past it).
- Terminal channel `safe_end`: all events `surviving`.
- Terminal channel `transport_invalid`: the fatal action is the fixed
  protocol fallback, which has no candidate and therefore no shadow
  event; all logged events are `surviving` and the episode contributes
  no fatal label. These episodes are counted and reported.

## Predeclared gates (all required to license Gate 2)

1. **Coverage**: at least 15 of 21 episodes complete (returncode 0)
   with a non-empty shadow trace, including at least one episode from a
   b-config and one from a c-config.
2. **Power**: at least 5 fatal-labeled events pooled. Fewer means the
   wave is underpowered — the verdict is "extend the wave", not pass
   or fail.
3. **Discrimination**: pooled rank AUC of `surviving` over `fatal`
   logits >= 0.70. (Offline within-state AUC was 0.825-0.842; the live
   bar is set lower because live phi and the offline corpus can drift,
   but a live shadow that cannot clear 0.70 has no business reranking.)
4. **Direction**: median fatal logit strictly below median surviving
   logit.

Descriptive (reported, not gated): calibration table of empirical
survival rate by logit band; splits by `candidate_kind` and by step
band (0-7 / 8-15 / 16+); per-config AUC where both labels occur.

Fail: the ranker stays shadow-only, the result is recorded in the
ledger, and Gate 2 does not run on this artifact. Pass: Gate 2's rerank
arm is licensed under its own preregistration. No retuning of the
artifact against these episodes in either case.
