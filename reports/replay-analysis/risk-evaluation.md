# Release risk: uncertainty and offline re-ranking evaluation

- rows: 679 (release: 462) in 13 snapshots
- All CIs are snapshot-clustered bootstrap (1000 iterations, percentile 2.5/97.5).
- Predictions are leave-one-snapshot-out: no row is scored by a model that saw its snapshot.

## Grouped-CV AUC with uncertainty

| label | LOSO AUC | 95% CI |
|---|---:|---|
| rotated_over_30 | 0.699 | [0.581, 0.804] |
| not_placed_safe | 0.620 | [0.519, 0.751] |

## Extrapolation splits

| label | split | direction | train n | test n | AUC |
|---|---|---|---:|---:|---:|
| rotated_over_30 | case | train_b000 | 223 | 239 | 0.784 |
| rotated_over_30 | case | train_b001 | 239 | 223 | 0.676 |
| rotated_over_30 | pool | train_k20 | 231 | 231 | 0.745 |
| rotated_over_30 | pool | train_k40 | 231 | 231 | 0.646 |
| not_placed_safe | case | train_b000 | 223 | 239 | 0.731 |
| not_placed_safe | case | train_b001 | 239 | 223 | 0.588 |
| not_placed_safe | pool | train_k20 | 231 | 231 | 0.671 |
| not_placed_safe | pool | train_k40 | 231 | 231 | 0.666 |

## Danger rates with uncertainty (weighted)

| label | segment | n | raw+ | rate | 95% CI |
|---|---|---:|---:|---:|---|
| rotated_over_30 | all_release | 462 | 102 | 0.258 | [0.147, 0.382] |
| rotated_over_30 | gate_pass | 156 | 5 | 0.020 | [0.000, 0.066] |
| rotated_over_30 | gate_reject | 306 | 97 | 0.387 | [0.265, 0.493] |
| rotated_over_30 | support_ratio_ge_0.6 | 131 | 3 | 0.004 | [0.000, 0.016] |
| not_placed_safe | all_release | 462 | 97 | 0.296 | [0.164, 0.444] |
| not_placed_safe | gate_pass | 156 | 10 | 0.061 | [0.000, 0.154] |
| not_placed_safe | gate_reject | 306 | 87 | 0.422 | [0.275, 0.562] |
| not_placed_safe | support_ratio_ge_0.6 | 131 | 4 | 0.028 | [0.000, 0.077] |

`support_ratio_ge_0.6` is a low-risk *region estimate*, not a safety proof; its CI is the thing to read.

## Offline re-ranking sweep over release candidates (Q_old - lambda * P_rot)

| lambda | snapshots | selected rotated | selected unsafe | changed vs score-argmax | changed vs original release sel. | mean P_rot of selection | mean score loss | median | max |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 0.0 | 13 | 3 | 1 | 0 | 12/13 | 0.231 | 0.000 | 0.000 | 0.000 |
| 0.25 | 13 | 2 | 1 | 2 | 12/13 | 0.186 | 0.004 | 0.000 | 0.031 |
| 0.5 | 13 | 1 | 1 | 3 | 13/13 | 0.158 | 0.015 | 0.000 | 0.096 |
| 1.0 | 13 | 1 | 1 | 4 | 13/13 | 0.142 | 0.024 | 0.000 | 0.117 |
| 2.0 | 13 | 2 | 2 | 6 | 13/13 | 0.126 | 0.046 | 0.000 | 0.265 |
| 4.0 | 13 | 1 | 1 | 8 | 13/13 | 0.093 | 0.143 | 0.031 | 0.665 |
| 8.0 | 13 | 1 | 1 | 9 | 13/13 | 0.078 | 0.230 | 0.192 | 0.692 |

Restricted to sampled release candidates (the population the risk model scores); the live settled-preference and lookahead are not reproduced here. P_rot is the leave-one-snapshot-out prediction, so no selection is scored by a model that saw its snapshot.

## Horizontal displacement with item attributes

Rows with joined item attributes: 462

| feature | Spearman vs d_xy |
|---|---:|
| support_ratio | -0.182 |
| com_margin | -0.174 |
| drop_normalized | -0.016 |
| abs_support_imbalance | 0.102 |
| abs_left_right_imbalance | 0.078 |
| abs_front_back_imbalance | 0.062 |
| mass | -0.057 |
| lateral_friction | -0.181 |
| restitution | 0.181 |
| is_soft | -0.181 |
| density | -0.165 |
| min_over_max_extent | 0.174 |

| model | binary LOSO AUC | 95% CI | continuous LOSO Spearman |
|---|---:|---|---:|
| phi_only | 0.614 | [0.528, 0.716] | 0.076 |
| phi_plus_item | 0.693 | [0.602, 0.770] | 0.176 |

