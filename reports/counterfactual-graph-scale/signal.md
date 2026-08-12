# Bounded counterfactual teacher-signal audit

- Graphs / graphs with edges: 24 / 18
- Conditions: 8
- Edges / failed physical edges: 226 / 0
- Terminal trajectories: 136 (horizon:124, no_candidate:12)
- Sibling pairs: 112
- Equal-immediate-score pairs with different recorded downstream ranges: 0 / 44
- Unequal-score pairs with different downstream ranges: 66
- Lower-score action had a better reachable leaf: placed_count:1, fill_score_proxy:33, com_z:29, surface_total_variation:24, soft_covered_by_other:3
- Training readiness: not_established_preregistered_gates_failed.
- Root-step split is preregistered as discovery <15 and late holdout >=15.

| case | step | edges | terminal trajectories | terminals | siblings | equal score separated | unequal score separated |
|---|---:|---:|---:|---|---:|---:|---:|
| m-dual-empty | 6 | 14 | 8 | horizon:8 | 7 | 0 / 3 | 4 |
| m-dual-empty | 12 | 14 | 8 | horizon:8 | 7 | 0 / 2 | 5 |
| m-dual-empty | 15 | 14 | 8 | horizon:8 | 7 | 0 / 7 | 0 |
| m-dual-full-stream | 6 | 14 | 8 | horizon:8 | 7 | 0 / 7 | 0 |
| m-dual-full-stream | 9 | 14 | 8 | horizon:8 | 7 | 0 / 5 | 2 |
| m-dual-full-stream | 12 | 14 | 8 | horizon:8 | 7 | 0 / 7 | 0 |
| m-dual-preloaded-dedicated | 6 | 14 | 8 | horizon:8 | 7 | 0 / 0 | 7 |
| m-dual-preloaded-dedicated | 12 | 14 | 8 | horizon:8 | 7 | 0 / 0 | 7 |
| m-dual-preloaded-dedicated | 15 | 14 | 8 | horizon:8 | 7 | 0 / 0 | 6 |
| m-dual-shelf-mixed | 6 | 14 | 8 | horizon:8 | 7 | 0 / 3 | 4 |
| m-dual-shelf-mixed | 12 | 14 | 8 | horizon:8 | 7 | 0 / 1 | 6 |
| m-dual-shelf-mixed | 15 | 10 | 6 | horizon:4, no_candidate:2 | 5 | 0 / 1 | 4 |
| m-single-empty-noshelf | 6 | 14 | 8 | horizon:8 | 7 | 0 / 2 | 5 |
| m-single-empty-noshelf | 12 | 0 | 1 | no_candidate:1 | 0 | 0 / 0 | 0 |
| m-single-empty-noshelf | 15 | 2 | 2 | no_candidate:2 | 1 | 0 / 0 | 0 |
| m-single-empty-noshelf | 6 | 14 | 8 | horizon:8 | 7 | 0 / 3 | 4 |
| m-single-empty-noshelf | 12 | 0 | 1 | no_candidate:1 | 0 | 0 / 0 | 0 |
| m-single-empty-noshelf | 15 | 0 | 1 | no_candidate:1 | 0 | 0 / 0 | 0 |
| m-single-preloaded | 6 | 0 | 1 | no_candidate:1 | 0 | 0 / 0 | 0 |
| m-single-preloaded | 9 | 0 | 1 | no_candidate:1 | 0 | 0 / 0 | 0 |
| m-single-preloaded | 12 | 0 | 1 | no_candidate:1 | 0 | 0 / 0 | 0 |
| m-single-empty-shelf | 6 | 14 | 8 | horizon:8 | 7 | 0 / 0 | 7 |
| m-single-empty-shelf | 12 | 14 | 8 | horizon:8 | 7 | 0 / 2 | 5 |
| m-single-empty-shelf | 15 | 4 | 2 | no_candidate:2 | 1 | 0 / 1 | 0 |

This audit keeps placed, fill, CoG, surface variation, priority and soft-item outcomes separate. A 'better reachable leaf' is an existence result inside the bounded graph, not a probability, a competition-score total, or a learned value estimate.
