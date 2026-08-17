# Post-shake attribute instrument: preregistered protocol

Committed 2026-08-17 JST before any result is opened. Motivation
(`soft-axis-is-the-single-blind-instrument`): the local soft proxy
reads the settled state before the shake while the official procedure
may score after it; every learning label generated without closing
this gap would bake the blind spot into a trained policy at scale.
This instrument must exist and pass its fidelity gate BEFORE any
probe-generated training corpus is built (ladder rung 3) and before
rung 2's gates are finalized.

## Mechanism (offline instrument, no agent change)

`scripts/measure_post_shake.py`:

1. Rebuilds a recorded final episode state in the probe world (the
   validated physics clone: official dynamics constants, true settled
   poses from the episode's final step_metrics or evaluation state).
2. Applies the OFFICIAL shake procedure cloned verbatim from
   simulator/src/ground_handling/evaluator.py (the gravity-vector
   sequence and step counts as implemented there -- constants copied,
   never invented; any place the official code reads config values,
   the instrument reads the same config).
3. After the shake, recomputes: per-item displacement and topple
   angle, soft/priority coverage violations on the POST-shake poses
   (same candidate_attribute_violations contract), and summary
   metrics post_shake_soft_clean, post_shake_priority_clean,
   post_shake_toppled, post_shake_max_shift, peak kinetic energy.

## Fidelity gate (all required before the instrument is trusted)

Validation data already exists: every run_risk_ablation row records
the bundled evaluator's own shake_response. On >= 40 recorded
episodes spanning base and quiet_guard arms:

1. Per-episode Spearman correlation of cloned vs recorded
   shake_max_shift >= 0.8, and of shake_items_shifted >= 0.8.
2. Cloned shake_items_toppled matches recorded within +-1 on >= 80%
   of episodes.
3. Directional reproduction of the wave-level guard signature: the
   clone must show quiet_guard's peak-KE excess over base with the
   same sign as the recorded +24%.

Pass: the instrument becomes (a) a required column in future wave
adjudications (post-shake soft/priority gates where relevant), (b)
the label generator for rung 3 -- training targets become
(settle_safe, post_shake_stable, post_shake_coverage), the full
scored objective, and (c) the local readout that finally makes the
official soft axis attackable without spending submissions. Fail: the
gap between the probe world and the bundled shake is itself the
finding; recorded, and official submissions remain the only soft
readout. No constant in the clone may be tuned to pass -- they are
the official code's or nothing.
