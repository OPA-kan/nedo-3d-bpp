# Residual-state diversity condition matrix

- Scenarios: 8
- Core 1/2-container x shelf/no-shelf coverage: True
- Positive / negative-risk labels: 816 / 540
- Arm (observed swap rounds): 64
- Portfolio construction: `['paired_control_seed_then_observed_state_swap']`, swaps applied: 510
- Acceptance verdict: **pass** (pass)
- Completeness: complete
- Failed scenarios: []

| scenario | containers | shelves | steps | safe positive | negative risk | mean physical NN delta | verdict |
|---|---:|---:|---:|---:|---:|---:|---|
| m-dual-dedicated-priority | 2 | 0 | 5 | 86 | 61 | 0.08171195235696657 | pass |
| m-dual-empty | 2 | 0 | 6 | 141 | 57 | 0.0746202847509397 | pass |
| m-dual-full-stream | 2 | 1 | 4 | 109 | 35 | 0.07724616864403042 | pass |
| m-dual-preloaded-dedicated | 2 | 0 | 6 | 127 | 80 | 0.07438259279766785 | pass |
| m-dual-shelf-mixed | 2 | 1 | 6 | 142 | 49 | 0.080519730896685 | pass |
| m-single-empty-noshelf | 1 | 0 | 5 | 101 | 140 | 0.07569405400612272 | pass |
| m-single-empty-shelf | 1 | 1 | 5 | 76 | 77 | 0.06394764534491845 | pass |
| m-single-preloaded | 1 | 0 | 3 | 34 | 41 | 0.10690371475426404 | pass |

The 1/2-container x shelf/no-shelf cells must all be present; each scenario must retain a non-empty safe-positive arm and pass its paired physical-diversity guards. Scenario metrics are never pooled to hide a failed condition.
