# Residual-state diversity condition matrix

- Scenarios: 4
- Core 1/2-container x shelf/no-shelf coverage: True
- Positive / negative-risk labels: 281 / 69
- Acceptance verdict: **fail**
- Failed scenarios: ['m-dual-empty']

| scenario | containers | shelves | steps | safe positive | negative risk | mean physical NN delta | verdict |
|---|---:|---:|---:|---:|---:|---:|---|
| m-dual-empty | 2 | 0 | 3 | 72 | 9 | 0.05339631569490443 | fail |
| m-dual-shelf-mixed | 2 | 1 | 3 | 73 | 8 | 0.0373544056466305 | pass |
| m-single-empty-noshelf | 1 | 0 | 3 | 85 | 28 | 0.025534800282052017 | pass |
| m-single-empty-shelf | 1 | 1 | 3 | 51 | 24 | 0.041504822503602046 | pass |

The 1/2-container x shelf/no-shelf cells must all be present; each scenario must retain a non-empty safe-positive arm and pass its paired physical-diversity guards. Scenario metrics are never pooled to hide a failed condition.
