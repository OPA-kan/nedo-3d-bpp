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

## Reading (model-selection conclusions, not truths)

- Calibration: decile-mean predictions track observed rates closely, so P_hat is usable as a probability. Within the range compared here, no nonlinear rule beat the linear one. That removes one motivation for nonlinearity (miscalibration), but not the others: candidate-dependent loss L(s,a), different damage for large vs small rotations, nonlinear risk tolerance, rotated_over_30 being a coarse proxy for the true loss, and score not being a utility scale could each still justify a nonlinear form. None of those was tested here.
- Linear-lambda sweeps and hard-epsilon sweeps produced nearly the same empirical frontier ON these 24 snapshots, these candidate sets, and this parameter grid. With finite discrete candidate sets this is not guaranteed in general (unsupported Pareto points can exist), so it is an empirical observation, not a duality theorem.
- hard+fallback never starved here, but this is offline on saved candidate sets with a calibrated probability and a least-risky fallback. It rehabilitates neither the old static enforce gate (different features, thresholds, and fallback design) nor online enforcement: live candidate generation and search cutoffs change the candidate set, so online starvation is not ruled out.
- state_scaled_linear is numerically identical to linear at every lambda because the sampled snapshots span remaining items 25-34 (scale 0.831-1.130 around the mean). This dataset cannot test state-dependent lambda(s) -- and remaining items is itself an unverified proxy for the failure loss V_safe - V_fail. Early snapshots would be added to identify whether the failure loss varies with state, not merely to widen the remaining-items range.
- With only 3/24 baseline topple snapshots, 3->0 and loss differences like 0.042 vs 0.047 are unstable; family-level micro-ranking is unreadable. The robust statement: every family shows signs of avoiding dangerous candidates, and no clear ordering between families is visible. There is no evidence to adopt a more complex form than Q - lambda*P_hat on current data.

