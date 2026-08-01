# Online risk ablation (development configurations only)

- episode rows: 10; paired differences use `base` as the baseline arm.

- fill_score / num_placed_items are the only official components the bundled simulator computes; cog / stability / placement / soft_item scores exist only in the official environment and are captured automatically when present (score_components). final CoM z is the local cog proxy.

## Per arm

| arm | episodes | placed mean | fill mean | steps mean | final CoM z | near-miss settles (5-30 deg) | surface TV |
|---|---:|---:|---:|---:|---:|---:|---:|
| base | 5 | 14.0 | 17.677 | 15.0 | 0.666 | 1.0 | 0.027 |
| cross_step_shadow | 5 | 14.2 | 17.883 | 15.2 | 0.678 | 0.6 | 0.028 |

## Cross-step incumbent telemetry

| arm | steps | carried | pool survived | static valid | static survival | would prevent fallback | validation ms/step | deadline overruns |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| base | 0 | 0 | 0 | 0 | None | 0 | None | 0 |
| cross_step_shadow | 76 | 1603 | 1603 | 702 | 0.437929 | 0 | 37.684 | 1 |

## Paired per-case difference vs base

| arm | case | placed diff | fill diff |
|---|---|---:|---:|
| cross_step_shadow | b000-k15 | 0.0 | 0.0 |
| cross_step_shadow | b000-k20 | 3.0 | 2.635 |
| cross_step_shadow | b000-k40 | 0.0 | 0.0 |
| cross_step_shadow | b001-k20 | 0.0 | 0.0 |
| cross_step_shadow | b001-k30 | -2.0 | -1.602 |
