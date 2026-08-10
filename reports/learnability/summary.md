# Learnability audit

- Verdict: **no_established_signal**
- Modelable rows: 325 across 11 states and 4 cases
- Safe / unsafe: 238 / 87 (a sampling design, not a natural rate)
- Excluded: {'no_phi_candidate': 117, 'duplicate_across_arms': 107}
- Contributing runs: `31391424126` (verdict fail, swap rounds 64)
- Split: `leave_one_case_out`; not run: ['gbdt', 'deep_sets']

## is_placed_safe (ranking only; prevalence is designed)

| model | mean within-state AUC | pooled AUC | top-1 safe rate |
|---|---:|---:|---:|
| constant | 0.500 | 0.369 | 0.744 |
| incumbent | 0.768 | 0.691 | 0.800 |
| lookup | 0.564 | 0.539 | 0.727 |
| linear | 0.741 | 0.685 | 0.900 |

## settle regression (R^2 against a held-out constant)

| target | rows | lookup | linear |
|---|---:|---:|---:|
| delta_theta_deg | 325 | -0.121 | 0.141 |
| d_norm | 325 | -0.082 | 0.075 |

## folds

| held out | train rows | test rows | train states | test states | train safe rate |
|---|---:|---:|---:|---:|---:|
| m-dual-empty | 248 | 77 | 8 | 3 | 0.714 |
| m-dual-shelf-mixed | 241 | 84 | 8 | 3 | 0.689 |
| m-single-empty-noshelf | 251 | 74 | 9 | 2 | 0.757 |
| m-single-empty-shelf | 235 | 90 | 8 | 3 | 0.770 |

Mean within-state AUC is the headline. A model must beat the incumbent Ranker.score, not merely a constant, to be worth building on. With this few cases the fold spread is wide, so a small difference is not a result. GBDT and Deep Sets were not run -- only numpy is available -- so a null here bounds them weakly.
