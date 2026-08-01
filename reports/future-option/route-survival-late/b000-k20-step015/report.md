# Future-option saved-snapshot evaluation

> Geometry-only replay from the same serialized observation. It does not restore PyBullet and does not claim to reproduce the historical action or the downstream physical trajectory.

- snapshot: `reports/replay-dataset/20260731_013609-b000-k20-weighted-class_aware-shadow-0fb74669-86041076d589/step-015-state.json`
- case / step: `b000-k20` / 15
- repeats: 1
- item top-K: 10
- Q-live band: 0.15
- validation budget per hypothetical: 32
- route validation budget per hypothetical: 16

## Summary

| arm | selected items | elapsed mean | range | unique actions |
|---|---|---:|---:|---:|
| off | [5] | 5.003s | 5.003-5.003s | 1 |
| future-option | [5] | 5.197s | 5.197-5.197s | 1 |

## Per run

| arm | repeat | item | elapsed | action hash | future changed | aborted |
|---|---:|---:|---:|---|---|---|
| off | 0 | 5 | 5.003s | `9146042e3fba3948` |  |  |
| future-option | 0 | 5 | 5.197s | `9146042e3fba3948` | False | False |

The JSON preserves every evaluated item's `Q_live`, Q gap, the four live future-option components, and the shadow quotient / static-conflict capacity descriptors. Only the four live components participate in selection. Route telemetry uses a separate corridor-stratified probe population and partitions after-state loss into `route_lost` and `space_lost`. `valid_candidates` is a count inside the sampled probe budget, not a full anchor population count.
