# Future-option saved-snapshot evaluation

> Geometry-only replay from the same serialized observation. It does not restore PyBullet and does not claim to reproduce the historical action or the downstream physical trajectory.

- snapshot: `reports/replay-dataset/20260731_143112-b000-k20-weighted-class_aware-shadow-0fb74669-53f3e88bdd6f/step-009-state.json`
- case / step: `b000-k20` / 9
- repeats: 3
- item top-K: 10
- Q-live band: 0.15
- validation budget per hypothetical: 32

## Summary

| arm | selected items | elapsed mean | range | unique actions |
|---|---|---:|---:|---:|
| off | [5, 5, 5] | 5.009s | 5.004-5.014s | 1 |
| future-option | [19, 17, 17] | 5.865s | 5.842-5.896s | 2 |

## Per run

| arm | repeat | item | elapsed | action hash | future changed | aborted |
|---|---:|---:|---:|---|---|---|
| off | 0 | 5 | 5.008s | `aa4c4670fa7c6fec` |  |  |
| future-option | 0 | 19 | 5.896s | `a09a5bae39ecf540` | True | False |
| off | 1 | 5 | 5.014s | `aa4c4670fa7c6fec` |  |  |
| future-option | 1 | 17 | 5.842s | `ea71c71b3e88dd92` | True | False |
| off | 2 | 5 | 5.004s | `aa4c4670fa7c6fec` |  |  |
| future-option | 2 | 17 | 5.857s | `ea71c71b3e88dd92` | True | False |

The JSON preserves every evaluated item's `Q_live`, Q gap, the four live future-option components, and the shadow quotient / static-conflict capacity descriptors. Only the four live components participate in selection. `valid_candidates` is a count inside the sampled probe budget, not a full anchor population count.
