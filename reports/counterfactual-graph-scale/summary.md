# Counterfactual graph condition matrix

- Graphs: 8
- Edges: 51
- Physical safe / failed: 47 / 4
- These synthetic scenarios measure condition coverage; their proxy scores are not mutually score-comparable.

| case | step | containers | shelves | preload | dedicated | pool | nodes | edges | safe | failed | items | terminal reasons |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| m-dual-empty | 15 | 2 | 0 | 0 | 0 | 20 | 14 | 13 | 13 | 0 | 6 | - |
| m-dual-full-stream | 12 | 2 | 1 | 0 | 1 | 40 | 15 | 14 | 14 | 0 | 4 | - |
| m-dual-preloaded-dedicated | 15 | 2 | 0 | 2 | 1 | 40 | 15 | 14 | 14 | 0 | 6 | - |
| m-dual-shelf-mixed | 15 | 2 | 1 | 0 | 0 | 20 | 5 | 6 | 2 | 4 | 4 | physical_failure:2 |
| m-single-empty-noshelf | 15 | 1 | 0 | 0 | 0 | 10 | 1 | 0 | 0 | 0 | 0 | no_candidate:1 |
| m-single-empty-noshelf | 15 | 1 | 0 | 0 | 0 | 40 | 1 | 0 | 0 | 0 | 0 | no_candidate:1 |
| m-single-preloaded | 12 | 1 | 0 | 3 | 0 | 20 | 1 | 0 | 0 | 0 | 0 | no_candidate:1 |
| m-single-empty-shelf | 15 | 1 | 1 | 0 | 0 | 20 | 5 | 4 | 4 | 0 | 3 | no_candidate:2 |

The JSON companion retains separate ranges for placed count, fill, CoG, surface variation, priority, soft-item, rotation, and displacement labels. No single proxy is treated as the competition score.
