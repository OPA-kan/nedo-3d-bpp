# Online policy ablation

- episode rows: 48; paired differences use `base` as the baseline arm.

- fill_score / num_placed_items are the only official components the bundled simulator computes; cog / stability / placement / soft_item scores exist only in the official environment and are captured automatically when present (score_components). final CoM z is the local cog proxy.

## Per arm

| arm | episodes | placed mean | fill mean | steps mean | final CoM z | near-miss settles (5-30 deg) | surface TV |
|---|---:|---:|---:|---:|---:|---:|---:|
| base | 24 | 16.625 | 20.264 | 17.625 | 0.704 | 1.0 | 0.032 |
| rollout_enforce | 24 | 16.375 | 19.221 | 17.375 | 0.692 | 0.333 | 0.03 |

## Mean totals and registered development guard

| arm | development cases | dev placed total | dev fill total | suite cases | suite placed total | suite fill total |
|---|---:|---:|---:|---:|---:|---:|
| base | 5 | 77.332 | 96.101 | 8 | 132.999 | 162.112 |
| rollout_enforce | 5 | 76.667 | 90.953 | 8 | 131.001 | 153.764 |

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
| rollout_enforce | 406 | 1214 | 701 | 147 | 73 | 122 | 0.491803 | 66 | 111.38 | 0.420208 |

### Rollout telemetry by step index

| arm | step | observed | non-degenerate | rate | would change | enforced | unrestricted change | ms/step | max seconds |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| rollout_enforce | 0 | 24 | 15 | 0.625 | 9 | 12 | 9 | 266.04 | 0.395716 |
| rollout_enforce | 1 | 24 | 21 | 0.875 | 9 | 9 | 18 | 252.589 | 0.420208 |
| rollout_enforce | 2 | 24 | 24 | 1.0 | 9 | 15 | 15 | 200.245 | 0.319779 |
| rollout_enforce | 3 | 24 | 24 | 1.0 | 11 | 11 | 20 | 136.559 | 0.244925 |
| rollout_enforce | 4 | 24 | 24 | 1.0 | 11 | 11 | 16 | 105.996 | 0.191618 |
| rollout_enforce | 5 | 24 | 16 | 0.666667 | 5 | 5 | 10 | 74.554 | 0.156204 |
| rollout_enforce | 6 | 24 | 7 | 0.291667 | 0 | 0 | 7 | 55.681 | 0.109041 |
| rollout_enforce | 7 | 24 | 1 | 0.041667 | 2 | 0 | 3 | 51.652 | 0.078493 |
| rollout_enforce | 8 | 24 | 3 | 0.125 | 0 | 0 | 0 | 56.416 | 0.073782 |
| rollout_enforce | 9 | 24 | 3 | 0.125 | 3 | 3 | 3 | 63.057 | 0.097158 |
| rollout_enforce | 10 | 24 | 0 | 0.0 | 4 | 0 | 4 | 65.071 | 0.081216 |
| rollout_enforce | 11 | 24 | 0 | 0.0 | 2 | 0 | 2 | 71.826 | 0.090385 |
| rollout_enforce | 12 | 21 | 0 | 0.0 | 0 | 0 | 0 | 75.892 | 0.097396 |
| rollout_enforce | 13 | 21 | 5 | 0.238095 | 0 | 0 | 3 | 98.831 | 0.207222 |
| rollout_enforce | 14 | 21 | 4 | 0.190476 | 2 | 0 | 6 | 98.663 | 0.142551 |
| rollout_enforce | 15 | 16 | 0 | 0.0 | 1 | 0 | 1 | 88.698 | 0.119758 |
| rollout_enforce | 16 | 11 | 0 | 0.0 | 2 | 0 | 2 | 102.988 | 0.133878 |
| rollout_enforce | 17 | 10 | 0 | 0.0 | 3 | 0 | 3 | 102.096 | 0.135393 |
| rollout_enforce | 18 | 4 | 0 | 0.0 | 0 | 0 | 0 | 115.639 | 0.130709 |
| rollout_enforce | 19 | 3 | 0 | 0.0 | 0 | 0 | 0 | 123.895 | 0.129911 |
| rollout_enforce | 20 | 3 | 0 | 0.0 | 0 | 0 | 0 | 129.619 | 0.135702 |
| rollout_enforce | 21 | 3 | 0 | 0.0 | 0 | 0 | 0 | 135.407 | 0.142289 |
| rollout_enforce | 22 | 3 | 0 | 0.0 | 0 | 0 | 0 | 136.232 | 0.139584 |
| rollout_enforce | 23 | 2 | 0 | 0.0 | 0 | 0 | 0 | 137.885 | 0.138432 |

## Paired per-case difference vs base

| arm | case | placed diff | fill diff |
|---|---|---:|---:|
| rollout_enforce | b000-k10 | 0.334 | 0.995 |
| rollout_enforce | b000-k15 | -6.0 | -9.891 |
| rollout_enforce | b000-k20 | 1.334 | 2.786 |
| rollout_enforce | b000-k40 | 5.667 | 3.763 |
| rollout_enforce | b001-k10 | 0.0 | -1.029 |
| rollout_enforce | b001-k20 | -2.0 | 0.874 |
| rollout_enforce | b001-k30 | 0.334 | -2.68 |
| rollout_enforce | b001-k40 | -1.667 | -3.166 |
