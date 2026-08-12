# Bounded counterfactual teacher-signal audit

- Graphs / graphs with edges: 3 / 3
- Conditions: 2
- Edges / failed physical edges: 186 / 0
- Terminal trajectories: 96 (horizon:96)
- Sibling pairs: 93
- Equal-immediate-score pairs with different recorded downstream ranges: 0 / 39
- Unequal-score pairs with different downstream ranges: 54
- Lower-score action had a better reachable leaf: fill_score_proxy:36, com_z:10, surface_total_variation:12
- Training readiness: not_established_preregistered_gates_failed.
- Root-step split is preregistered as discovery <15 and late holdout >=15.

| case | step | edges | terminal trajectories | terminals | siblings | equal score separated | unequal score separated |
|---|---:|---:|---:|---|---:|---:|---:|
| m-dual-empty | 6 | 62 | 32 | horizon:32 | 31 | 0 / 3 | 28 |
| m-dual-full-stream | 6 | 62 | 32 | horizon:32 | 31 | 0 / 15 | 16 |
| m-dual-full-stream | 9 | 62 | 32 | horizon:32 | 31 | 0 / 21 | 10 |

This audit keeps placed, fill, CoG, surface variation, priority and soft-item outcomes separate. A 'better reachable leaf' is an existence result inside the bounded graph, not a probability, a competition-score total, or a learned value estimate.
