# Residual-state diversity condition matrix

- Scenarios: 6
- Core 1/2-container x shelf/no-shelf coverage: True
- Positive / negative-risk labels: 752 / 497
- Arm (observed swap rounds): 64
- Portfolio construction: `['paired_control_seed_then_observed_state_swap']`, swaps applied: 473
- Acceptance verdict: **pass** (pass)
- Completeness: complete
- Failed scenarios: []

| scenario | containers | shelves | steps | safe positive | negative risk | mean physical NN delta | verdict |
|---|---:|---:|---:|---:|---:|---:|---|
| m-dual-dedicated-priority | 2 | 0 | 6 | 112 | 128 | 0.07518983416940983 | pass |
| m-dual-empty | 2 | 0 | 6 | 137 | 43 | 0.07872662004612511 | pass |
| m-dual-preloaded-dedicated | 2 | 0 | 6 | 116 | 69 | 0.0870245387354689 | pass |
| m-dual-shelf-mixed | 2 | 1 | 6 | 167 | 55 | 0.06392982680152347 | pass |
| m-single-empty-noshelf | 1 | 0 | 6 | 131 | 136 | 0.06998418224862457 | pass |
| m-single-empty-shelf | 1 | 1 | 6 | 89 | 66 | 0.08557696885392567 | pass |

The 1/2-container x shelf/no-shelf cells must all be present; each scenario must retain a non-empty safe-positive arm and pass its paired physical-diversity guards. Scenario metrics are never pooled to hide a failed condition.
