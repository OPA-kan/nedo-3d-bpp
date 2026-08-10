# Residual-state diversity condition matrix

- Scenarios: 7
- Core 1/2-container x shelf/no-shelf coverage: False
- Positive / negative-risk labels: 865 / 599
- Arm (observed swap rounds): 64
- Portfolio construction: `['paired_control_seed_then_observed_state_swap']`, swaps applied: 552
- Acceptance verdict: **fail** (incomplete_conditions)
- **The matrix is incomplete: a condition is missing, so this is not a guard result.** Re-run before citing it.
- Failed scenarios: []

| scenario | containers | shelves | steps | safe positive | negative risk | mean physical NN delta | verdict |
|---|---:|---:|---:|---:|---:|---:|---|
| m-dual-dedicated-priority | 2 | 0 | 6 | 125 | 119 | 0.06645373722843843 | pass |
| m-dual-empty | 2 | 0 | 6 | 142 | 56 | 0.07269029262926342 | pass |
| m-dual-full-stream | 2 | 1 | 5 | 149 | 54 | 0.062209116989120274 | pass |
| m-dual-preloaded-dedicated | 2 | 0 | 6 | 99 | 60 | 0.08888446639950427 | pass |
| m-dual-shelf-mixed | 2 | 1 | 6 | 165 | 66 | 0.06611056700546374 | pass |
| m-single-empty-noshelf | 1 | 0 | 6 | 136 | 193 | 0.085169656809178 | pass |
| m-single-preloaded | 1 | 0 | 4 | 49 | 51 | 0.07662523262747137 | pass |

The 1/2-container x shelf/no-shelf cells must all be present; each scenario must retain a non-empty safe-positive arm and pass its paired physical-diversity guards. Scenario metrics are never pooled to hide a failed condition.
