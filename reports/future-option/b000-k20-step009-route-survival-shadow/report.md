# Future-option saved-snapshot evaluation

> Geometry-only replay from the same serialized observation. It does not restore PyBullet and does not claim to reproduce the historical action or the downstream physical trajectory.

- snapshot: `reports/replay-dataset/20260731_143112-b000-k20-weighted-class_aware-shadow-0fb74669-53f3e88bdd6f/step-009-state.json`
- case / step: `b000-k20` / 9
- repeats: 3
- item top-K: 10
- Q-live band: 0.15
- validation budget per hypothetical: 32
- route validation budget per hypothetical: 16

## Summary

| arm | selected items | elapsed mean | range | unique actions |
|---|---|---:|---:|---:|
| off | [21, 9, 5] | 5.010s | 5.007-5.012s | 3 |
| future-option | [17, 17, 21] | 5.998s | 5.913-6.062s | 2 |

## Per run

| arm | repeat | item | elapsed | action hash | future changed | aborted |
|---|---:|---:|---:|---|---|---|
| off | 0 | 21 | 5.010s | `af2c20dcc684e9c3` |  |  |
| future-option | 0 | 17 | 6.018s | `ea71c71b3e88dd92` | True | False |
| off | 1 | 9 | 5.012s | `34755cab89dd10b4` |  |  |
| future-option | 1 | 17 | 5.913s | `ea71c71b3e88dd92` | True | False |
| off | 2 | 5 | 5.007s | `aa4c4670fa7c6fec` |  |  |
| future-option | 2 | 21 | 6.062s | `af2c20dcc684e9c3` | True | False |

The JSON preserves every evaluated item's `Q_live`, Q gap, the four live future-option components, and the shadow quotient / static-conflict capacity descriptors. Only the four live components participate in selection. Route telemetry uses a separate corridor-stratified probe population and partitions after-state loss into `route_lost` and `space_lost`. `valid_candidates` is a count inside the sampled probe budget, not a full anchor population count.
