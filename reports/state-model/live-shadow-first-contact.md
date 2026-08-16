# Live safety shadow: first contact

`SAFETY_RERANK_SHADOW` scored every decision of one local c000-k1
episode with the exported candidate-mlp artifact, computing phi from the
agent's own `release_risk.features` at decision time. Paired against the
identical episode with the shadow off: **both trajectories are
identical** (24 steps, same ending), confirming the log-only contract.

All 23 decisions produced logits, both candidate kinds covered. The
sequence is the phase-structure story seen through the model's eyes:

| phase | steps | chosen-action safety logit |
|---|---|---|
| open board | 0-5 | +12 to +25 |
| filling | 6-13 | +2 to +19 |
| crowded | 14-15 | +3.3 to +3.9 |
| **coin-flip zone** | **16-17** | **-0.13, -0.47** |
| late | 18-22 | +2.5 to +6.2 |

At steps 16-17 the policy executed actions the model scores below 50%
safe — exactly the states where a reranker could substitute a safer
retained candidate. This single episode is a contract check, not
calibration evidence; the calibration study (predicted logit versus
actual settle outcome across many episodes and regimes, split by step
band) is the next shadow deliverable, and it falls out of running the
existing ablation workflows with the knob set.

On the regime question: the perception layer needs no per-regime
training — the LOCO protocol already validates cross-scenario transfer
(held-out-case AUC 0.825), and physics is regime-invariant. What is
regime-dependent is the *pricing* of a given safety probability (the
57-death postmortem's "insufficient endgame penalty"): P(safe)=0.7 is
acceptable at step 30 and reckless at step 10. One perception model,
one hazard-priced decision rule — that is the architecture this shadow
is scaffolding toward.
