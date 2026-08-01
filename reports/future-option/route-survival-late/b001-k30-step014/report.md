# Future-option saved-snapshot evaluation

> Geometry-only replay from the same serialized observation. It does not restore PyBullet and does not claim to reproduce the historical action or the downstream physical trajectory.

- snapshot: `reports/replay-dataset/20260731_120259-b001-k30-weighted-class_aware-shadow-5119fcc9-fedb535ea218/step-014-state.json`
- case / step: `b001-k30` / 14
- repeats: 1
- item top-K: 10
- Q-live band: 0.15
- validation budget per hypothetical: 32
- route validation budget per hypothetical: 16

## Summary

| arm | selected items | elapsed mean | range | unique actions |
|---|---|---:|---:|---:|
| off | [31] | 5.013s | 5.013-5.013s | 1 |
| future-option | [27] | 6.269s | 6.269-6.269s | 1 |

## Per run

| arm | repeat | item | elapsed | action hash | future changed | aborted |
|---|---:|---:|---:|---|---|---|
| off | 0 | 31 | 5.013s | `bee6a5e18e7f30b2` |  |  |
| future-option | 0 | 27 | 6.269s | `992c3638c8137dd1` | True | False |

The JSON preserves every evaluated item's `Q_live`, Q gap, the four live future-option components, and the shadow quotient / static-conflict capacity descriptors. Only the four live components participate in selection. Route telemetry uses a separate corridor-stratified probe population and partitions after-state loss into `route_lost` and `space_lost`. `valid_candidates` is a count inside the sampled probe budget, not a full anchor population count.
