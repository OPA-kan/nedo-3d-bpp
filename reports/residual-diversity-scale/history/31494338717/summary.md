# Residual-state diversity condition matrix

- Scenarios: 8
- Core 1/2-container x shelf/no-shelf coverage: True
- Positive / negative-risk labels: 961 / 653
- Arm (observed swap rounds): 64
- Portfolio construction: `['paired_control_seed_then_observed_state_swap']`, swaps applied: 481
- Acceptance verdict: **pass** (pass)
- Completeness: complete
- Failed scenarios: []

| scenario | containers | shelves | steps | safe positive | negative risk | mean physical NN delta | verdict |
|---|---:|---:|---:|---:|---:|---:|---|
| m-dual-dedicated-priority | 2 | 0 | 6 | 112 | 128 | 0.06790545129816765 | pass |
| m-dual-empty | 2 | 0 | 6 | 137 | 43 | 0.07031221358831218 | pass |
| m-dual-full-stream | 2 | 1 | 5 | 139 | 103 | 0.07444105644375104 | pass |
| m-dual-preloaded-dedicated | 2 | 0 | 5 | 117 | 63 | 0.07441513466692384 | pass |
| m-dual-shelf-mixed | 2 | 1 | 6 | 167 | 55 | 0.0671697254344883 | pass |
| m-single-empty-noshelf | 1 | 0 | 6 | 114 | 128 | 0.06505559706207935 | pass |
| m-single-empty-shelf | 1 | 1 | 6 | 106 | 82 | 0.05831295570576428 | pass |
| m-single-preloaded | 1 | 0 | 4 | 69 | 51 | 0.0787405036724919 | pass |

The 1/2-container x shelf/no-shelf cells must all be present; each scenario must retain a non-empty safe-positive arm and pass its paired physical-diversity guards. Scenario metrics are never pooled to hide a failed condition.
