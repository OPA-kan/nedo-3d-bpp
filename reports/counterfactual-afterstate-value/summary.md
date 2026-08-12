# Cross-run physical afterstate-value audit

Targets are best remaining H3 gains after subtracting each child state's immediate H0 outcome. Outcome axes remain separate.

| Axis | Rows | Immediate | Action geometry | Afterstate | Action + afterstate | Permuted afterstate min/median/max |
|---|---:|---:|---:|---:|---:|---:|
| placed_count | 4 | 1/4 | 2/4 | 0/4 | 0/4 | 1/2/4 |
| fill_score_proxy | 18 | 14/18 | 16/18 | 15/18 | 15/18 | 3/7/12 |
| com_z | 21 | 12/21 | 10/21 | 10/21 | 8/21 | 6/10/11 |
| surface_total_variation | 21 | 17/21 | 11/21 | 15/21 | 14/21 | 12/13/15 |
| priority_misrouted | 0 | 0/0 | 0/0 | 0/0 | 0/0 | 0/0/0 |
| soft_covered_by_other | 3 | 0/3 | 3/3 | 3/3 | 3/3 | 1/3/3 |

## Paired exact comparisons

Each `W/T/L` is for the model named first. The exact two-sided sign test uses only discordant held-out rows.

| Axis | Afterstate vs action | p | Action+state vs action | p | Afterstate vs immediate | p |
|---|---:|---:|---:|---:|---:|---:|
| placed_count | 0/2/2 | 0.5 | 0/2/2 | 0.5 | 0/3/1 | 1 |
| fill_score_proxy | 1/15/2 | 1 | 1/15/2 | 1 | 3/13/2 | 1 |
| com_z | 2/17/2 | 1 | 1/17/3 | 0.625 | 4/11/6 | 0.7539 |
| surface_total_variation | 9/7/5 | 0.424 | 8/8/5 | 0.5811 | 4/11/6 | 0.7539 |
| priority_misrouted | 0/0/0 | 1 | 0/0/0 | 1 | 0/0/0 | 1 |
| soft_covered_by_other | 0/3/0 | 1 | 0/3/0 | 1 | 3/0/0 | 0.25 |

The afterstate model is a fixed-L2 no-intercept ridge over the difference of permutation-invariant physical child-state summaries. Each target run is excluded in full from training. Seven deterministic training-state rotations are reported as a negative control.

> Synthetic run-held-out diagnostic. It tests learnable continuation value in H3 states, not episode-level policy improvement.
