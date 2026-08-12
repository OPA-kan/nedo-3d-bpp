# Counterfactual graph condition matrix

- Graphs: 24
- Conditions: 8
- Edges: 226
- Physical safe / failed: 226 / 0
- These synthetic scenarios measure condition coverage; their proxy scores are not mutually score-comparable.

| case | step | containers | shelves | preload | dedicated | pool | nodes | edges | safe | failed | items | terminal reasons |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| m-dual-empty | 6 | 2 | 0 | 0 | 0 | 20 | 15 | 14 | 14 | 0 | 5 | - |
| m-dual-empty | 12 | 2 | 0 | 0 | 0 | 20 | 15 | 14 | 14 | 0 | 6 | - |
| m-dual-empty | 15 | 2 | 0 | 0 | 0 | 20 | 15 | 14 | 14 | 0 | 4 | - |
| m-dual-full-stream | 6 | 2 | 1 | 0 | 1 | 40 | 15 | 14 | 14 | 0 | 5 | - |
| m-dual-full-stream | 9 | 2 | 1 | 0 | 1 | 40 | 15 | 14 | 14 | 0 | 5 | - |
| m-dual-full-stream | 12 | 2 | 1 | 0 | 1 | 40 | 15 | 14 | 14 | 0 | 4 | - |
| m-dual-preloaded-dedicated | 6 | 2 | 0 | 2 | 1 | 40 | 15 | 14 | 14 | 0 | 7 | - |
| m-dual-preloaded-dedicated | 12 | 2 | 0 | 2 | 1 | 40 | 15 | 14 | 14 | 0 | 7 | - |
| m-dual-preloaded-dedicated | 15 | 2 | 0 | 2 | 1 | 40 | 15 | 14 | 14 | 0 | 6 | - |
| m-dual-shelf-mixed | 6 | 2 | 1 | 0 | 0 | 20 | 15 | 14 | 14 | 0 | 7 | - |
| m-dual-shelf-mixed | 12 | 2 | 1 | 0 | 0 | 20 | 15 | 14 | 14 | 0 | 7 | - |
| m-dual-shelf-mixed | 15 | 2 | 1 | 0 | 0 | 20 | 11 | 10 | 10 | 0 | 6 | no_candidate:2 |
| m-single-empty-noshelf | 6 | 1 | 0 | 0 | 0 | 10 | 15 | 14 | 14 | 0 | 7 | - |
| m-single-empty-noshelf | 12 | 1 | 0 | 0 | 0 | 10 | 1 | 0 | 0 | 0 | 0 | no_candidate:1 |
| m-single-empty-noshelf | 15 | 1 | 0 | 0 | 0 | 10 | 3 | 2 | 2 | 0 | 2 | no_candidate:2 |
| m-single-empty-noshelf | 6 | 1 | 0 | 0 | 0 | 40 | 15 | 14 | 14 | 0 | 7 | - |
| m-single-empty-noshelf | 12 | 1 | 0 | 0 | 0 | 40 | 1 | 0 | 0 | 0 | 0 | no_candidate:1 |
| m-single-empty-noshelf | 15 | 1 | 0 | 0 | 0 | 40 | 1 | 0 | 0 | 0 | 0 | no_candidate:1 |
| m-single-preloaded | 6 | 1 | 0 | 3 | 0 | 20 | 1 | 0 | 0 | 0 | 0 | no_candidate:1 |
| m-single-preloaded | 9 | 1 | 0 | 3 | 0 | 20 | 1 | 0 | 0 | 0 | 0 | no_candidate:1 |
| m-single-preloaded | 12 | 1 | 0 | 3 | 0 | 20 | 1 | 0 | 0 | 0 | 0 | no_candidate:1 |
| m-single-empty-shelf | 6 | 1 | 1 | 0 | 0 | 20 | 15 | 14 | 14 | 0 | 6 | - |
| m-single-empty-shelf | 12 | 1 | 1 | 0 | 0 | 20 | 15 | 14 | 14 | 0 | 7 | - |
| m-single-empty-shelf | 15 | 1 | 1 | 0 | 0 | 20 | 5 | 4 | 4 | 0 | 3 | no_candidate:2 |

The JSON companion retains separate ranges for placed count, fill, CoG, surface variation, priority, soft-item, rotation, and displacement labels. No single proxy is treated as the competition score.
