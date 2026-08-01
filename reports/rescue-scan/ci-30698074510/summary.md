# Online risk ablation (development configurations only)

- episode rows: 10; paired differences use `base` as the baseline arm.

- fill_score / num_placed_items are the only official components the bundled simulator computes; cog / stability / placement / soft_item scores exist only in the official environment and are captured automatically when present (score_components). final CoM z is the local cog proxy.

## Per arm

| arm | episodes | placed mean | fill mean | steps mean | final CoM z | near-miss settles (5-30 deg) | surface TV |
|---|---:|---:|---:|---:|---:|---:|---:|
| base | 5 | 16.6 | 20.064 | 17.6 | 0.668 | 2.0 | 0.03 |
| rescue | 5 | 15.0 | 17.396 | 16.0 | 0.662 | 1.2 | 0.031 |

## Paired per-case difference vs base

| arm | case | placed diff | fill diff |
|---|---|---:|---:|
| rescue | b000-k15 | -1.0 | -1.123 |
| rescue | b000-k20 | 2.0 | 2.116 |
| rescue | b000-k40 | -1.0 | 0.0 |
| rescue | b001-k20 | -9.0 | -9.128 |
| rescue | b001-k30 | 1.0 | -5.205 |
