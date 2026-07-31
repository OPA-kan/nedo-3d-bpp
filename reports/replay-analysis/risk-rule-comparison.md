# Risk-integration rule comparison (offline, held-out P_hat)

- release rows: 849 in 24 snapshots; mechanics-feature LOSO predictions
- Selections run over each snapshot's sampled release set; the live settled preference and lookahead are not reproduced (same caveat as the rerank sweep).

## Calibration of P_hat (deciles)

| bin | n | mean predicted | raw rate | weighted rate |
|---:|---:|---:|---:|---:|
| 1 | 85 | 0.001 | 0.000 | 0.000 |
| 2 | 78 | 0.004 | 0.026 | 0.092 |
| 3 | 92 | 0.027 | 0.022 | 0.013 |
| 4 | 85 | 0.064 | 0.071 | 0.217 |
| 5 | 84 | 0.086 | 0.048 | 0.060 |
| 6 | 85 | 0.177 | 0.212 | 0.179 |
| 7 | 84 | 0.256 | 0.298 | 0.291 |
| 8 | 86 | 0.353 | 0.372 | 0.420 |
| 9 | 85 | 0.523 | 0.529 | 0.594 |
| 10 | 85 | 0.713 | 0.624 | 0.626 |

## Rule frontiers

| rule | param | tau | rotated | unsafe | mean loss | max loss | starved | on frontier |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| hard | 0.10 | - | 0 | 0 | 0.042 | 0.269 | 0 | YES |
| quadratic | 16.00 | - | 0 | 0 | 0.044 | 0.269 | - | no |
| linear | 2.00 | - | 0 | 0 | 0.047 | 0.269 | - | no |
| state_scaled_linear | 2.00 | - | 0 | 0 | 0.047 | 0.269 | - | no |
| linear | 4.00 | - | 0 | 0 | 0.048 | 0.269 | - | no |
| state_scaled_linear | 4.00 | - | 0 | 0 | 0.048 | 0.269 | - | no |
| quadratic | 1.00 | - | 1 | 0 | 0.007 | 0.076 | - | YES |
| hinge | 1.00 | 0.20 | 1 | 0 | 0.007 | 0.076 | - | no |
| quadratic | 2.00 | - | 1 | 0 | 0.008 | 0.076 | - | no |
| linear | 0.50 | - | 1 | 0 | 0.008 | 0.076 | - | no |
| state_scaled_linear | 0.50 | - | 1 | 0 | 0.008 | 0.076 | - | no |
| hinge | 2.00 | 0.20 | 1 | 0 | 0.015 | 0.189 | - | no |
| hinge | 4.00 | 0.20 | 1 | 0 | 0.015 | 0.189 | - | no |
| hard | 0.20 | - | 1 | 0 | 0.020 | 0.189 | 0 | no |
| quadratic | 4.00 | - | 1 | 0 | 0.026 | 0.189 | - | no |
| quadratic | 8.00 | - | 1 | 0 | 0.028 | 0.209 | - | no |
| linear | 1.00 | - | 1 | 0 | 0.028 | 0.209 | - | no |
| state_scaled_linear | 1.00 | - | 1 | 0 | 0.028 | 0.209 | - | no |
| hinge | 2.00 | 0.40 | 2 | 0 | 0.004 | 0.069 | - | YES |
| hinge | 4.00 | 0.40 | 2 | 0 | 0.004 | 0.069 | - | YES |
| linear | 0.25 | - | 2 | 0 | 0.004 | 0.069 | - | no |
| state_scaled_linear | 0.25 | - | 2 | 0 | 0.004 | 0.069 | - | no |
| hinge | 1.00 | 0.40 | 3 | 1 | 0.001 | 0.031 | - | YES |
| hard | 0.50 | - | 3 | 1 | 0.001 | 0.031 | 0 | YES |
| hard | 0.30 | - | 3 | 1 | 0.014 | 0.189 | 0 | no |

Frontier = not dominated on (selected rotated, mean score loss). Baseline (lambda=0): 3 rotated, 0 loss by definition.

## Reading

- Calibration: decile-mean predictions track observed rates closely across the range, so P_hat is usable as a probability. Nonlinear penalties are only justified as fixes for miscalibration; there is none to fix here.
- state_scaled_linear is numerically identical to linear at every lambda because the sampled snapshots span remaining items 25-34 (scale 0.831-1.130 around the mean). This dataset cannot test state-dependent lambda(s); it is not evidence against it.
- With only 3/24 baseline topple snapshots, differences of 1-2 selected topples between configurations are within noise; the family-level conclusion (no family separates from linear at matched loss) is the robust part.

