# Online risk ablation (development configurations only)

- episode rows: 10; paired differences use `base` as the baseline arm.

- fill_score / num_placed_items are the only official components the bundled simulator computes; cog / stability / placement / soft_item scores exist only in the official environment and are captured automatically when present (score_components). final CoM z is the local cog proxy.

## Per arm

| arm | episodes | placed mean | fill mean | steps mean | final CoM z | near-miss settles (5-30 deg) | surface TV |
|---|---:|---:|---:|---:|---:|---:|---:|
| base | 5 | 16.2 | 20.007 | 17.2 | 0.671 | 1.8 | 0.031 |
| rollout_shadow | 5 | 16.0 | 19.741 | 17.0 | 0.672 | 1.8 | 0.031 |

## Cross-step incumbent telemetry

| arm | steps | carried | pool survived | static valid | static survival | would prevent fallback | validation ms/step | deadline overruns |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| base | 0 | 0 | 0 | 0 | None | 0 | None | 0 |
| rollout_shadow | 0 | 0 | 0 | 0 | None | 0 | None | 0 |

## Visible-pool rollout telemetry

| arm | steps | candidates | eligible | non-degenerate | would change item | ms/step | max seconds |
|---|---:|---:|---:|---:|---:|---:|---:|
| base | 0 | 0 | 0 | 0 | 0 | None | 0.0 |
| rollout_shadow | 83 | 243 | 154 | 38 | 18 | 104.846 | 0.339514 |

## Paired per-case difference vs base

| arm | case | placed diff | fill diff |
|---|---|---:|---:|
| rollout_shadow | b000-k15 | 0.0 | 0.0 |
| rollout_shadow | b000-k20 | -1.0 | -1.318 |
| rollout_shadow | b000-k40 | 0.0 | 0.0 |
| rollout_shadow | b001-k20 | 0.0 | 0.0 |
| rollout_shadow | b001-k30 | 0.0 | -0.011 |
