# Online policy ablation

- episode rows: 36; paired differences use `base` as the baseline arm.

- fill_score / num_placed_items are the only official components the bundled simulator computes; cog / stability / placement / soft_item scores exist only in the official environment and are captured automatically when present (score_components). final CoM z is the local cog proxy.

## Per arm

| arm | episodes | placed mean | fill mean | steps mean | final CoM z | near-miss settles (5-30 deg) | surface TV |
|---|---:|---:|---:|---:|---:|---:|---:|
| base | 10 | 17.0 | 21.796 | 18.0 | 0.717 | 0.5 | 0.034 |
| board_k3 | 15 | 18.467 | 21.458 | 19.467 | 0.69 | 1.667 | 0.034 |
| board_k8 | 6 | 17.833 | 21.291 | 18.833 | 0.711 | 1.667 | 0.032 |
| topk8 | 5 | 17.2 | 22.667 | 18.2 | 0.722 | 0.4 | 0.035 |

## Mean totals and registered development guard

| arm | development cases | dev placed total | dev fill total | suite cases | suite placed total | suite fill total |
|---|---:|---:|---:|---:|---:|---:|
| base | 5 | 85.0 | 108.982 | 5 | 85.0 | 108.982 |
| board_k3 | 5 | 92.334 | 107.292 | 5 | 92.334 | 107.292 |
| board_k8 | 5 | 88.0 | 105.006 | 5 | 88.0 | 105.006 |
| topk8 | 5 | 86.0 | 113.334 | 5 | 86.0 | 113.334 |

Registered current-default development baseline: placed `88.0`, fill `114.6`. This is a historical guard; the simultaneously executed base arm is the causal comparator for this run.

## Cross-step incumbent telemetry

| arm | steps | carried | pool survived | static valid | static survival | would prevent fallback | validation ms/step | deadline overruns |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| base | 0 | 0 | 0 | 0 | None | 0 | None | 0 |
| board_k3 | 0 | 0 | 0 | 0 | None | 0 | None | 0 |
| board_k8 | 0 | 0 | 0 | 0 | None | 0 | None | 0 |
| topk8 | 0 | 0 | 0 | 0 | None | 0 | None | 0 |

## Visible-pool rollout telemetry

| arm | steps | candidates | eligible | non-degenerate | would change item | unrestricted change | within band | enforced | ms/step | max seconds |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| base | 0 | 0 | 0 | 0 | 0 | 0 | None | 0 | None | 0.0 |
| board_k3 | 0 | 0 | 0 | 0 | 0 | 0 | None | 0 | None | 0.0 |
| board_k8 | 0 | 0 | 0 | 0 | 0 | 0 | None | 0 | None | 0.0 |
| topk8 | 0 | 0 | 0 | 0 | 0 | 0 | None | 0 | None | 0.0 |

### Rollout telemetry by step index

| arm | step | observed | non-degenerate | rate | would change | enforced | unrestricted change | ms/step | max seconds |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|

## Paired per-case difference vs base

| arm | case | placed diff | fill diff |
|---|---|---:|---:|
| board_k3 | b000-k15 | 1.667 | -0.554 |
| board_k3 | b000-k20 | 1.5 | 5.01 |
| board_k3 | b000-k40 | 4.5 | 5.108 |
| board_k3 | b001-k20 | -4.333 | -6.839 |
| board_k3 | b001-k30 | 4.0 | -4.415 |
| board_k8 | b000-k15 | 2.0 | -0.378 |
| board_k8 | b000-k20 | 0.5 | 0.124 |
| board_k8 | b000-k40 | 4.5 | 5.108 |
| board_k8 | b001-k20 | -5.0 | -7.502 |
| board_k8 | b001-k30 | 1.0 | -1.328 |
| topk8 | b000-k15 | 0.0 | 0.0 |
| topk8 | b000-k20 | 1.5 | 5.01 |
| topk8 | b000-k40 | -0.5 | -0.658 |
| topk8 | b001-k20 | 0.0 | 0.0 |
| topk8 | b001-k30 | 0.0 | 0.0 |
