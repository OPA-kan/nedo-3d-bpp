# Residual-state diversity condition matrix

- Scenarios: 8
- Core 1/2-container x shelf/no-shelf coverage: True
- Positive / negative-risk labels: 985 / 548
- Arm (observed swap rounds): 64
- Portfolio construction: `['paired_control_seed_then_observed_state_swap']`, swaps applied: 524
- Acceptance verdict: **pass** (pass)
- Completeness: complete
- Failed scenarios: []

| scenario | containers | shelves | steps | safe positive | negative risk | mean physical NN delta | verdict |
|---|---:|---:|---:|---:|---:|---:|---|
| m-dual-dedicated-priority | 2 | 0 | 6 | 112 | 63 | 0.07201008169503235 | pass |
| m-dual-empty | 2 | 0 | 6 | 137 | 43 | 0.07031221358831218 | pass |
| m-dual-full-stream | 2 | 1 | 5 | 139 | 35 | 0.07315120472948045 | pass |
| m-dual-preloaded-dedicated | 2 | 0 | 6 | 116 | 69 | 0.08550024321520215 | pass |
| m-dual-shelf-mixed | 2 | 1 | 6 | 167 | 55 | 0.0671697254344883 | pass |
| m-single-empty-noshelf | 1 | 0 | 6 | 131 | 136 | 0.06550079049027795 | pass |
| m-single-empty-shelf | 1 | 1 | 6 | 106 | 82 | 0.05831295570576428 | pass |
| m-single-preloaded | 1 | 0 | 5 | 77 | 65 | 0.0795588708390726 | pass |

The 1/2-container x shelf/no-shelf cells must all be present; each scenario must retain a non-empty safe-positive arm and pass its paired physical-diversity guards. Scenario metrics are never pooled to hide a failed condition.
