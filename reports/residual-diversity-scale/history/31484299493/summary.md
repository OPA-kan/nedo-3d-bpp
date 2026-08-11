# Residual-state diversity condition matrix

- Scenarios: 8
- Core 1/2-container x shelf/no-shelf coverage: True
- Positive / negative-risk labels: 1056 / 571
- Arm (observed swap rounds): 64
- Portfolio construction: `['paired_control_seed_then_observed_state_swap']`, swaps applied: 666
- Acceptance verdict: **pass** (pass)
- Completeness: complete
- Failed scenarios: []

| scenario | containers | shelves | steps | safe positive | negative risk | mean physical NN delta | verdict |
|---|---:|---:|---:|---:|---:|---:|---|
| m-dual-dedicated-priority | 2 | 0 | 6 | 112 | 79 | 0.06154073613310515 | pass |
| m-dual-empty | 2 | 0 | 6 | 137 | 43 | 0.07872662004612511 | pass |
| m-dual-full-stream | 2 | 1 | 6 | 170 | 59 | 0.07738498332031586 | pass |
| m-dual-preloaded-dedicated | 2 | 0 | 6 | 164 | 86 | 0.07217505845309027 | pass |
| m-dual-shelf-mixed | 2 | 1 | 6 | 167 | 35 | 0.07505167850626782 | pass |
| m-single-empty-noshelf | 1 | 0 | 6 | 131 | 136 | 0.06998418224862457 | pass |
| m-single-empty-shelf | 1 | 1 | 6 | 106 | 82 | 0.06038324850333047 | pass |
| m-single-preloaded | 1 | 0 | 4 | 69 | 51 | 0.08108896215417911 | pass |

The 1/2-container x shelf/no-shelf cells must all be present; each scenario must retain a non-empty safe-positive arm and pass its paired physical-diversity guards. Scenario metrics are never pooled to hide a failed condition.
