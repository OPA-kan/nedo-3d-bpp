# Residual-state diversity condition matrix

- Scenarios: 8
- Core 1/2-container x shelf/no-shelf coverage: True
- Positive / negative-risk labels: 867 / 389
- Arm (observed swap rounds): 64
- Portfolio construction: `['paired_control_seed_then_observed_state_swap']`, swaps applied: 567
- Acceptance verdict: **pass** (pass)
- Completeness: complete
- Failed scenarios: []

| scenario | containers | shelves | steps | safe positive | negative risk | mean physical NN delta | verdict |
|---|---:|---:|---:|---:|---:|---:|---|
| m-dual-dedicated-priority | 2 | 0 | 6 | 112 | 63 | 0.07816397607281853 | pass |
| m-dual-empty | 2 | 0 | 6 | 137 | 43 | 0.07770535350637428 | pass |
| m-dual-full-stream | 2 | 1 | 5 | 139 | 35 | 0.080146545956537 | pass |
| m-dual-preloaded-dedicated | 2 | 0 | 6 | 116 | 69 | 0.09170015237333067 | pass |
| m-dual-shelf-mixed | 2 | 1 | 6 | 167 | 55 | 0.0681199027372425 | pass |
| m-single-empty-noshelf | 1 | 0 | 4 | 63 | 48 | 0.06963836466611026 | pass |
| m-single-empty-shelf | 1 | 1 | 6 | 90 | 56 | 0.08589982902771637 | pass |
| m-single-preloaded | 1 | 0 | 2 | 43 | 20 | 0.1087600605672416 | pass |

The 1/2-container x shelf/no-shelf cells must all be present; each scenario must retain a non-empty safe-positive arm and pass its paired physical-diversity guards. Scenario metrics are never pooled to hide a failed condition.
