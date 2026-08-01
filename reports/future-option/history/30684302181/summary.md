# Online policy ablation (development configurations only)

- episode rows: 10; every arm is environment-isolated. `base` means shipped defaults, `off` means the pre-risk baseline, and named arms enable only their declared experiment.

- fill_score / num_placed_items are the only official components the bundled simulator computes; cog / stability / placement / soft_item scores exist only in the official environment and are captured automatically when present (score_components). final CoM z is the local cog proxy.

## Per arm

| arm | episodes | placed mean | fill mean | steps mean | final CoM z | near-miss settles (5-30 deg) | surface TV |
|---|---:|---:|---:|---:|---:|---:|---:|
| base | 5 | 16.4 | 21.479 | 17.4 | 0.707 | 1.2 | 0.031 |
| future-option | 5 | 19.0 | 18.806 | 20.0 | 0.667 | 1.8 | 0.03 |

## Paired per-case difference vs off

| arm | case | placed diff | fill diff |
|---|---|---:|---:|

## Paired per-case difference vs shipped base

| arm | case | placed diff | fill diff |
|---|---|---:|---:|
| future-option | b000-k15 | 0.0 | -8.523 |
| future-option | b000-k20 | 11.0 | 3.731 |
| future-option | b000-k40 | 0.0 | -2.65 |
| future-option | b001-k20 | 3.0 | 3.901 |
| future-option | b001-k30 | -1.0 | -9.824 |

