# Future-option saved-snapshot evaluation

> Geometry-only replay from the same serialized observation. It does not restore PyBullet and does not claim to reproduce the historical action or the downstream physical trajectory.

- snapshot: `reports/replay-dataset/20260731_143112-b000-k20-weighted-class_aware-shadow-0fb74669-53f3e88bdd6f/step-009-state.json`
- case / step: `b000-k20` / 9
- repeats: 1
- item top-K: 10
- Q-live band: 0.15
- validation budget per hypothetical: 64

## Summary

| arm | selected items | elapsed mean | range | unique actions |
|---|---|---:|---:|---:|
| off | [9] | 5.008s | 5.008-5.008s | 1 |
| future-option | [17] | 6.115s | 6.115-6.115s | 1 |

## Per run

| arm | repeat | item | elapsed | action hash | future changed | aborted |
|---|---:|---:|---:|---|---|---|
| off | 0 | 9 | 5.008s | `34755cab89dd10b4` |  |  |
| future-option | 0 | 17 | 6.115s | `ea71c71b3e88dd92` | False | False |

The JSON preserves every evaluated item's `Q_live`, Q gap, the four live future-option components, and the shadow quotient / static-conflict capacity descriptors. Only the four live components participate in selection. `valid_candidates` is a count inside the sampled probe budget, not a full anchor population count.
