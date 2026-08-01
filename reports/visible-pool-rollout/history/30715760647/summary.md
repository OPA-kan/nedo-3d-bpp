# Online policy ablation

- episode rows: 48; paired differences use `base` as the baseline arm.

- fill_score / num_placed_items are the only official components the bundled simulator computes; cog / stability / placement / soft_item scores exist only in the official environment and are captured automatically when present (score_components). final CoM z is the local cog proxy.

## Per arm

| arm | episodes | placed mean | fill mean | steps mean | final CoM z | near-miss settles (5-30 deg) | surface TV |
|---|---:|---:|---:|---:|---:|---:|---:|
| base | 24 | 16.583 | 20.151 | 17.583 | 0.702 | 0.917 | 0.031 |
| rollout_enforce | 24 | 16.333 | 18.459 | 17.333 | 0.669 | 0.583 | 0.029 |

## Mean totals and registered development guard

| arm | development cases | dev placed total | dev fill total | suite cases | suite placed total | suite fill total |
|---|---:|---:|---:|---:|---:|---:|
| base | 5 | 77.333 | 95.882 | 8 | 132.666 | 161.204 |
| rollout_enforce | 5 | 76.666 | 91.919 | 8 | 130.666 | 147.67 |

Registered current-default development baseline: placed `88.0`, fill `114.6`. This is a historical guard; the simultaneously executed base arm is the causal comparator for this run.

## Cross-step incumbent telemetry

| arm | steps | carried | pool survived | static valid | static survival | would prevent fallback | validation ms/step | deadline overruns |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| base | 0 | 0 | 0 | 0 | None | 0 | None | 0 |
| rollout_enforce | 0 | 0 | 0 | 0 | None | 0 | None | 0 |

## Visible-pool rollout telemetry

| arm | steps | candidates | eligible | non-degenerate | would change item | unrestricted change | within band | enforced | ms/step | max seconds |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| base | 0 | 0 | 0 | 0 | 0 | 0 | None | 0 | None | 0.0 |
| rollout_enforce | 405 | 1213 | 700 | 149 | 74 | 128 | 0.507812 | 87 | 113.429 | 0.43831 |

### Rollout telemetry by step index

| arm | step | observed | non-degenerate | rate | would change | unrestricted change | ms/step | max seconds |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| rollout_enforce | 0 | 24 | 15 | 0.625 | 9 | 9 | 273.249 | 0.43831 |
| rollout_enforce | 1 | 24 | 21 | 0.875 | 9 | 18 | 254.464 | 0.418952 |
| rollout_enforce | 2 | 24 | 24 | 1.0 | 9 | 15 | 197.78 | 0.302388 |
| rollout_enforce | 3 | 24 | 24 | 1.0 | 8 | 17 | 135.494 | 0.270843 |
| rollout_enforce | 4 | 24 | 24 | 1.0 | 9 | 18 | 99.22 | 0.188394 |
| rollout_enforce | 5 | 24 | 16 | 0.666667 | 4 | 10 | 79.256 | 0.162233 |
| rollout_enforce | 6 | 24 | 9 | 0.375 | 1 | 9 | 60.282 | 0.119983 |
| rollout_enforce | 7 | 24 | 2 | 0.083333 | 4 | 4 | 56.311 | 0.116864 |
| rollout_enforce | 8 | 24 | 3 | 0.125 | 2 | 2 | 57.336 | 0.081937 |
| rollout_enforce | 9 | 24 | 3 | 0.125 | 5 | 5 | 64.744 | 0.097769 |
| rollout_enforce | 10 | 24 | 0 | 0.0 | 3 | 3 | 66.763 | 0.088524 |
| rollout_enforce | 11 | 24 | 0 | 0.0 | 2 | 2 | 73.027 | 0.096239 |
| rollout_enforce | 12 | 19 | 0 | 0.0 | 2 | 2 | 79.313 | 0.101228 |
| rollout_enforce | 13 | 19 | 4 | 0.210526 | 0 | 3 | 99.268 | 0.218917 |
| rollout_enforce | 14 | 19 | 4 | 0.210526 | 1 | 5 | 98.057 | 0.148795 |
| rollout_enforce | 15 | 16 | 0 | 0.0 | 2 | 2 | 93.279 | 0.115127 |
| rollout_enforce | 16 | 13 | 0 | 0.0 | 1 | 1 | 99.409 | 0.132767 |
| rollout_enforce | 17 | 10 | 0 | 0.0 | 2 | 2 | 100.833 | 0.132212 |
| rollout_enforce | 18 | 5 | 0 | 0.0 | 0 | 0 | 122.009 | 0.134837 |
| rollout_enforce | 19 | 4 | 0 | 0.0 | 0 | 0 | 137.032 | 0.151032 |
| rollout_enforce | 20 | 4 | 0 | 0.0 | 0 | 0 | 145.225 | 0.162202 |
| rollout_enforce | 21 | 2 | 0 | 0.0 | 0 | 0 | 133.673 | 0.136496 |
| rollout_enforce | 22 | 2 | 0 | 0.0 | 1 | 1 | 136.207 | 0.136849 |
| rollout_enforce | 23 | 1 | 0 | 0.0 | 0 | 0 | 141.429 | 0.141429 |
| rollout_enforce | 24 | 1 | 0 | 0.0 | 0 | 0 | 147.184 | 0.147184 |
| rollout_enforce | 25 | 1 | 0 | 0.0 | 0 | 0 | 143.982 | 0.143982 |
| rollout_enforce | 26 | 1 | 0 | 0.0 | 0 | 0 | 147.855 | 0.147855 |

## Paired per-case difference vs base

| arm | case | placed diff | fill diff |
|---|---|---:|---:|
| rollout_enforce | b000-k10 | -0.667 | -3.542 |
| rollout_enforce | b000-k15 | -6.0 | -9.891 |
| rollout_enforce | b000-k20 | 1.666 | 3.503 |
| rollout_enforce | b000-k40 | 5.667 | 3.763 |
| rollout_enforce | b001-k10 | 0.667 | -3.081 |
| rollout_enforce | b001-k20 | -1.333 | 1.556 |
| rollout_enforce | b001-k30 | -0.667 | -2.894 |
| rollout_enforce | b001-k40 | -1.333 | -2.948 |
