# Cross-run action-only teacher audit

Each row trains on discovery roots from the other runs and tests the complete target run's late roots.

| Target run | Axis | Rows | Immediate | Full pair | Geometry pair | Score only | Action delta | Geometry delta |
|---:|---|---:|---:|---:|---:|---:|---:|---:|
| 31563029977 | fill_score_proxy | 7 | 4/7 | 5/7 | 5/7 | 3/7 | 5/7 | 5/7 |
| 31563029977 | com_z | 10 | 8/10 | 8/10 | 9/10 | 4/10 | 7/10 | 7/10 |
| 31563029977 | surface_total_variation | 10 | 5/10 | 6/10 | 5/10 | 5/10 | 7/10 | 7/10 |
| 31565624982 | fill_score_proxy | 7 | 5/7 | 6/7 | 6/7 | 2/7 | 6/7 | 6/7 |
| 31565624982 | com_z | 8 | 6/8 | 5/8 | 5/8 | 4/8 | 4/8 | 4/8 |
| 31565624982 | surface_total_variation | 8 | 4/8 | 6/8 | 5/8 | 4/8 | 7/8 | 7/8 |
| 31566153353 | fill_score_proxy | 10 | 2/10 | 7/10 | 7/10 | 4/10 | 8/10 | 8/10 |
| 31566153353 | com_z | 12 | 12/12 | 11/12 | 10/12 | 10/12 | 10/12 | 10/12 |
| 31566153353 | surface_total_variation | 12 | 9/12 | 8/12 | 8/12 | 9/12 | 8/12 | 8/12 |
| 31566975749 | fill_score_proxy | 9 | 5/9 | 7/9 | 7/9 | 4/9 | 7/9 | 7/9 |
| 31566975749 | com_z | 12 | 10/12 | 9/12 | 9/12 | 5/12 | 8/12 | 8/12 |
| 31566975749 | surface_total_variation | 12 | 7/12 | 8/12 | 7/12 | 7/12 | 9/12 | 9/12 |

## Pooled exact counts

- fill_score_proxy: immediate 16/33; full action 25/33; geometry no score 25/33; score only 13/33; action delta 26/33; geometry delta 26/33
- com_z: immediate 36/42; full action 33/42; geometry no score 33/42; score only 23/42; action delta 29/42; geometry delta 29/42
- surface_total_variation: immediate 25/42; full action 28/42; geometry no score 25/42; score only 25/42; action delta 31/42; geometry delta 31/42

## Two-axis Pareto shadow

- immediate_higher: proposals 42/42; non-contradicted 12; contradicted 30
- geometry_delta_consensus: proposals 15/42; non-contradicted 9; contradicted 6

## Joint reachable-set Pareto dominance

- immediate score: 9/9
- geometry utility delta: 6/9

> Run-held-out synthetic diagnostic; repeated scenarios and small late denominators do not establish official-policy gain.
