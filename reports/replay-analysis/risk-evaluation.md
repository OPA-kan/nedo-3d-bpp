# Release risk: uncertainty and offline re-ranking evaluation

- rows: 1291 (release: 849) in 24 snapshots
- All CIs are snapshot-clustered bootstrap (1000 iterations, percentile 2.5/97.5).
- Predictions are leave-one-snapshot-out: no row is scored by a model that saw its snapshot.

## Grouped-CV AUC with uncertainty

| label | LOSO AUC | 95% CI |
|---|---:|---|
| rotated_over_30 | 0.732 | [0.646, 0.807] |
| not_placed_safe | 0.721 | [0.626, 0.808] |

## Extrapolation splits

| label | split | direction | train n | test n | AUC |
|---|---|---|---:|---:|---:|
| rotated_over_30 | case | test_b000 | 346 | 503 | 0.676 |
| rotated_over_30 | case | test_b001 | 503 | 346 | 0.781 |
| rotated_over_30 | pool | test_k10 | 775 | 74 | 0.982 |
| rotated_over_30 | pool | test_k15 | 701 | 148 | 0.638 |
| rotated_over_30 | pool | test_k20 | 494 | 355 | 0.642 |
| rotated_over_30 | pool | test_k30 | 684 | 165 | 0.810 |
| rotated_over_30 | pool | test_k40 | 742 | 107 | 0.717 |
| not_placed_safe | case | test_b000 | 346 | 503 | 0.666 |
| not_placed_safe | case | test_b001 | 503 | 346 | 0.756 |
| not_placed_safe | pool | test_k10 | 775 | 74 | 0.956 |
| not_placed_safe | pool | test_k15 | 701 | 148 | 0.805 |
| not_placed_safe | pool | test_k20 | 494 | 355 | 0.639 |
| not_placed_safe | pool | test_k30 | 684 | 165 | 0.812 |
| not_placed_safe | pool | test_k40 | 742 | 107 | 0.692 |

## Danger rates with uncertainty (weighted)

| label | segment | n | raw+ | rate | 95% CI |
|---|---|---:|---:|---:|---|
| rotated_over_30 | all_release | 849 | 187 | 0.300 | [0.215, 0.393] |
| rotated_over_30 | gate_pass | 329 | 37 | 0.051 | [0.014, 0.109] |
| rotated_over_30 | gate_reject | 520 | 150 | 0.437 | [0.337, 0.528] |
| rotated_over_30 | support_ratio_ge_0.6 | 272 | 13 | 0.021 | [0.005, 0.053] |
| not_placed_safe | all_release | 849 | 213 | 0.375 | [0.284, 0.484] |
| not_placed_safe | gate_pass | 329 | 47 | 0.116 | [0.040, 0.238] |
| not_placed_safe | gate_reject | 520 | 166 | 0.517 | [0.412, 0.613] |
| not_placed_safe | support_ratio_ge_0.6 | 272 | 18 | 0.077 | [0.012, 0.192] |

`support_ratio_ge_0.6` is a low-risk *region estimate*, not a safety proof; its CI is the thing to read.

## Offline re-ranking sweep over release candidates (Q_old - lambda * P_rot)

| lambda | snapshots | selected rotated | selected unsafe | changed vs score-argmax | changed vs original release sel. | mean P_rot of selection | mean score loss | median | max |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 0.0 | 24 | 3 | 1 | 0 | 19/20 | 0.173 | 0.000 | 0.000 | 0.000 |
| 0.25 | 24 | 2 | 1 | 2 | 19/20 | 0.137 | 0.002 | 0.000 | 0.031 |
| 0.5 | 24 | 2 | 1 | 3 | 19/20 | 0.136 | 0.002 | 0.000 | 0.031 |
| 1.0 | 24 | 2 | 1 | 5 | 19/20 | 0.136 | 0.002 | 0.000 | 0.031 |
| 2.0 | 24 | 2 | 1 | 8 | 19/20 | 0.120 | 0.020 | 0.000 | 0.209 |
| 4.0 | 24 | 2 | 2 | 11 | 20/20 | 0.109 | 0.058 | 0.000 | 0.356 |
| 8.0 | 24 | 3 | 3 | 15 | 20/20 | 0.082 | 0.214 | 0.027 | 1.189 |

Restricted to sampled release candidates (the population the risk model scores); the live settled-preference and lookahead are not reproduced here. P_rot is the leave-one-snapshot-out prediction, so no selection is scored by a model that saw its snapshot.

## Counterfactual pairs on changed snapshots (primary)

- changed snapshots: 2 (labelled pairs: 2, unmatched: 0)
- rotation danger difference (baseline - shadow): 0 (baseline 0 vs shadow 0)
- placed-safe difference: 0 (not_placed_safe baseline 0 vs shadow 0)
- safe -> dangerous reversals: 0 (dangerous -> safe: 0)
- mean pair score loss: 0.006

## Horizontal displacement with item attributes

Rows with joined item attributes: 849

| feature | Spearman vs d_xy |
|---|---:|
| support_ratio | -0.097 |
| com_margin | -0.108 |
| drop_normalized | -0.149 |
| abs_support_imbalance | 0.243 |
| abs_left_right_imbalance | 0.087 |
| abs_front_back_imbalance | 0.220 |
| mass | 0.036 |
| lateral_friction | -0.094 |
| restitution | 0.094 |
| is_soft | -0.089 |
| density | -0.053 |
| min_over_max_extent | 0.054 |

| model | binary LOSO AUC | 95% CI | continuous LOSO Spearman |
|---|---:|---|---:|
| phi_only | 0.714 | [0.618, 0.803] | 0.309 |
| phi_plus_item | 0.707 | [0.618, 0.784] | 0.303 |

