# Residual-state diversity condition matrix

- Scenarios: 8
- Core 1/2-container x shelf/no-shelf coverage: True
- Positive / negative-risk labels: 1018 / 639
- Arm (observed swap rounds): 64
- Portfolio construction: `['paired_control_seed_then_observed_state_swap']`, swaps applied: 542
- Acceptance verdict: **pass** (pass)
- Completeness: complete
- Failed scenarios: []

| scenario | containers | shelves | steps | safe positive | negative risk | mean physical NN delta | verdict |
|---|---:|---:|---:|---:|---:|---:|---|
| m-dual-dedicated-priority | 2 | 0 | 6 | 112 | 128 | 0.06790545129816765 | pass |
| m-dual-empty | 2 | 0 | 6 | 137 | 43 | 0.07031221358831218 | pass |
| m-dual-full-stream | 2 | 1 | 6 | 170 | 59 | 0.07275847526817873 | pass |
| m-dual-preloaded-dedicated | 2 | 0 | 6 | 148 | 81 | 0.07212373291206524 | pass |
| m-dual-shelf-mixed | 2 | 1 | 6 | 167 | 55 | 0.0671697254344883 | pass |
| m-single-empty-noshelf | 1 | 0 | 6 | 114 | 128 | 0.06505559706207935 | pass |
| m-single-empty-shelf | 1 | 1 | 6 | 89 | 66 | 0.08428807453959546 | pass |
| m-single-preloaded | 1 | 0 | 5 | 81 | 79 | 0.062164244473595 | pass |

The 1/2-container x shelf/no-shelf cells must all be present; each scenario must retain a non-empty safe-positive arm and pass its paired physical-diversity guards. Scenario metrics are never pooled to hide a failed condition.
