# Risk-integration rule comparison (offline, held-out P_hat)

- release rows: 1180 in 33 snapshots; mechanics-feature LOSO predictions
- Selections run over each snapshot's sampled release set; the live settled preference and lookahead are not reproduced (same caveat as the rerank sweep).

## Calibration of P_hat (deciles)

| bin | n | mean predicted | raw rate | weighted rate |
|---:|---:|---:|---:|---:|
| 1 | 118 | 0.005 | 0.025 | 0.012 |
| 2 | 115 | 0.017 | 0.026 | 0.016 |
| 3 | 121 | 0.064 | 0.074 | 0.154 |
| 4 | 118 | 0.111 | 0.059 | 0.196 |
| 5 | 118 | 0.137 | 0.110 | 0.130 |
| 6 | 118 | 0.210 | 0.203 | 0.183 |
| 7 | 118 | 0.272 | 0.305 | 0.295 |
| 8 | 118 | 0.358 | 0.390 | 0.458 |
| 9 | 118 | 0.523 | 0.576 | 0.544 |
| 10 | 118 | 0.704 | 0.627 | 0.675 |

## Rule frontiers

| rule | param | tau | rotated | unsafe | mean loss | max loss | starved | on frontier |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| quadratic | 8.00 | - | 0 | 0 | 0.095 | 0.871 | - | YES |
| quadratic | 16.00 | - | 0 | 0 | 0.097 | 0.871 | - | no |
| linear | 2.00 | - | 0 | 0 | 0.098 | 0.871 | - | no |
| state_scaled_linear | 2.00 | - | 0 | 0 | 0.098 | 0.871 | - | no |
| linear | 4.00 | - | 0 | 0 | 0.099 | 0.871 | - | no |
| state_scaled_linear | 4.00 | - | 0 | 0 | 0.099 | 0.871 | - | no |
| hinge | 2.00 | 0.20 | 1 | 0 | 0.068 | 0.871 | - | YES |
| hinge | 4.00 | 0.20 | 1 | 0 | 0.069 | 0.871 | - | no |
| hard | 0.20 | - | 1 | 0 | 0.080 | 0.871 | 0 | no |
| quadratic | 4.00 | - | 1 | 0 | 0.082 | 0.871 | - | no |
| hard | 0.10 | - | 1 | 1 | 0.200 | 1.539 | 0 | no |
| hinge | 4.00 | 0.40 | 2 | 0 | 0.053 | 0.871 | - | YES |
| hard | 0.30 | - | 2 | 1 | 0.064 | 0.871 | 0 | no |
| state_scaled_linear | 0.25 | - | 3 | 2 | 0.003 | 0.069 | - | YES |
| linear | 0.25 | - | 3 | 2 | 0.003 | 0.069 | - | no |
| quadratic | 1.00 | - | 3 | 2 | 0.006 | 0.076 | - | no |
| linear | 0.50 | - | 3 | 2 | 0.006 | 0.076 | - | no |
| state_scaled_linear | 0.50 | - | 3 | 2 | 0.006 | 0.076 | - | no |
| quadratic | 2.00 | - | 3 | 2 | 0.013 | 0.231 | - | no |
| linear | 1.00 | - | 3 | 2 | 0.035 | 0.231 | - | no |
| state_scaled_linear | 1.00 | - | 3 | 2 | 0.035 | 0.231 | - | no |
| hard | 0.50 | - | 3 | 1 | 0.051 | 0.871 | 0 | no |
| hinge | 2.00 | 0.40 | 4 | 2 | 0.003 | 0.069 | - | YES |
| hinge | 1.00 | 0.20 | 4 | 3 | 0.007 | 0.076 | - | no |
| hinge | 1.00 | 0.40 | 5 | 3 | 0.001 | 0.031 | - | YES |

Frontier = not dominated on (selected rotated, mean score loss). Baseline (lambda=0): 5 rotated, 0 loss by definition.

## Reading (model-selection conclusions, not truths)

- Calibration: decile-mean predictions track observed rates closely, so P_hat is usable as a probability. Within the range compared here, no nonlinear rule beat the linear one. That removes one motivation for nonlinearity (miscalibration), but not the others: candidate-dependent loss L(s,a), different damage for large vs small rotations, nonlinear risk tolerance, rotated_over_30 being a coarse proxy for the true loss, and score not being a utility scale could each still justify a nonlinear form. None of those was tested here.
- Linear-lambda sweeps and hard-epsilon sweeps produced nearly the same empirical frontier ON these 33 snapshots, these candidate sets, and this parameter grid. With finite discrete candidate sets this is not guaranteed in general (unsupported Pareto points can exist), so it is an empirical observation, not a duality theorem.
- hard+fallback never starved here, but this is offline on saved candidate sets with a calibrated probability and a least-risky fallback. It rehabilitates neither the old static enforce gate (different features, thresholds, and fallback design) nor online enforcement: live candidate generation and search cutoffs change the candidate set, so online starvation is not ruled out.
- state_scaled_linear is numerically identical to linear at every lambda because the sampled snapshots span remaining items 25-34 (scale 0.838-1.140 around the mean). This dataset cannot test state-dependent lambda(s) -- and remaining items is itself an unverified proxy for the failure loss V_safe - V_fail. Early snapshots would be added to identify whether the failure loss varies with state, not merely to widen the remaining-items range.
- With only 5/33 baseline topple snapshots, single-topple and third-decimal loss differences are unstable; family-level micro-ranking is unreadable. The robust statement: every family shows signs of avoiding dangerous candidates, and no clear ordering between families is visible. There is no evidence to adopt a more complex form than Q - lambda*P_hat on current data.

