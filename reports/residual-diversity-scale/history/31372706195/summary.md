# Residual-state diversity condition matrix

- Scenarios: 4
- Core 1/2-container x shelf/no-shelf coverage: True
- Positive / negative-risk labels: 282 / 108
- Acceptance verdict: **fail**
- Failed scenarios: ['m-dual-shelf-mixed', 'm-single-empty-shelf']

| scenario | containers | shelves | steps | safe positive | negative risk | mean physical NN delta | verdict |
|---|---:|---:|---:|---:|---:|---:|---|
| m-dual-empty | 2 | 0 | 3 | 73 | 26 | 0.031232188332598897 | pass |
| m-dual-shelf-mixed | 2 | 1 | 3 | 73 | 12 | 0.03622342139351132 | fail |
| m-single-empty-noshelf | 1 | 0 | 3 | 85 | 38 | 0.023906004915654516 | pass |
| m-single-empty-shelf | 1 | 1 | 3 | 51 | 32 | 0.02856498218760718 | fail |

The 1/2-container x shelf/no-shelf cells must all be present; each scenario must retain a non-empty safe-positive arm and pass its paired physical-diversity guards. Scenario metrics are never pooled to hide a failed condition.
