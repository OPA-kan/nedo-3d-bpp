# Bounded H3 teacher-signal audit

- Graphs / graphs with edges: 8 / 5
- Edges / failed physical edges: 51 / 4
- Terminal trajectories: 32 (horizon:23, no_candidate:5, physical_failure:4)
- Sibling pairs: 24
- Equal-immediate-score pairs with different recorded downstream ranges: 0 / 15
- Unequal-score pairs with different downstream ranges: 8
- Lower-score action had a better reachable leaf: fill_score_proxy:2, com_z:2, surface_total_variation:4, soft_covered_by_other:2
- Training readiness: not established by this small condition matrix.

| case | step | edges | terminal trajectories | terminals | siblings | equal score separated | unequal score separated |
|---|---:|---:|---:|---|---:|---:|---:|
| m-dual-empty | 15 | 13 | 7 | horizon:7 | 6 | 0 / 4 | 2 |
| m-dual-full-stream | 12 | 14 | 8 | horizon:8 | 7 | 0 / 7 | 0 |
| m-dual-preloaded-dedicated | 15 | 14 | 8 | horizon:8 | 7 | 0 / 0 | 6 |
| m-dual-shelf-mixed | 15 | 6 | 4 | physical_failure:4 | 3 | 0 / 3 | 0 |
| m-single-empty-noshelf | 15 | 0 | 1 | no_candidate:1 | 0 | 0 / 0 | 0 |
| m-single-empty-noshelf | 15 | 0 | 1 | no_candidate:1 | 0 | 0 / 0 | 0 |
| m-single-preloaded | 12 | 0 | 1 | no_candidate:1 | 0 | 0 / 0 | 0 |
| m-single-empty-shelf | 15 | 4 | 2 | no_candidate:2 | 1 | 0 / 1 | 0 |

This audit keeps placed, fill, CoG, surface variation, priority and soft-item outcomes separate. A 'better reachable leaf' is an existence result inside the bounded graph, not a probability, a competition-score total, or a learned value estimate.
