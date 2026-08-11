# Residual-state diversity condition matrix

- Scenarios: 8
- Core 1/2-container x shelf/no-shelf coverage: True
- Positive / negative-risk labels: 1006 / 586
- Arm (observed swap rounds): 64
- Portfolio construction: `['paired_control_seed_then_observed_state_swap']`, swaps applied: 644
- Acceptance verdict: **pass** (pass)
- Completeness: complete
- Failed scenarios: []

| scenario | containers | shelves | steps | safe positive | negative risk | mean physical NN delta | verdict |
|---|---:|---:|---:|---:|---:|---:|---|
| m-dual-dedicated-priority | 2 | 0 | 6 | 112 | 79 | 0.0604241831295829 | pass |
| m-dual-empty | 2 | 0 | 6 | 137 | 43 | 0.07770535350637428 | pass |
| m-dual-full-stream | 2 | 1 | 5 | 139 | 35 | 0.080146545956537 | pass |
| m-dual-preloaded-dedicated | 2 | 0 | 6 | 148 | 117 | 0.07370050735670948 | pass |
| m-dual-shelf-mixed | 2 | 1 | 6 | 167 | 35 | 0.07728178445890534 | pass |
| m-single-empty-noshelf | 1 | 0 | 6 | 131 | 140 | 0.06906684879558685 | pass |
| m-single-empty-shelf | 1 | 1 | 6 | 106 | 82 | 0.06038324850333047 | pass |
| m-single-preloaded | 1 | 0 | 4 | 66 | 55 | 0.09294596867573027 | pass |

The 1/2-container x shelf/no-shelf cells must all be present; each scenario must retain a non-empty safe-positive arm and pass its paired physical-diversity guards. Scenario metrics are never pooled to hide a failed condition.
