# Mechanical topple features: frozen-split comparison

- release rows: 849 in 24 snapshots (development+validation; final_holdout closed)
- degenerate contact rows: 0
- Phi_mech inputs are pre-release predicted contact state only; replay observables stay labels (MATHEMATICAL_MODEL 5.2.1).
- Only 2 actually-changed shadow pairs exist across the datasets; within-snapshot discordant-pair accuracy is the statistically usable ranking metric until more changed pairs accumulate.

## Univariate mechanics AUC (rotated_over_30, danger-oriented)

| feature | AUC |
|---|---:|
| d_min | 0.790 |
| theta_c_min | 0.786 |
| B_min | 0.817 |
| log1p_eta_max | 0.825 |

## rotated_over_30

| feature set | LOSO AUC | 95% CI | worst case | worst pool | worst extrap. (case) | worst extrap. (pool) | pair acc. (n) |
|---|---:|---|---:|---:|---:|---:|---:|
| static_only | 0.732 | [0.646, 0.807] | 0.693 | 0.673 | 0.676 | 0.638 | 0.720 (4884) |
| mechanics_only | 0.841 | [0.776, 0.898] | 0.797 | 0.764 | 0.814 | 0.771 | 0.842 (4884) |
| static_plus_mechanics | 0.827 | [0.752, 0.893] | 0.772 | 0.764 | 0.733 | 0.736 | 0.826 (4884) |

### Extrapolation detail

| feature set | split | direction | AUC |
|---|---|---|---:|
| static_only | case | test_b000 | 0.676 |
| static_only | case | test_b001 | 0.781 |
| static_only | pool | test_k10 | 0.982 |
| static_only | pool | test_k15 | 0.638 |
| static_only | pool | test_k20 | 0.642 |
| static_only | pool | test_k30 | 0.810 |
| static_only | pool | test_k40 | 0.717 |
| mechanics_only | case | test_b000 | 0.814 |
| mechanics_only | case | test_b001 | 0.951 |
| mechanics_only | pool | test_k10 | 0.966 |
| mechanics_only | pool | test_k15 | 0.833 |
| mechanics_only | pool | test_k20 | 0.845 |
| mechanics_only | pool | test_k30 | 0.937 |
| mechanics_only | pool | test_k40 | 0.771 |
| static_plus_mechanics | case | test_b000 | 0.733 |
| static_plus_mechanics | case | test_b001 | 0.927 |
| static_plus_mechanics | pool | test_k10 | 0.971 |
| static_plus_mechanics | pool | test_k15 | 0.736 |
| static_plus_mechanics | pool | test_k20 | 0.773 |
| static_plus_mechanics | pool | test_k30 | 0.924 |
| static_plus_mechanics | pool | test_k40 | 0.778 |


## not_placed_safe

| feature set | LOSO AUC | 95% CI | worst case | worst pool | worst extrap. (case) | worst extrap. (pool) | pair acc. (n) |
|---|---:|---|---:|---:|---:|---:|---:|
| static_only | 0.721 | [0.626, 0.808] | 0.681 | 0.624 | 0.666 | 0.639 | 0.753 (5071) |
| mechanics_only | 0.821 | [0.747, 0.888] | 0.796 | 0.743 | 0.817 | 0.750 | 0.857 (5071) |
| static_plus_mechanics | 0.838 | [0.774, 0.897] | 0.814 | 0.772 | 0.797 | 0.751 | 0.860 (5071) |

### Extrapolation detail

| feature set | split | direction | AUC |
|---|---|---|---:|
| static_only | case | test_b000 | 0.666 |
| static_only | case | test_b001 | 0.756 |
| static_only | pool | test_k10 | 0.956 |
| static_only | pool | test_k15 | 0.805 |
| static_only | pool | test_k20 | 0.639 |
| static_only | pool | test_k30 | 0.812 |
| static_only | pool | test_k40 | 0.692 |
| mechanics_only | case | test_b000 | 0.817 |
| mechanics_only | case | test_b001 | 0.907 |
| mechanics_only | pool | test_k10 | 0.964 |
| mechanics_only | pool | test_k15 | 0.888 |
| mechanics_only | pool | test_k20 | 0.820 |
| mechanics_only | pool | test_k30 | 0.850 |
| mechanics_only | pool | test_k40 | 0.750 |
| static_plus_mechanics | case | test_b000 | 0.797 |
| static_plus_mechanics | case | test_b001 | 0.873 |
| static_plus_mechanics | pool | test_k10 | 0.979 |
| static_plus_mechanics | pool | test_k15 | 0.868 |
| static_plus_mechanics | pool | test_k20 | 0.755 |
| static_plus_mechanics | pool | test_k30 | 0.872 |
| static_plus_mechanics | pool | test_k40 | 0.751 |

