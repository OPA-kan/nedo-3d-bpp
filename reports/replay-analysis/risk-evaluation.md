# Release risk: uncertainty and offline re-ranking evaluation

- rows: 1797 (release: 1180) in 33 snapshots
- All CIs are snapshot-clustered bootstrap (1000 iterations, percentile 2.5/97.5).
- Predictions are leave-one-snapshot-out: no row is scored by a model that saw its snapshot.

## Grouped-CV AUC with uncertainty

| label | LOSO AUC | 95% CI |
|---|---:|---|
| rotated_over_30 | 0.698 | [0.620, 0.767] |
| not_placed_safe | 0.709 | [0.634, 0.780] |

## Extrapolation splits

| label | split | direction | train n | test n | AUC |
|---|---|---|---:|---:|---:|
| rotated_over_30 | case | test_b000 | 504 | 676 | 0.534 |
| rotated_over_30 | case | test_b001 | 676 | 504 | 0.632 |
| rotated_over_30 | pool | test_k10 | 1106 | 74 | 0.985 |
| rotated_over_30 | pool | test_k15 | 950 | 230 | 0.683 |
| rotated_over_30 | pool | test_k20 | 724 | 456 | 0.604 |
| rotated_over_30 | pool | test_k30 | 933 | 247 | 0.739 |
| rotated_over_30 | pool | test_k40 | 1007 | 173 | 0.575 |
| not_placed_safe | case | test_b000 | 504 | 676 | 0.564 |
| not_placed_safe | case | test_b001 | 676 | 504 | 0.697 |
| not_placed_safe | pool | test_k10 | 1106 | 74 | 0.959 |
| not_placed_safe | pool | test_k15 | 950 | 230 | 0.787 |
| not_placed_safe | pool | test_k20 | 724 | 456 | 0.634 |
| not_placed_safe | pool | test_k30 | 933 | 247 | 0.745 |
| not_placed_safe | pool | test_k40 | 1007 | 173 | 0.584 |

## Danger rates with uncertainty (weighted)

| label | segment | n | raw+ | rate | 95% CI |
|---|---|---:|---:|---:|---|
| rotated_over_30 | all_release | 1180 | 283 | 0.309 | [0.238, 0.383] |
| rotated_over_30 | gate_pass | 464 | 71 | 0.108 | [0.047, 0.182] |
| rotated_over_30 | gate_reject | 716 | 212 | 0.426 | [0.351, 0.497] |
| rotated_over_30 | support_ratio_ge_0.6 | 386 | 34 | 0.065 | [0.026, 0.116] |
| not_placed_safe | all_release | 1180 | 326 | 0.386 | [0.303, 0.472] |
| not_placed_safe | gate_pass | 464 | 83 | 0.155 | [0.079, 0.234] |
| not_placed_safe | gate_reject | 716 | 243 | 0.519 | [0.428, 0.602] |
| not_placed_safe | support_ratio_ge_0.6 | 386 | 41 | 0.112 | [0.047, 0.198] |

`support_ratio_ge_0.6` is a low-risk *region estimate*, not a safety proof; its CI is the thing to read.

## Offline re-ranking sweep over release candidates (Q_old - lambda * P_rot)

| lambda | snapshots | selected rotated | selected unsafe | changed vs score-argmax | changed vs original release sel. | mean P_rot of selection | mean score loss | median | max |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 0.0 | 33 | 5 | 3 | 0 | 27/28 | 0.193 | 0.000 | 0.000 | 0.000 |
| 0.25 | 33 | 4 | 3 | 2 | 27/28 | 0.171 | 0.001 | 0.000 | 0.031 |
| 0.5 | 33 | 4 | 3 | 3 | 27/28 | 0.171 | 0.002 | 0.000 | 0.031 |
| 1.0 | 33 | 4 | 3 | 6 | 27/28 | 0.161 | 0.010 | 0.000 | 0.209 |
| 2.0 | 33 | 5 | 3 | 10 | 27/28 | 0.156 | 0.016 | 0.000 | 0.209 |
| 4.0 | 33 | 7 | 5 | 13 | 27/28 | 0.146 | 0.047 | 0.000 | 0.356 |
| 8.0 | 33 | 6 | 4 | 23 | 26/28 | 0.107 | 0.273 | 0.061 | 1.548 |

Restricted to sampled release candidates (the population the risk model scores); the live settled-preference and lookahead are not reproduced here. P_rot is the leave-one-snapshot-out prediction, so no selection is scored by a model that saw its snapshot.

## Counterfactual pairs on changed snapshots (primary)

- changed snapshots: 4 (labelled pairs: 4, unmatched: 0)
- rotation danger difference (baseline - shadow): 0 (baseline 1 vs shadow 1)
- placed-safe difference: 1 (not_placed_safe baseline 1 vs shadow 0)
- safe -> dangerous reversals: 0 (dangerous -> safe: 1)
- mean pair score loss: -0.190

## Horizontal displacement with item attributes

Rows with joined item attributes: 1180

| feature | Spearman vs d_xy |
|---|---:|
| support_ratio | -0.068 |
| com_margin | -0.086 |
| drop_normalized | -0.131 |
| abs_support_imbalance | 0.204 |
| abs_left_right_imbalance | 0.068 |
| abs_front_back_imbalance | 0.202 |
| mass | 0.042 |
| lateral_friction | -0.070 |
| restitution | 0.070 |
| is_soft | -0.066 |
| density | -0.027 |
| min_over_max_extent | 0.033 |

| model | binary LOSO AUC | 95% CI | continuous LOSO Spearman |
|---|---:|---|---:|
| phi_only | 0.704 | [0.626, 0.775] | 0.274 |
| phi_plus_item | 0.699 | [0.630, 0.762] | 0.289 |

