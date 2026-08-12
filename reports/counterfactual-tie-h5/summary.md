# Counterfactual graph condition matrix

- Graphs: 3
- Conditions: 2
- Edges: 186
- Physical safe / failed: 186 / 0
- These synthetic scenarios measure condition coverage; their proxy scores are not mutually score-comparable.

| case | step | containers | shelves | preload | dedicated | pool | nodes | edges | safe | failed | items | terminal reasons |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| m-dual-empty | 6 | 2 | 0 | 0 | 0 | 20 | 63 | 62 | 62 | 0 | 10 | - |
| m-dual-full-stream | 6 | 2 | 1 | 0 | 1 | 40 | 63 | 62 | 62 | 0 | 7 | - |
| m-dual-full-stream | 9 | 2 | 1 | 0 | 1 | 40 | 63 | 62 | 62 | 0 | 7 | - |

The JSON companion retains separate ranges for placed count, fill, CoG, surface variation, priority, soft-item, rotation, and displacement labels. No single proxy is treated as the competition score.
