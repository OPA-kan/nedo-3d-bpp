# Learnability audit

- Verdict: **no_established_signal**
- Modelable rows: 3482 across 93 states and 8 cases
- Safe / unsafe: 2213 / 1269 (a sampling design, not a natural rate)
- Excluded: {'no_phi_candidate': 999, 'duplicate_across_arms': 1269}
- Contributing runs: `31391424126` (verdict fail, swap rounds 64), `31393167142` (verdict pass, swap rounds 64), `31394891316` (verdict fail, swap rounds 64)
- Split: `leave_one_case_out`; not run: ['gbdt', 'deep_sets']

## is_placed_safe (ranking only; prevalence is designed)

| model | mean within-state AUC | pooled AUC | top-1 safe rate |
|---|---:|---:|---:|
| constant | 0.500 | 0.388 | 0.666 |
| incumbent | 0.725 | 0.705 | 0.867 |
| lookup | 0.676 | 0.648 | 0.825 |
| linear | 0.709 | 0.678 | 0.868 |

## settle regression (R^2 against a held-out constant)

| target | rows | lookup | linear |
|---|---:|---:|---:|
| delta_theta_deg | 3482 | 0.060 | 0.147 |
| d_norm | 3482 | 0.071 | 0.081 |

## folds

| held out | train rows | test rows | train states | test states | train safe rate |
|---|---:|---:|---:|---:|---:|
| m-dual-dedicated-priority | 2988 | 494 | 81 | 12 | 0.648 |
| m-dual-empty | 3083 | 399 | 81 | 12 | 0.620 |
| m-dual-full-stream | 3062 | 420 | 83 | 10 | 0.627 |
| m-dual-preloaded-dedicated | 3073 | 409 | 81 | 12 | 0.629 |
| m-dual-shelf-mixed | 2964 | 518 | 78 | 15 | 0.617 |
| m-single-empty-noshelf | 2921 | 561 | 81 | 12 | 0.663 |
| m-single-empty-shelf | 3109 | 373 | 82 | 11 | 0.639 |
| m-single-preloaded | 3174 | 308 | 84 | 9 | 0.641 |

## learning curve (training STATES, not rows)

| train states | folds | mean within-state AUC | R^2 delta_theta_deg | R^2 d_norm |
|---:|---:|---:|---:|---:|
| 4 | 40 | 0.666 | -0.008 | -0.124 |
| 8 | 40 | 0.697 | 0.055 | -0.009 |
| 16 | 40 | 0.710 | 0.153 | 0.075 |
| 32 | 40 | 0.708 | 0.148 | 0.074 |
| 64 | 40 | 0.711 | 0.166 | 0.093 |
| 78 | 40 | 0.711 | 0.164 | 0.091 |

Sampling is by state, not by row: rows inside a state are not independent, so a row-wise curve saturates early and reads as a ceiling that is not there. The curve describes doublings already taken, not the next one.

Mean within-state AUC is the headline. A model must beat the incumbent Ranker.score, not merely a constant, to be worth building on. With this few cases the fold spread is wide, so a small difference is not a result. GBDT and Deep Sets were not run -- only numpy is available -- so a null here bounds them weakly.
