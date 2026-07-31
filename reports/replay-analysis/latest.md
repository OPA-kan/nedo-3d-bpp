# Replay dataset Phi -> Y analysis

- rows: 679
- `20260730_161245-b000-k20-weighted-class_aware-shadow-0fb74669-c5ec4f65c4ca`: 83 rows
- `20260730_161846-b000-k20-weighted-class_aware-shadow-0fb74669-616c41f58ac4`: 50 rows
- `20260730_162936-b000-k40-weighted-class_aware-shadow-c1adf14c-80ff7f22fde9`: 66 rows
- `20260730_163302-b000-k40-weighted-class_aware-shadow-c1adf14c-79e9cd048e2a`: 91 rows
- `20260730_164227-b001-k20-weighted-class_aware-shadow-2e6de0af-24e614269991`: 124 rows
- `20260730_165446-b001-k20-weighted-class_aware-shadow-2e6de0af-6fef617f0a69`: 66 rows
- `20260730_170531-b001-k40-weighted-class_aware-shadow-60c01a1e-4236de070210`: 133 rows
- `20260730_171526-b001-k40-weighted-class_aware-shadow-60c01a1e-7c6b10e81430`: 66 rows

## Label prevalence (per kind)

| kind | n | rotated_over_30 | horizontal_displaced_over_half_footprint | displaced_over_half_footprint | not_placed_safe | not_valid |
|---|---:|---:|---:|---:|---:|---:|
| release_candidate | 462 | 0.221 / 0.258 | 0.143 / 0.195 | 0.260 / 0.361 | 0.210 / 0.296 | 0.000 / 0.000 |
| candidate | 217 | 0.051 / 0.027 | 0.032 / 0.061 | 0.069 / 0.106 | 0.065 / 0.041 | 0.000 / 0.000 |

Cells are `raw rate / weighted rate`.

## Gate verdict split (release candidates)

| verdict | n | rotated_over_30 | horizontal_displaced_over_half_footprint | displaced_over_half_footprint | not_placed_safe | not_valid |
|---|---:|---:|---:|---:|---:|---:|
| pass | 156 | 0.032 / 0.020 | 0.019 / 0.052 | 0.096 / 0.157 | 0.064 / 0.061 | 0.000 / 0.000 |
| reject | 306 | 0.317 / 0.387 | 0.206 / 0.273 | 0.343 / 0.471 | 0.284 / 0.422 | 0.000 / 0.000 |

## Current gate confusion (positive = dangerous)

| label | TP | FP | FN | TN | reject precision | reject recall | danger rate among passed |
|---|---:|---:|---:|---:|---:|---:|---:|
| rotated_over_30 | 97 | 209 | 5 | 151 | 0.387 | 0.973 | 0.020 |
| horizontal_displaced_over_half_footprint | 63 | 243 | 3 | 153 | 0.273 | 0.907 | 0.052 |
| displaced_over_half_footprint | 105 | 201 | 15 | 141 | 0.471 | 0.847 | 0.157 |
| not_placed_safe | 87 | 219 | 10 | 146 | 0.422 | 0.928 | 0.061 |
| not_valid | 0 | 306 | 0 | 156 | 0.000 | - | 0.000 |

Counts are raw rows; precision/recall/danger-rate are weighted.

## Univariate Phi -> Y (release candidates)

| feature | n | rho(dtheta) | rho(d_xy) | rho(d_z) | Q1..Q4 rate not_placed_safe | Q1..Q4 mean dtheta |
|---|---:|---:|---:|---:|---|---|
| support_ratio | 462 | -0.243 | -0.182 | -0.321 | 0.267 / 0.143 / 0.296 / 0.026 | 24.3 / 26.6 / 25.7 / 2.6 |
| com_margin | 462 | -0.257 | -0.174 | -0.340 | 0.257 / - / 0.248 / 0.078 | 24.4 / - / 23.8 / 4.5 |
| overhang_ratio | 462 | 0.243 | 0.182 | 0.321 | 0.026 / 0.296 / 0.260 / - | 2.6 / 25.7 / 24.5 / - |
| drop_normalized | 462 | 0.010 | -0.016 | 0.040 | 0.316 / 0.073 / 0.197 / 0.128 | 26.2 / 12.1 / 17.8 / 13.1 |
| support_imbalance | 462 | 0.138 | 0.102 | 0.012 | 0.263 / 0.000 / 0.071 / 0.259 | 23.6 / 1.1 / 4.6 / 26.6 |
| left_right_imbalance | 462 | -0.033 | 0.017 | -0.044 | 0.241 / - / - / 0.071 | 21.0 / - / - / 11.7 |
| front_back_imbalance | 462 | -0.047 | 0.011 | -0.057 | 0.222 / - / 0.000 / 0.181 | 20.2 / - / 3.1 / 17.0 |

## Within-snapshot contrast (safe minus dangerous)

Snapshots containing both safe and dangerous release rows: 13

| feature | snapshots | mean diff | safe-higher count |
|---|---:|---:|---:|
| support_ratio | 13 | 0.165 | 8 |
| com_margin | 13 | 0.357 | 8 |
| overhang_ratio | 13 | -0.165 | 2 |
| drop_normalized | 13 | 0.012 | 8 |
| support_imbalance | 13 | -0.131 | 3 |
| left_right_imbalance | 13 | 0.128 | 10 |
| front_back_imbalance | 13 | -0.070 | 3 |

## Gate reject reasons (release candidates)

| reason | rejected dangerous (TP) | rejected safe (FP) |
|---|---:|---:|
| com_margin | 82 | 206 |
| overhang | 72 | 186 |
| support | 72 | 186 |
| support_imbalance | 29 | 60 |

Dangerous/safe by `not_placed_safe`; a candidate can carry several reasons.

## Single-feature AUC (higher score = claimed dangerous)

| feature | not_placed_safe | rotated_over_30 | horizontal_displaced_over_half_footprint |
|---|---:|---:|---:|
| support_ratio | 0.643 | 0.632 | 0.679 |
| com_margin | 0.630 | 0.635 | 0.670 |
| overhang_ratio | 0.643 | 0.632 | 0.679 |
| drop_normalized | 0.409 | 0.464 | 0.394 |
| abs_support_imbalance | 0.478 | 0.557 | 0.388 |
| abs_left_right_imbalance | 0.466 | 0.537 | 0.383 |
| abs_front_back_imbalance | 0.509 | 0.559 | 0.416 |

## Hard-accept sweep on support_ratio (release candidates)

| min support_ratio | n | weighted share accepted | not_placed_safe raw/weighted | rotated_over_30 raw/weighted |
|---:|---:|---:|---:|---:|
| 0.5 | 149 | 0.342 | 0.060 / 0.047 | 0.027 / 0.005 |
| 0.6 | 131 | 0.327 | 0.031 / 0.028 | 0.023 / 0.004 |
| 0.7 | 92 | 0.249 | 0.011 / 0.031 | 0.000 / 0.000 |
| 0.8 | 83 | 0.218 | 0.012 / 0.035 | 0.000 / 0.000 |
| 0.9 | 53 | 0.159 | 0.019 / 0.048 | 0.000 / 0.000 |
| 0.95 | 46 | 0.133 | 0.022 / 0.057 | 0.000 / 0.000 |

## Logistic separability probe (snapshot-held-out)

Train n=322, test n=140; features: intercept, support_ratio, com_margin, drop_normalized, abs_support_imbalance, abs_left_right_imbalance, abs_front_back_imbalance

| label | test AUC | best single-feature test AUC | weights |
|---|---:|---:|---|
| not_placed_safe | 0.656 | 0.696 | [0.753, -5.142, 1.365, -3.206, -0.892, 0.832, 2.087] |
| rotated_over_30 | 0.776 | 0.624 | [-0.184, -4.47, 0.661, -2.649, 0.807, 0.551, 0.525] |

## Danger rate by score band (raw)

### release_candidate

| band | n | not_placed_safe | rotated_over_30 | not_valid |
|---|---:|---:|---:|---:|
| top1 | 13 | 0.077 | 0.231 | 0.000 |
| top10 | 105 | 0.143 | 0.200 | 0.000 |
| top10pct | 168 | 0.190 | 0.202 | 0.000 |
| tail | 176 | 0.278 | 0.250 | 0.000 |

### candidate

| band | n | not_placed_safe | rotated_over_30 | not_valid |
|---|---:|---:|---:|---:|
| top1 | 9 | 0.111 | 0.111 | 0.000 |
| top10 | 72 | 0.111 | 0.111 | 0.000 |
| top10pct | 64 | 0.031 | 0.000 | 0.000 |
| tail | 72 | 0.042 | 0.028 | 0.000 |

