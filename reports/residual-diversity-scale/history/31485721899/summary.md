# Residual-state diversity condition matrix

- Scenarios: 8
- Core 1/2-container x shelf/no-shelf coverage: True
- Positive / negative-risk labels: 1002 / 561
- Arm (observed swap rounds): 64
- Portfolio construction: `['paired_control_seed_then_observed_state_swap']`, swaps applied: 617
- Acceptance verdict: **pass** (pass)
- Completeness: complete
- Failed scenarios: []

| scenario | containers | shelves | steps | safe positive | negative risk | mean physical NN delta | verdict |
|---|---:|---:|---:|---:|---:|---:|---|
| m-dual-dedicated-priority | 2 | 0 | 6 | 112 | 79 | 0.06154073613310515 | pass |
| m-dual-empty | 2 | 0 | 6 | 137 | 43 | 0.07872662004612511 | pass |
| m-dual-full-stream | 2 | 1 | 6 | 169 | 56 | 0.07497242302466198 | pass |
| m-dual-preloaded-dedicated | 2 | 0 | 6 | 148 | 79 | 0.07365703592034335 | pass |
| m-dual-shelf-mixed | 2 | 1 | 6 | 167 | 55 | 0.06392982680152347 | pass |
| m-single-empty-noshelf | 1 | 0 | 6 | 114 | 128 | 0.0697799772626168 | pass |
| m-single-empty-shelf | 1 | 1 | 6 | 89 | 66 | 0.08557696885392567 | pass |
| m-single-preloaded | 1 | 0 | 4 | 66 | 55 | 0.09294596867573027 | pass |

The 1/2-container x shelf/no-shelf cells must all be present; each scenario must retain a non-empty safe-positive arm and pass its paired physical-diversity guards. Scenario metrics are never pooled to hide a failed condition.
