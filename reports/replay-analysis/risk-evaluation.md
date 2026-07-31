# Release risk: uncertainty and offline re-ranking evaluation

- rows: 480 (release: 338) in 10 snapshots
- All CIs are snapshot-clustered bootstrap (1000 iterations, percentile 2.5/97.5).
- Predictions are leave-one-snapshot-out: no row is scored by a model that saw its snapshot.

## Grouped-CV AUC with uncertainty

| label | LOSO AUC | 95% CI |
|---|---:|---|
| rotated_over_30 | 0.699 | [0.563, 0.825] |
| not_placed_safe | 0.587 | [0.453, 0.761] |

## Extrapolation splits

| label | split | direction | train n | test n | AUC |
|---|---|---|---:|---:|---:|
| rotated_over_30 | case | train_b000 | 223 | 115 | 0.843 |
| rotated_over_30 | case | train_b001 | 115 | 223 | 0.697 |
| rotated_over_30 | pool | train_k20 | 231 | 107 | 0.714 |
| rotated_over_30 | pool | train_k40 | 107 | 231 | 0.684 |
| not_placed_safe | case | train_b000 | 223 | 115 | 0.775 |
| not_placed_safe | case | train_b001 | 115 | 223 | 0.608 |
| not_placed_safe | pool | train_k20 | 231 | 107 | 0.628 |
| not_placed_safe | pool | train_k40 | 107 | 231 | 0.659 |

## Danger rates with uncertainty (weighted)

| label | segment | n | raw+ | rate | 95% CI |
|---|---|---:|---:|---:|---|
| rotated_over_30 | all_release | 338 | 83 | 0.312 | [0.180, 0.449] |
| rotated_over_30 | gate_pass | 106 | 5 | 0.031 | [0.000, 0.114] |
| rotated_over_30 | gate_reject | 232 | 78 | 0.433 | [0.310, 0.543] |
| rotated_over_30 | support_ratio_ge_0.6 | 86 | 3 | 0.007 | [0.000, 0.032] |
| not_placed_safe | all_release | 338 | 89 | 0.362 | [0.198, 0.541] |
| not_placed_safe | gate_pass | 106 | 9 | 0.060 | [0.000, 0.221] |
| not_placed_safe | gate_reject | 232 | 80 | 0.493 | [0.351, 0.626] |
| not_placed_safe | support_ratio_ge_0.6 | 86 | 3 | 0.007 | [0.000, 0.032] |

`support_ratio_ge_0.6` is a low-risk *region estimate*, not a safety proof; its CI is the thing to read.

## Offline re-ranking sweep over release candidates (Q_old - lambda * P_rot)

| lambda | snapshots | selected rotated | selected unsafe | changed vs score-argmax | changed vs original release sel. | mean P_rot of selection | mean score loss | median | max |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 0.0 | 10 | 2 | 1 | 0 | 9/10 | 0.269 | 0.000 | 0.000 | 0.000 |
| 0.25 | 10 | 1 | 1 | 1 | 10/10 | 0.189 | 0.006 | 0.000 | 0.064 |
| 0.5 | 10 | 1 | 1 | 2 | 10/10 | 0.189 | 0.006 | 0.000 | 0.064 |
| 1.0 | 10 | 1 | 1 | 3 | 10/10 | 0.167 | 0.018 | 0.000 | 0.117 |
| 2.0 | 10 | 2 | 2 | 4 | 10/10 | 0.146 | 0.045 | 0.000 | 0.265 |
| 4.0 | 10 | 1 | 1 | 6 | 10/10 | 0.121 | 0.131 | 0.062 | 0.587 |
| 8.0 | 10 | 1 | 1 | 6 | 10/10 | 0.110 | 0.202 | 0.131 | 0.692 |

Restricted to sampled release candidates (the population the risk model scores); the live settled-preference and lookahead are not reproduced here. P_rot is the leave-one-snapshot-out prediction, so no selection is scored by a model that saw its snapshot.

## Counterfactual pairs on changed snapshots (primary)

- changed snapshots: 0 (labelled pairs: 0, unmatched: 0)
- rotation danger difference (baseline - shadow): 0 (baseline 0 vs shadow 0)
- placed-safe difference: 0 (not_placed_safe baseline 0 vs shadow 0)
- safe -> dangerous reversals: 0 (dangerous -> safe: 0)
- mean pair score loss: -

## Horizontal displacement with item attributes

Rows with joined item attributes: 338

| feature | Spearman vs d_xy |
|---|---:|
| support_ratio | -0.177 |
| com_margin | -0.162 |
| drop_normalized | -0.012 |
| abs_support_imbalance | 0.042 |
| abs_left_right_imbalance | 0.022 |
| abs_front_back_imbalance | 0.051 |
| mass | -0.066 |
| lateral_friction | -0.216 |
| restitution | 0.216 |
| is_soft | -0.216 |
| density | -0.204 |
| min_over_max_extent | 0.214 |

| model | binary LOSO AUC | 95% CI | continuous LOSO Spearman |
|---|---:|---|---:|
| phi_only | 0.585 | [0.488, 0.713] | 0.069 |
| phi_plus_item | 0.707 | [0.618, 0.809] | 0.216 |

