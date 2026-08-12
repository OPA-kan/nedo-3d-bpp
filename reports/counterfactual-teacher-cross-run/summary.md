# Cross-run action-only teacher audit

Each row trains on discovery roots from the other runs and tests the complete target run's late roots.

| Target run | Axis | Rows | Immediate | Full pair | Geometry pair | Score only | Action delta | Geometry delta |
|---:|---|---:|---:|---:|---:|---:|---:|---:|
| 31563029977 | fill_score_proxy | 7 | 4/7 | 5/7 | 5/7 | 3/7 | 5/7 | 5/7 |
| 31563029977 | com_z | 10 | 8/10 | 8/10 | 6/10 | 4/10 | 5/10 | 5/10 |
| 31563029977 | surface_total_variation | 10 | 5/10 | 6/10 | 5/10 | 5/10 | 7/10 | 7/10 |
| 31565624982 | fill_score_proxy | 7 | 5/7 | 6/7 | 6/7 | 2/7 | 6/7 | 6/7 |
| 31565624982 | com_z | 8 | 6/8 | 5/8 | 5/8 | 4/8 | 4/8 | 4/8 |
| 31565624982 | surface_total_variation | 8 | 4/8 | 5/8 | 5/8 | 4/8 | 7/8 | 7/8 |
| 31566153353 | fill_score_proxy | 10 | 2/10 | 7/10 | 7/10 | 4/10 | 8/10 | 8/10 |
| 31566153353 | com_z | 12 | 12/12 | 10/12 | 8/12 | 8/12 | 8/12 | 8/12 |
| 31566153353 | surface_total_variation | 12 | 9/12 | 8/12 | 8/12 | 9/12 | 8/12 | 8/12 |

## Pooled exact counts

- fill_score_proxy: immediate 11/24; full action 18/24; geometry no score 18/24; score only 9/24; action delta 19/24; geometry delta 19/24
- com_z: immediate 26/30; full action 23/30; geometry no score 19/30; score only 16/30; action delta 17/30; geometry delta 17/30
- surface_total_variation: immediate 18/30; full action 19/30; geometry no score 18/30; score only 18/30; action delta 22/30; geometry delta 22/30

## Two-axis Pareto shadow

- immediate_higher: proposals 30/30; non-contradicted 8; contradicted 22
- geometry_delta_consensus: proposals 10/30; non-contradicted 6; contradicted 4

## Joint reachable-set Pareto dominance

- immediate score: 6/6
- geometry utility delta: 4/6

> Run-held-out synthetic diagnostic; repeated scenarios and small late denominators do not establish official-policy gain.
