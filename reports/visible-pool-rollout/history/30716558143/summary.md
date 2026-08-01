# Online policy ablation

- episode rows: 48; paired differences use `base` as the baseline arm.

- fill_score / num_placed_items are the only official components the bundled simulator computes; cog / stability / placement / soft_item scores exist only in the official environment and are captured automatically when present (score_components). final CoM z is the local cog proxy.

## Per arm

| arm | episodes | placed mean | fill mean | steps mean | final CoM z | near-miss settles (5-30 deg) | surface TV |
|---|---:|---:|---:|---:|---:|---:|---:|
| base | 24 | 17.208 | 20.985 | 18.208 | 0.713 | 1.0 | 0.032 |
| rollout_enforce | 24 | 16.375 | 18.957 | 17.375 | 0.691 | 0.417 | 0.029 |

## Mean totals and registered development guard

| arm | development cases | dev placed total | dev fill total | suite cases | suite placed total | suite fill total |
|---|---:|---:|---:|---:|---:|---:|
| base | 5 | 84.0 | 104.239 | 8 | 137.667 | 167.881 |
| rollout_enforce | 5 | 79.333 | 95.233 | 8 | 131.0 | 151.656 |

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
| rollout_enforce | 406 | 1218 | 707 | 142 | 79 | 124 | 0.540323 | 54 | 111.054 | 0.617579 |

### Rollout telemetry by step index

| arm | step | observed | non-degenerate | rate | would change | enforced | unrestricted change | ms/step | max seconds |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| rollout_enforce | 0 | 24 | 15 | 0.625 | 9 | 9 | 9 | 264.786 | 0.412702 |
| rollout_enforce | 1 | 24 | 21 | 0.875 | 9 | 9 | 18 | 259.046 | 0.617579 |
| rollout_enforce | 2 | 24 | 24 | 1.0 | 9 | 15 | 15 | 196.904 | 0.299743 |
| rollout_enforce | 3 | 24 | 24 | 1.0 | 11 | 10 | 19 | 140.773 | 0.272992 |
| rollout_enforce | 4 | 24 | 24 | 1.0 | 8 | 6 | 15 | 102.359 | 0.167848 |
| rollout_enforce | 5 | 24 | 16 | 0.666667 | 5 | 5 | 10 | 75.246 | 0.157664 |
| rollout_enforce | 6 | 24 | 7 | 0.291667 | 0 | 0 | 5 | 57.149 | 0.121859 |
| rollout_enforce | 7 | 24 | 3 | 0.125 | 0 | 0 | 3 | 54.661 | 0.085139 |
| rollout_enforce | 8 | 24 | 3 | 0.125 | 1 | 0 | 1 | 58.24 | 0.081986 |
| rollout_enforce | 9 | 24 | 3 | 0.125 | 4 | 0 | 4 | 65.075 | 0.097569 |
| rollout_enforce | 10 | 24 | 0 | 0.0 | 4 | 0 | 4 | 68.06 | 0.089973 |
| rollout_enforce | 11 | 24 | 0 | 0.0 | 5 | 0 | 5 | 74.815 | 0.099485 |
| rollout_enforce | 12 | 20 | 0 | 0.0 | 0 | 0 | 0 | 79.222 | 0.103937 |
| rollout_enforce | 13 | 20 | 1 | 0.05 | 1 | 0 | 2 | 86.81 | 0.115929 |
| rollout_enforce | 14 | 19 | 1 | 0.052632 | 3 | 0 | 4 | 89.737 | 0.12328 |
| rollout_enforce | 15 | 16 | 0 | 0.0 | 1 | 0 | 1 | 89.952 | 0.120766 |
| rollout_enforce | 16 | 11 | 0 | 0.0 | 3 | 0 | 3 | 95.339 | 0.111463 |
| rollout_enforce | 17 | 9 | 0 | 0.0 | 6 | 0 | 6 | 99.427 | 0.121146 |
| rollout_enforce | 18 | 5 | 0 | 0.0 | 0 | 0 | 0 | 114.386 | 0.127664 |
| rollout_enforce | 19 | 4 | 0 | 0.0 | 0 | 0 | 0 | 112.387 | 0.128881 |
| rollout_enforce | 20 | 4 | 0 | 0.0 | 0 | 0 | 0 | 119.296 | 0.136315 |
| rollout_enforce | 21 | 4 | 0 | 0.0 | 0 | 0 | 0 | 120.763 | 0.138662 |
| rollout_enforce | 22 | 4 | 0 | 0.0 | 0 | 0 | 0 | 126.798 | 0.140048 |
| rollout_enforce | 23 | 1 | 0 | 0.0 | 0 | 0 | 0 | 89.95 | 0.08995 |
| rollout_enforce | 24 | 1 | 0 | 0.0 | 0 | 0 | 0 | 89.766 | 0.089766 |

## Paired per-case difference vs base

| arm | case | placed diff | fill diff |
|---|---|---:|---:|
| rollout_enforce | b000-k10 | -0.667 | -2.955 |
| rollout_enforce | b000-k15 | -6.0 | -9.891 |
| rollout_enforce | b000-k20 | 0.666 | 0.307 |
| rollout_enforce | b000-k40 | 2.667 | 1.395 |
| rollout_enforce | b001-k10 | -0.333 | -1.636 |
| rollout_enforce | b001-k20 | -2.666 | 0.008 |
| rollout_enforce | b001-k30 | 0.666 | -0.825 |
| rollout_enforce | b001-k40 | -1.0 | -2.628 |
