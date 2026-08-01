# Online risk ablation (development configurations only)

- episode rows: 10; paired differences use `base` as the baseline arm.

- fill_score / num_placed_items are the only official components the bundled simulator computes; cog / stability / placement / soft_item scores exist only in the official environment and are captured automatically when present (score_components). final CoM z is the local cog proxy.

## Per arm

| arm | episodes | placed mean | fill mean | steps mean | final CoM z | near-miss settles (5-30 deg) | surface TV |
|---|---:|---:|---:|---:|---:|---:|---:|
| base | 5 | 16.0 | 19.599 | 17.0 | 0.696 | 0.8 | 0.031 |
| rescue | 5 | 14.8 | 17.605 | 15.8 | 0.682 | 1.4 | 0.029 |

## Paired per-case difference vs base

| arm | case | placed diff | fill diff |
|---|---|---:|---:|
| rescue | b000-k15 | 0.0 | 0.0 |
| rescue | b000-k20 | -2.0 | -4.46 |
| rescue | b000-k40 | -6.0 | -6.288 |
| rescue | b001-k20 | 2.0 | 0.779 |
| rescue | b001-k30 | 0.0 | 0.0 |
