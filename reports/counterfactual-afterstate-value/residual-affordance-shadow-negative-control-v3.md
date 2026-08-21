# Residual-affordance shadow negative-control v3

This protocol is frozen after v2 run `32435231411` and before the first v3
episode is launched. V2 remains a failure: 23 of 65 physical comparisons
exceeded its preregistered simultaneous-base repeat spread. V3 does not
reclassify that wave.

## Why the physical calibration changes

V2 passed same-call decision invariance at every one of 287 observations,
blocked all six soft/priority contract regressions, and retained 126 guarded
action proposals. Its physical gate nevertheless failed. Seventeen of the 23
breaches had an exactly zero simultaneous-base spread. Pooling completed base
repeats showed that independent waves vary even when repeats within one wave
are bit-identical. The v2 noise estimator therefore measured too narrow a
domain; this is an instrument failure, not evidence that the shadow changed
the executed action.

## Frozen calibration

The physical reference is formed only from the `base` arms of completed runs
`32380902237`, `32381957502`, and `32435231411`. Every shadow-arm value in
those runs is excluded, regardless of its value. These run IDs may not be
changed after seeing the prospective v3 wave.

For each case and physical metric, the reference center is the mean of all
nine historical base repeats and the tolerance is their full range
(`max - min`). Missing metrics, fewer than three repeats in any calibration
wave, or fewer than three calibration waves fail closed.

## Frozen prospective gates

1. **Same-call decision invariance.** The selected action and retained
   portfolio must remain value-identical before and after shadow scoring at
   every observation.
2. **Attribute safety.** Every unrestricted increase in direct or stack-aware
   soft/priority coverage or priority routing must be blocked, with zero
   guarded regressions.
3. **Reach.** At least five guarded action changes must remain among at least
   50 observations.
4. **Current-base validity.** For every required metric, the current base mean
   must lie within one historical full-range tolerance of the historical base
   center. A wave outside this calibration domain is invalid, not a pass.
5. **Physical effect.** The prospective effect is the current shadow mean
   minus its simultaneous current base mean. Its absolute value must not
   exceed the historical base-only full-range tolerance for any required
   metric. Both current arms require at least three repeats.
6. **Cross-process hashes remain diagnostic only.** They cannot override
   gates 1--5.

The required physical metrics are the same 13 channels frozen in v2:
placement, fill, policy time, priority/soft cleanliness, all shake
displacement/energy/shift/topple channels, and terminal inclusion, validity,
and placed-safe status.

`scripts/evaluate_residual_affordance_shadow_gate_v3.py` is the sole
executable adjudicator. A prospective PASS licenses preparation of a
separately preregistered guarded enforce canary. It does not license an
official submission or establish an official-score improvement.
