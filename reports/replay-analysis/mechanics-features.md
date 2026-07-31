# Mechanical topple features: frozen-split comparison

- release rows: 1180 in 33 snapshots (development+validation; final_holdout closed)
- degenerate contact rows: 0
- Phi_mech inputs are pre-release predicted contact state only; replay observables stay labels (MATHEMATICAL_MODEL 5.2.1).
- Only 2 actually-changed shadow pairs exist across the datasets; within-snapshot discordant-pair accuracy is the statistically usable ranking metric until more changed pairs accumulate.

## Univariate mechanics AUC (rotated_over_30, danger-oriented)

| feature | AUC |
|---|---:|
| d_min | 0.757 |
| theta_c_min | 0.755 |
| B_min | 0.786 |
| log1p_eta_max | 0.788 |

## rotated_over_30

| feature set | LOSO AUC | 95% CI | worst case | worst pool | worst extrap. (case) | worst extrap. (pool) | pair acc. (n) |
|---|---:|---|---:|---:|---:|---:|---:|
| static_only | 0.698 | [0.620, 0.767] | 0.669 | 0.567 | 0.534 | 0.575 | 0.681 (7303) |
| mechanics_only | 0.819 | [0.764, 0.870] | 0.783 | 0.695 | 0.798 | 0.697 | 0.824 (7303) |
| static_plus_mechanics | 0.815 | [0.748, 0.873] | 0.770 | 0.676 | 0.703 | 0.669 | 0.825 (7303) |

### Extrapolation detail

| feature set | split | direction | AUC |
|---|---|---|---:|
| static_only | case | test_b000 | 0.534 |
| static_only | case | test_b001 | 0.632 |
| static_only | pool | test_k10 | 0.985 |
| static_only | pool | test_k15 | 0.683 |
| static_only | pool | test_k20 | 0.604 |
| static_only | pool | test_k30 | 0.739 |
| static_only | pool | test_k40 | 0.575 |
| mechanics_only | case | test_b000 | 0.798 |
| mechanics_only | case | test_b001 | 0.890 |
| mechanics_only | pool | test_k10 | 0.967 |
| mechanics_only | pool | test_k15 | 0.856 |
| mechanics_only | pool | test_k20 | 0.817 |
| mechanics_only | pool | test_k30 | 0.879 |
| mechanics_only | pool | test_k40 | 0.697 |
| static_plus_mechanics | case | test_b000 | 0.703 |
| static_plus_mechanics | case | test_b001 | 0.831 |
| static_plus_mechanics | pool | test_k10 | 0.978 |
| static_plus_mechanics | pool | test_k15 | 0.817 |
| static_plus_mechanics | pool | test_k20 | 0.745 |
| static_plus_mechanics | pool | test_k30 | 0.865 |
| static_plus_mechanics | pool | test_k40 | 0.669 |


## not_placed_safe

| feature set | LOSO AUC | 95% CI | worst case | worst pool | worst extrap. (case) | worst extrap. (pool) | pair acc. (n) |
|---|---:|---|---:|---:|---:|---:|---:|
| static_only | 0.709 | [0.634, 0.780] | 0.680 | 0.554 | 0.564 | 0.584 | 0.748 (7742) |
| mechanics_only | 0.809 | [0.749, 0.864] | 0.787 | 0.693 | 0.797 | 0.701 | 0.836 (7742) |
| static_plus_mechanics | 0.835 | [0.778, 0.887] | 0.808 | 0.703 | 0.760 | 0.666 | 0.854 (7742) |

### Extrapolation detail

| feature set | split | direction | AUC |
|---|---|---|---:|
| static_only | case | test_b000 | 0.564 |
| static_only | case | test_b001 | 0.697 |
| static_only | pool | test_k10 | 0.959 |
| static_only | pool | test_k15 | 0.787 |
| static_only | pool | test_k20 | 0.634 |
| static_only | pool | test_k30 | 0.745 |
| static_only | pool | test_k40 | 0.584 |
| mechanics_only | case | test_b000 | 0.797 |
| mechanics_only | case | test_b001 | 0.867 |
| mechanics_only | pool | test_k10 | 0.964 |
| mechanics_only | pool | test_k15 | 0.895 |
| mechanics_only | pool | test_k20 | 0.800 |
| mechanics_only | pool | test_k30 | 0.810 |
| mechanics_only | pool | test_k40 | 0.701 |
| static_plus_mechanics | case | test_b000 | 0.760 |
| static_plus_mechanics | case | test_b001 | 0.858 |
| static_plus_mechanics | pool | test_k10 | 0.982 |
| static_plus_mechanics | pool | test_k15 | 0.903 |
| static_plus_mechanics | pool | test_k20 | 0.750 |
| static_plus_mechanics | pool | test_k30 | 0.867 |
| static_plus_mechanics | pool | test_k40 | 0.666 |

