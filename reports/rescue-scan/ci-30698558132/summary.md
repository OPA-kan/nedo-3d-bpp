# Online risk ablation (development configurations only)

- episode rows: 10; paired differences use `base` as the baseline arm.

- fill_score / num_placed_items are the only official components the bundled simulator computes; cog / stability / placement / soft_item scores exist only in the official environment and are captured automatically when present (score_components). final CoM z is the local cog proxy.

## Per arm

| arm | episodes | placed mean | fill mean | steps mean | final CoM z | near-miss settles (5-30 deg) | surface TV |
|---|---:|---:|---:|---:|---:|---:|---:|
| base | 5 | 16.4 | 20.064 | 17.4 | 0.668 | 2.2 | 0.03 |
| rescue | 5 | 15.6 | 18.851 | 16.6 | 0.665 | 1.6 | 0.03 |

## Paired per-case difference vs base

| arm | case | placed diff | fill diff |
|---|---|---:|---:|
| rescue | b000-k15 | 0.0 | 0.0 |
| rescue | b000-k20 | -2.0 | -4.46 |
| rescue | b000-k40 | 0.0 | 0.0 |
| rescue | b001-k20 | 0.0 | 0.0 |
| rescue | b001-k30 | -2.0 | -1.602 |
