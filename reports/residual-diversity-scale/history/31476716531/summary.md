# Residual-state diversity condition matrix

- Scenarios: 8
- Core 1/2-container x shelf/no-shelf coverage: True
- Positive / negative-risk labels: 984 / 619
- Arm (observed swap rounds): 64
- Portfolio construction: `['paired_control_seed_then_observed_state_swap']`, swaps applied: 576
- Acceptance verdict: **fail** (guard_failure)
- Completeness: complete
- Failed scenarios: ['m-single-empty-noshelf']

| scenario | containers | shelves | steps | safe positive | negative risk | mean physical NN delta | verdict |
|---|---:|---:|---:|---:|---:|---:|---|
| m-dual-dedicated-priority | 2 | 0 | 6 | 112 | 128 | 0.07518983416940983 | pass |
| m-dual-empty | 2 | 0 | 6 | 137 | 43 | 0.07872662004612511 | pass |
| m-dual-full-stream | 2 | 1 | 5 | 139 | 35 | 0.07755758866092663 | pass |
| m-dual-preloaded-dedicated | 2 | 0 | 6 | 148 | 81 | 0.07498929981185164 | pass |
| m-dual-shelf-mixed | 2 | 1 | 6 | 167 | 35 | 0.07505167850626782 | pass |
| m-single-empty-noshelf | 1 | 0 | 6 | 94 | 136 | 0.03398352930712529 | fail |
| m-single-empty-shelf | 1 | 1 | 6 | 106 | 82 | 0.06038324850333047 | pass |
| m-single-preloaded | 1 | 0 | 5 | 81 | 79 | 0.06923345660735533 | pass |

The 1/2-container x shelf/no-shelf cells must all be present; each scenario must retain a non-empty safe-positive arm and pass its paired physical-diversity guards. Scenario metrics are never pooled to hide a failed condition.
