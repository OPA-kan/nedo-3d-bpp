# Residual-state diversity condition matrix

- Scenarios: 8
- Core 1/2-container x shelf/no-shelf coverage: True
- Positive / negative-risk labels: 954 / 597
- Arm (observed swap rounds): 64
- Portfolio construction: `['paired_control_seed_then_observed_state_swap']`, swaps applied: 582
- Acceptance verdict: **pass** (pass)
- Completeness: complete
- Failed scenarios: []

| scenario | containers | shelves | steps | safe positive | negative risk | mean physical NN delta | verdict |
|---|---:|---:|---:|---:|---:|---:|---|
| m-dual-dedicated-priority | 2 | 0 | 6 | 112 | 79 | 0.0604241831295829 | pass |
| m-dual-empty | 2 | 0 | 6 | 137 | 43 | 0.07770535350637428 | pass |
| m-dual-full-stream | 2 | 1 | 5 | 139 | 103 | 0.08061604711919654 | pass |
| m-dual-preloaded-dedicated | 2 | 0 | 5 | 117 | 63 | 0.08013232601689899 | pass |
| m-dual-shelf-mixed | 2 | 1 | 6 | 163 | 44 | 0.07286523159404147 | pass |
| m-single-empty-noshelf | 1 | 0 | 6 | 114 | 128 | 0.0697799772626168 | pass |
| m-single-empty-shelf | 1 | 1 | 6 | 106 | 82 | 0.06038324850333047 | pass |
| m-single-preloaded | 1 | 0 | 4 | 66 | 55 | 0.09294596867573027 | pass |

The 1/2-container x shelf/no-shelf cells must all be present; each scenario must retain a non-empty safe-positive arm and pass its paired physical-diversity guards. Scenario metrics are never pooled to hide a failed condition.
