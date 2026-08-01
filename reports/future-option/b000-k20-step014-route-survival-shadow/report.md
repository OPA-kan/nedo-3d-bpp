# Future-option saved-snapshot evaluation

> Geometry-only replay from the same serialized observation. It does not restore PyBullet and does not claim to reproduce the historical action or the downstream physical trajectory.

- snapshot: `reports/replay-dataset/20260731_143112-b000-k20-weighted-class_aware-shadow-0fb74669-53f3e88bdd6f/step-014-state.json`
- case / step: `b000-k20` / 14
- repeats: 1
- item top-K: 10
- Q-live band: 0.15
- validation budget per hypothetical: 32
- route validation budget per hypothetical: 16

## Summary

| arm | selected items | elapsed mean | range | unique actions |
|---|---|---:|---:|---:|
| off | [25] | 5.004s | 5.004-5.004s | 1 |
| future-option | [25] | 5.692s | 5.692-5.692s | 1 |

## Per run

| arm | repeat | item | elapsed | action hash | future changed | aborted |
|---|---:|---:|---:|---|---|---|
| off | 0 | 25 | 5.004s | `99740db46fc2cbd0` |  |  |
| future-option | 0 | 25 | 5.692s | `99740db46fc2cbd0` | False | False |

The JSON preserves every evaluated item's `Q_live`, Q gap, the four live future-option components, and the shadow quotient / static-conflict capacity descriptors. Only the four live components participate in selection. Route telemetry uses a separate corridor-stratified probe population and partitions after-state loss into `route_lost` and `space_lost`. `valid_candidates` is a count inside the sampled probe budget, not a full anchor population count.
