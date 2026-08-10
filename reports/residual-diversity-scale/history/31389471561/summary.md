# Residual-state diversity condition matrix

- Scenarios: 4
- Core 1/2-container x shelf/no-shelf coverage: True
- Positive / negative-risk labels: 244 / 106
- Acceptance verdict: **pass**
- Failed scenarios: []

| scenario | containers | shelves | steps | safe positive | negative risk | mean physical NN delta | verdict |
|---|---:|---:|---:|---:|---:|---:|---|
| m-dual-empty | 2 | 0 | 3 | 56 | 16 | 0.0833479931139688 | pass |
| m-dual-shelf-mixed | 2 | 1 | 3 | 73 | 12 | 0.0846488690997614 | pass |
| m-single-empty-noshelf | 1 | 0 | 3 | 64 | 46 | 0.06192852691796898 | pass |
| m-single-empty-shelf | 1 | 1 | 3 | 51 | 32 | 0.08149432705352078 | pass |

The 1/2-container x shelf/no-shelf cells must all be present; each scenario must retain a non-empty safe-positive arm and pass its paired physical-diversity guards. Scenario metrics are never pooled to hide a failed condition.
