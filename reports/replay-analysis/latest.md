# Replay dataset Phi -> Y analysis

- rows: 1291
- `20260730_161245-b000-k20-weighted-class_aware-shadow-0fb74669-c5ec4f65c4ca`: 83 rows
- `20260730_161846-b000-k20-weighted-class_aware-shadow-0fb74669-616c41f58ac4`: 50 rows
- `20260730_162936-b000-k40-weighted-class_aware-shadow-c1adf14c-80ff7f22fde9`: 66 rows
- `20260730_163302-b000-k40-weighted-class_aware-shadow-c1adf14c-79e9cd048e2a`: 91 rows
- `20260730_164227-b001-k20-weighted-class_aware-shadow-2e6de0af-24e614269991`: 124 rows
- `20260730_165446-b001-k20-weighted-class_aware-shadow-2e6de0af-6fef617f0a69`: 66 rows
- `20260731_004909-b000-k15-weighted-class_aware-shadow-64963f72-fcb3f260899a`: 91 rows
- `20260731_005851-b001-k30-weighted-class_aware-shadow-5119fcc9-58e3ccf96ad2`: 133 rows
- `20260731_011036-b000-k15-weighted-class_aware-shadow-64963f72-f9a761522e33`: 132 rows
- `20260731_012436-b001-k30-weighted-class_aware-shadow-5119fcc9-5944289f1f32`: 132 rows
- `20260731_013609-b000-k20-weighted-class_aware-shadow-0fb74669-86041076d589`: 83 rows
- `20260731_014746-b001-k20-weighted-class_aware-shadow-2e6de0af-837abea4e973`: 116 rows
- `20260731_020139-b000-k10-weighted-class_aware-shadow-fa6cf9cc-9a44e0dc484a`: 124 rows

## Label prevalence (per kind)

| kind | n | rotated_over_30 | horizontal_displaced_over_half_footprint | displaced_over_half_footprint | not_placed_safe | not_valid |
|---|---:|---:|---:|---:|---:|---:|
| release_candidate | 849 | 0.220 / 0.300 | 0.196 / 0.281 | 0.304 / 0.456 | 0.251 / 0.375 | 0.000 / 0.000 |
| candidate | 442 | 0.070 / 0.054 | 0.079 / 0.105 | 0.097 / 0.139 | 0.088 / 0.073 | 0.000 / 0.000 |

Cells are `raw rate / weighted rate`.

## Gate verdict split (release candidates)

| verdict | n | rotated_over_30 | horizontal_displaced_over_half_footprint | displaced_over_half_footprint | not_placed_safe | not_valid |
|---|---:|---:|---:|---:|---:|---:|
| pass | 329 | 0.112 / 0.051 | 0.134 / 0.135 | 0.179 / 0.197 | 0.143 / 0.116 | 0.000 / 0.000 |
| reject | 520 | 0.288 / 0.437 | 0.235 / 0.361 | 0.383 / 0.597 | 0.319 / 0.517 | 0.000 / 0.000 |

## Current gate confusion (positive = dangerous)

| label | TP | FP | FN | TN | reject precision | reject recall | danger rate among passed |
|---|---:|---:|---:|---:|---:|---:|---:|
| rotated_over_30 | 150 | 370 | 37 | 292 | 0.437 | 0.940 | 0.051 |
| horizontal_displaced_over_half_footprint | 122 | 398 | 44 | 285 | 0.361 | 0.830 | 0.135 |
| displaced_over_half_footprint | 199 | 321 | 59 | 270 | 0.597 | 0.847 | 0.197 |
| not_placed_safe | 166 | 354 | 47 | 282 | 0.517 | 0.890 | 0.116 |
| not_valid | 0 | 520 | 0 | 329 | 0.000 | - | 0.000 |

Counts are raw rows; precision/recall/danger-rate are weighted.

## Univariate Phi -> Y (release candidates)

| feature | n | rho(dtheta) | rho(d_xy) | rho(d_z) | Q1..Q4 rate not_placed_safe | Q1..Q4 mean dtheta |
|---|---:|---:|---:|---:|---|---|
| support_ratio | 849 | -0.177 | -0.097 | -0.214 | 0.232 / 0.407 / 0.429 / 0.061 | 19.4 / 29.1 / 37.1 / 6.1 |
| com_margin | 849 | -0.191 | -0.108 | -0.243 | 0.245 / 0.500 / 0.439 / 0.061 | 19.9 / 30.3 / 38.3 / 6.0 |
| overhang_ratio | 849 | 0.177 | 0.097 | 0.214 | 0.061 / 0.434 / 0.255 / - | 6.1 / 37.1 / 20.8 / - |
| drop_normalized | 849 | -0.112 | -0.149 | -0.034 | 0.380 / 0.219 / 0.182 / 0.207 | 33.4 / 18.7 / 15.0 / 16.1 |
| support_imbalance | 849 | 0.220 | 0.243 | 0.158 | 0.227 / 0.000 / 0.108 / 0.491 | 19.0 / 1.5 / 8.5 / 42.1 |
| left_right_imbalance | 849 | -0.035 | 0.008 | -0.022 | 0.254 / - / - / 0.238 | 21.0 / - / - / 22.0 |
| front_back_imbalance | 849 | 0.175 | 0.213 | 0.179 | 0.187 / - / 0.017 / 0.491 | 16.3 / - / 4.4 / 39.1 |

## Within-snapshot contrast (safe minus dangerous)

Snapshots containing both safe and dangerous release rows: 23

| feature | snapshots | mean diff | safe-higher count |
|---|---:|---:|---:|
| support_ratio | 23 | 0.095 | 14 |
| com_margin | 23 | 0.236 | 12 |
| overhang_ratio | 23 | -0.095 | 6 |
| drop_normalized | 23 | 0.019 | 16 |
| support_imbalance | 23 | -0.279 | 4 |
| left_right_imbalance | 23 | 0.072 | 12 |
| front_back_imbalance | 23 | -0.215 | 6 |

## Gate reject reasons (release candidates)

| reason | rejected dangerous (TP) | rejected safe (FP) |
|---|---:|---:|
| com_margin | 141 | 341 |
| overhang | 119 | 324 |
| support | 119 | 324 |
| support_imbalance | 81 | 73 |

Dangerous/safe by `not_placed_safe`; a candidate can carry several reasons.

## Single-feature AUC (higher score = claimed dangerous)

| feature | not_placed_safe | rotated_over_30 | horizontal_displaced_over_half_footprint |
|---|---:|---:|---:|
| support_ratio | 0.570 | 0.574 | 0.528 |
| com_margin | 0.577 | 0.580 | 0.534 |
| overhang_ratio | 0.570 | 0.574 | 0.528 |
| drop_normalized | 0.414 | 0.413 | 0.345 |
| abs_support_imbalance | 0.618 | 0.628 | 0.616 |
| abs_left_right_imbalance | 0.487 | 0.516 | 0.487 |
| abs_front_back_imbalance | 0.658 | 0.641 | 0.636 |

## Hard-accept sweep on support_ratio (release candidates)

| min support_ratio | n | weighted share accepted | not_placed_safe raw/weighted | rotated_over_30 raw/weighted |
|---:|---:|---:|---:|---:|
| 0.5 | 318 | 0.343 | 0.138 / 0.105 | 0.110 / 0.043 |
| 0.6 | 272 | 0.313 | 0.066 / 0.077 | 0.048 / 0.021 |
| 0.7 | 208 | 0.198 | 0.058 / 0.113 | 0.034 / 0.025 |
| 0.8 | 144 | 0.152 | 0.062 / 0.128 | 0.028 / 0.014 |
| 0.9 | 81 | 0.108 | 0.049 / 0.142 | 0.012 / 0.018 |
| 0.95 | 69 | 0.093 | 0.043 / 0.117 | 0.014 / 0.021 |

## Logistic separability probe (snapshot-held-out)

Train n=577, test n=272; features: intercept, support_ratio, com_margin, drop_normalized, abs_support_imbalance, abs_left_right_imbalance, abs_front_back_imbalance

| label | test AUC | best single-feature test AUC | weights |
|---|---:|---:|---|
| not_placed_safe | 0.830 | 0.764 | [-0.573, -1.355, -0.12, -3.986, -0.487, 0.501, 2.251] |
| rotated_over_30 | 0.787 | 0.750 | [-0.82, -1.873, -0.08, -3.621, 0.722, 0.392, 1.004] |

## Danger rate by score band (raw)

### release_candidate

| band | n | not_placed_safe | rotated_over_30 | not_valid |
|---|---:|---:|---:|---:|
| top1 | 24 | 0.042 | 0.125 | 0.000 |
| top10 | 193 | 0.078 | 0.067 | 0.000 |
| top10pct | 296 | 0.267 | 0.253 | 0.000 |
| tail | 336 | 0.351 | 0.286 | 0.000 |

### candidate

| band | n | not_placed_safe | rotated_over_30 | not_valid |
|---|---:|---:|---:|---:|
| top1 | 18 | 0.111 | 0.111 | 0.000 |
| top10 | 144 | 0.076 | 0.076 | 0.000 |
| top10pct | 136 | 0.066 | 0.037 | 0.000 |
| tail | 144 | 0.118 | 0.090 | 0.000 |

