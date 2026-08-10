# Learnability audit

- Verdict: **no_established_signal**
- Modelable rows: 1778 across 49 states and 8 cases
- Safe / unsafe: 1155 / 623 (a sampling design, not a natural rate)
- Excluded: {'no_phi_candidate': 537, 'duplicate_across_arms': 848}
- Contributing runs: `31391424126` (verdict fail, swap rounds 64), `31393167142` (verdict pass, swap rounds 64)
- Split: `leave_one_case_out`; not run: ['gbdt', 'deep_sets']

## is_placed_safe (ranking only; prevalence is designed)

| model | mean within-state AUC | pooled AUC | top-1 safe rate |
|---|---:|---:|---:|
| constant | 0.500 | 0.394 | 0.683 |
| incumbent | 0.745 | 0.709 | 0.872 |
| lookup | 0.671 | 0.650 | 0.780 |
| linear | 0.727 | 0.677 | 0.851 |

## settle regression (R^2 against a held-out constant)

| target | rows | lookup | linear |
|---|---:|---:|---:|
| delta_theta_deg | 1778 | 0.075 | 0.184 |
| d_norm | 1778 | 0.078 | 0.125 |

## folds

| held out | train rows | test rows | train states | test states | train safe rate |
|---|---:|---:|---:|---:|---:|
| m-dual-dedicated-priority | 1530 | 248 | 43 | 6 | 0.666 |
| m-dual-empty | 1590 | 188 | 43 | 6 | 0.635 |
| m-dual-full-stream | 1567 | 211 | 44 | 5 | 0.649 |
| m-dual-preloaded-dedicated | 1567 | 211 | 43 | 6 | 0.646 |
| m-dual-shelf-mixed | 1481 | 297 | 40 | 9 | 0.625 |
| m-single-empty-noshelf | 1522 | 256 | 43 | 6 | 0.666 |
| m-single-empty-shelf | 1596 | 182 | 43 | 6 | 0.651 |
| m-single-preloaded | 1593 | 185 | 44 | 5 | 0.659 |

## learning curve (training STATES, not rows)

| train states | folds | mean within-state AUC | R^2 delta_theta_deg | R^2 d_norm |
|---:|---:|---:|---:|---:|
| 4 | 40 | 0.664 | -1.678 | -0.762 |
| 8 | 40 | 0.697 | 0.134 | 0.055 |
| 12 | 40 | 0.701 | 0.146 | 0.060 |
| 16 | 40 | 0.700 | 0.152 | 0.082 |
| 24 | 40 | 0.719 | 0.169 | 0.094 |
| 32 | 40 | 0.715 | 0.172 | 0.103 |
| 40 | 40 | 0.720 | 0.180 | 0.111 |
| 45 | 0 | — | — | — |

Sampling is by state, not by row: rows inside a state are not independent, so a row-wise curve saturates early and reads as a ceiling that is not there. The curve describes doublings already taken, not the next one.

Mean within-state AUC is the headline. A model must beat the incumbent Ranker.score, not merely a constant, to be worth building on. With this few cases the fold spread is wide, so a small difference is not a result. GBDT and Deep Sets were not run -- only numpy is available -- so a null here bounds them weakly.
