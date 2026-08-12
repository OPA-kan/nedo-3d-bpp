# Cross-run physical afterstate-value audit

Targets are best remaining H3 gains after subtracting each child state's immediate H0 outcome. Outcome axes remain separate.

| Axis | Rows | Immediate | Action geometry | Afterstate | Action + afterstate | Permuted afterstate min/median/max |
|---|---:|---:|---:|---:|---:|---:|
| placed_count | 4 | 1/4 | 2/4 | 0/4 | 0/4 | 1/4/4 |
| fill_score_proxy | 22 | 16/22 | 17/22 | 21/22 | 21/22 | 6/9/13 |
| com_z | 26 | 14/26 | 15/26 | 16/26 | 13/26 | 9/13/17 |
| surface_total_variation | 26 | 22/26 | 16/26 | 13/26 | 12/26 | 12/16/17 |
| priority_misrouted | 0 | 0/0 | 0/0 | 0/0 | 0/0 | 0/0/0 |
| soft_covered_by_other | 4 | 0/4 | 4/4 | 4/4 | 4/4 | 4/4/4 |

## Paired exact comparisons

Each `W/T/L` is for the model named first. The exact two-sided sign test uses only discordant held-out rows.

| Axis | Afterstate vs action | p | Action+state vs action | p | Afterstate vs immediate | p |
|---|---:|---:|---:|---:|---:|---:|
| placed_count | 0/2/2 | 0.5 | 0/2/2 | 0.5 | 0/3/1 | 1 |
| fill_score_proxy | 4/18/0 | 0.125 | 4/18/0 | 0.125 | 6/15/1 | 0.125 |
| com_z | 4/19/3 | 1 | 1/22/3 | 0.625 | 6/16/4 | 0.7539 |
| surface_total_variation | 6/11/9 | 0.6072 | 5/12/9 | 0.424 | 2/13/11 | 0.02246 |
| priority_misrouted | 0/0/0 | 1 | 0/0/0 | 1 | 0/0/0 | 1 |
| soft_covered_by_other | 0/4/0 | 1 | 0/4/0 | 1 | 4/0/0 | 0.125 |

## Fill-only selective consensus

- discovery_retrospective: 101/103 correct at 103/111 coverage
- late_retrospective: 20/20 correct at 20/22 coverage

> This consensus was designed after inspecting the five-run late errors. Both existing splits are retrospective; only a subsequent physical run can confirm it.

The afterstate model is a fixed-L2 no-intercept ridge over the difference of permutation-invariant physical child-state summaries. Each target run is excluded in full from training. Seven deterministic training-state rotations are reported as a negative control.

> Synthetic run-held-out diagnostic. It tests learnable continuation value in H3 states, not episode-level policy improvement.
