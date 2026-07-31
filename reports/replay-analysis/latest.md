# Replay dataset Phi -> Y analysis

- rows: 480
- `20260730_161245-b000-k20-weighted-class_aware-shadow-0fb74669-c5ec4f65c4ca`: 83 rows
- `20260730_161846-b000-k20-weighted-class_aware-shadow-0fb74669-616c41f58ac4`: 50 rows
- `20260730_162936-b000-k40-weighted-class_aware-shadow-c1adf14c-80ff7f22fde9`: 66 rows
- `20260730_163302-b000-k40-weighted-class_aware-shadow-c1adf14c-79e9cd048e2a`: 91 rows
- `20260730_164227-b001-k20-weighted-class_aware-shadow-2e6de0af-24e614269991`: 124 rows
- `20260730_165446-b001-k20-weighted-class_aware-shadow-2e6de0af-6fef617f0a69`: 66 rows

## Label prevalence (per kind)

| kind | n | rotated_over_30 | horizontal_displaced_over_half_footprint | displaced_over_half_footprint | not_placed_safe | not_valid |
|---|---:|---:|---:|---:|---:|---:|
| release_candidate | 338 | 0.246 / 0.312 | 0.178 / 0.242 | 0.320 / 0.429 | 0.263 / 0.362 | 0.000 / 0.000 |
| candidate | 142 | 0.070 / 0.017 | 0.028 / 0.019 | 0.070 / 0.060 | 0.092 / 0.038 | 0.000 / 0.000 |

Cells are `raw rate / weighted rate`.

## Gate verdict split (release candidates)

| verdict | n | rotated_over_30 | horizontal_displaced_over_half_footprint | displaced_over_half_footprint | not_placed_safe | not_valid |
|---|---:|---:|---:|---:|---:|---:|
| pass | 106 | 0.047 / 0.031 | 0.019 / 0.046 | 0.113 / 0.149 | 0.085 / 0.060 | 0.000 / 0.000 |
| reject | 232 | 0.336 / 0.433 | 0.250 / 0.326 | 0.414 / 0.550 | 0.345 / 0.493 | 0.000 / 0.000 |

## Current gate confusion (positive = dangerous)

| label | TP | FP | FN | TN | reject precision | reject recall | danger rate among passed |
|---|---:|---:|---:|---:|---:|---:|---:|
| rotated_over_30 | 78 | 154 | 5 | 101 | 0.433 | 0.970 | 0.031 |
| horizontal_displaced_over_half_footprint | 58 | 174 | 2 | 104 | 0.326 | 0.943 | 0.046 |
| displaced_over_half_footprint | 96 | 136 | 12 | 94 | 0.550 | 0.895 | 0.149 |
| not_placed_safe | 80 | 152 | 9 | 97 | 0.493 | 0.950 | 0.060 |
| not_valid | 0 | 232 | 0 | 106 | 0.000 | - | 0.000 |

Counts are raw rows; precision/recall/danger-rate are weighted.

## Univariate Phi -> Y (release candidates)

| feature | n | rho(dtheta) | rho(d_xy) | rho(d_z) | Q1..Q4 rate not_placed_safe | Q1..Q4 mean dtheta |
|---|---:|---:|---:|---:|---|---|
| support_ratio | 338 | -0.203 | -0.177 | -0.296 | 0.298 / - / 0.455 / 0.036 | 26.4 / - / 34.7 / 3.5 |
| com_margin | 338 | -0.221 | -0.162 | -0.310 | 0.290 / - / 0.411 / 0.098 | 26.8 / - / 31.1 / 5.5 |
| overhang_ratio | 338 | 0.203 | 0.177 | 0.296 | 0.035 / 0.341 / - / - | 3.4 / 28.8 / - / - |
| drop_normalized | 338 | -0.011 | -0.012 | 0.046 | 0.319 / 0.244 / 0.272 / 0.121 | 28.1 / 20.3 / 22.4 / 10.9 |
| support_imbalance | 338 | 0.084 | 0.042 | -0.045 | 0.292 / - / 0.131 / 0.294 | 25.8 / - / 6.8 / 25.5 |
| left_right_imbalance | 338 | -0.100 | -0.026 | -0.118 | 0.282 / - / - / 0.125 | 23.9 / - / - / 10.6 |
| front_back_imbalance | 338 | -0.030 | -0.021 | -0.058 | 0.276 / - / - / 0.221 | 23.2 / - / - / 19.2 |

## Within-snapshot contrast (safe minus dangerous)

Snapshots containing both safe and dangerous release rows: 10

| feature | snapshots | mean diff | safe-higher count |
|---|---:|---:|---:|
| support_ratio | 10 | 0.152 | 6 |
| com_margin | 10 | 0.328 | 5 |
| overhang_ratio | 10 | -0.152 | 1 |
| drop_normalized | 10 | 0.008 | 6 |
| support_imbalance | 10 | -0.193 | 1 |
| left_right_imbalance | 10 | 0.096 | 7 |
| front_back_imbalance | 10 | -0.011 | 2 |

## Gate reject reasons (release candidates)

| reason | rejected dangerous (TP) | rejected safe (FP) |
|---|---:|---:|
| com_margin | 75 | 151 |
| overhang | 67 | 145 |
| support | 67 | 145 |
| support_imbalance | 24 | 20 |

Dangerous/safe by `not_placed_safe`; a candidate can carry several reasons.

## Single-feature AUC (higher score = claimed dangerous)

| feature | not_placed_safe | rotated_over_30 | horizontal_displaced_over_half_footprint |
|---|---:|---:|---:|
| support_ratio | 0.607 | 0.600 | 0.655 |
| com_margin | 0.593 | 0.609 | 0.650 |
| overhang_ratio | 0.607 | 0.600 | 0.655 |
| drop_normalized | 0.440 | 0.443 | 0.416 |
| abs_support_imbalance | 0.508 | 0.542 | 0.411 |
| abs_left_right_imbalance | 0.495 | 0.534 | 0.408 |
| abs_front_back_imbalance | 0.531 | 0.529 | 0.422 |

## Hard-accept sweep on support_ratio (release candidates)

| min support_ratio | n | weighted share accepted | not_placed_safe raw/weighted | rotated_over_30 raw/weighted |
|---:|---:|---:|---:|---:|
| 0.5 | 101 | 0.295 | 0.079 / 0.038 | 0.040 / 0.008 |
| 0.6 | 86 | 0.278 | 0.035 / 0.007 | 0.035 / 0.007 |
| 0.7 | 53 | 0.180 | 0.000 / 0.000 | 0.000 / 0.000 |
| 0.8 | 49 | 0.167 | 0.000 / 0.000 | 0.000 / 0.000 |
| 0.9 | 25 | 0.111 | 0.000 / 0.000 | 0.000 / 0.000 |
| 0.95 | 21 | 0.093 | 0.000 / 0.000 | 0.000 / 0.000 |

## Logistic separability probe (snapshot-held-out)

Train n=247, test n=91; features: intercept, support_ratio, com_margin, drop_normalized, abs_support_imbalance, abs_left_right_imbalance, abs_front_back_imbalance

| label | test AUC | best single-feature test AUC | weights |
|---|---:|---:|---|
| not_placed_safe | 0.731 | 0.687 | [0.535, -5.719, 1.534, -0.12, -0.296, 0.784, 2.209] |
| rotated_over_30 | 0.637 | 0.669 | [-0.867, -3.713, 0.288, 0.001, 1.816, 0.569, 0.051] |

## Danger rate by score band (raw)

### release_candidate

| band | n | not_placed_safe | rotated_over_30 | not_valid |
|---|---:|---:|---:|---:|
| top1 | 10 | 0.100 | 0.200 | 0.000 |
| top10 | 80 | 0.188 | 0.163 | 0.000 |
| top10pct | 120 | 0.267 | 0.275 | 0.000 |
| tail | 128 | 0.320 | 0.273 | 0.000 |

### candidate

| band | n | not_placed_safe | rotated_over_30 | not_valid |
|---|---:|---:|---:|---:|
| top1 | 6 | 0.167 | 0.167 | 0.000 |
| top10 | 48 | 0.167 | 0.167 | 0.000 |
| top10pct | 40 | 0.050 | 0.000 | 0.000 |
| tail | 48 | 0.042 | 0.021 | 0.000 |

