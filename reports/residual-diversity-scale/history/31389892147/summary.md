# Residual-state diversity condition matrix

- Scenarios: 4
- Core 1/2-container x shelf/no-shelf coverage: True
- Positive / negative-risk labels: 286 / 111
- Acceptance verdict: **pass**
- Failed scenarios: []

| scenario | containers | shelves | steps | safe positive | negative risk | mean physical NN delta | verdict |
|---|---:|---:|---:|---:|---:|---:|---|
| m-dual-empty | 2 | 0 | 3 | 56 | 16 | 0.059554000212093394 | pass |
| m-dual-shelf-mixed | 2 | 1 | 3 | 94 | 24 | 0.0227817794889502 | pass |
| m-single-empty-noshelf | 1 | 0 | 3 | 85 | 38 | 0.024663468033026843 | pass |
| m-single-empty-shelf | 1 | 1 | 3 | 51 | 33 | 0.03107001542260632 | pass |

The 1/2-container x shelf/no-shelf cells must all be present; each scenario must retain a non-empty safe-positive arm and pass its paired physical-diversity guards. Scenario metrics are never pooled to hide a failed condition.
