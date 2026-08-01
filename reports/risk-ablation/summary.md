# Online risk ablation (development configurations only)

- episode rows: 61; arms compare the submission-default baseline (off) with live mechanics rerank (RELEASE_RISK_LIVE_RERANK=1, RELEASE_RISK_P_MODEL=mech).

- fill_score / num_placed_items are the only official components the bundled simulator computes; cog / stability / placement / soft_item scores exist only in the official environment and are captured automatically when present (score_components). final CoM z is the local cog proxy.

## Per arm

| arm | episodes | placed mean | fill mean | steps mean | final CoM z | near-miss settles (5-30 deg) | surface TV |
|---|---:|---:|---:|---:|---:|---:|---:|
| base | 5 | 18.4 | 18.616 | 19.4 | 0.706 | 2.6 | 0.031 |
| mech-lam1 | 11 | 18.909 | 21.077 | 19.909 | 0.728 | 1.636 | 0.032 |
| mech-lam2 | 12 | 15.667 | 17.451 | 16.667 | 0.634 | 0.833 | 0.03 |
| mech-lam4 | 7 | 18.0 | 19.903 | 19.0 | 0.653 | 0.857 | 0.035 |
| off | 16 | 15.625 | 17.589 | 16.625 | 0.679 | 1.625 | 0.029 |
| slide05 | 5 | 16.6 | 20.605 | 17.6 | 0.679 | 1.6 | 0.033 |
| slide10 | 5 | 14.0 | 18.124 | 15.0 | 0.684 | 0.6 | 0.028 |

## Paired per-case difference vs off

| arm | case | placed diff | fill diff |
|---|---|---:|---:|
| base | b000-k15 | 3.0 | 6.274 |
| base | b000-k20 | 15.0 | 9.781 |
| base | b000-k40 | 0.0 | 0.0 |
| base | b001-k20 | 5.0 | 8.526 |
| base | b001-k30 | 2.5 | -0.341 |
| mech-lam1 | b000-k10 | 0.0 | -0.428 |
| mech-lam1 | b000-k15 | 3.0 | 6.274 |
| mech-lam1 | b000-k20 | 15.0 | 9.781 |
| mech-lam1 | b000-k40 | 0.0 | 0.0 |
| mech-lam1 | b001-k10 | 2.5 | 0.539 |
| mech-lam1 | b001-k20 | -3.0 | -3.356 |
| mech-lam1 | b001-k30 | 2.5 | 3.751 |
| mech-lam1 | b001-k40 | 1.0 | 1.293 |
| mech-lam2 | b000-k10 | -2.0 | -6.274 |
| mech-lam2 | b000-k15 | 0.0 | 8.124 |
| mech-lam2 | b000-k20 | 1.0 | 5.282 |
| mech-lam2 | b000-k40 | 0.0 | -0.519 |
| mech-lam2 | b001-k20 | -2.0 | -0.304 |
| mech-lam2 | b001-k30 | 4.5 | 1.059 |
| mech-lam4 | b000-k10 | -0.5 | -2.435 |
| mech-lam4 | b000-k15 | 0.0 | 8.124 |
| mech-lam4 | b000-k20 | 5.0 | 9.536 |
| mech-lam4 | b000-k40 | 1.0 | 0.787 |
| mech-lam4 | b001-k20 | -1.0 | -1.538 |
| mech-lam4 | b001-k30 | 3.5 | 1.454 |
| slide05 | b000-k15 | 2.0 | 14.729 |
| slide05 | b000-k20 | 6.0 | 12.04 |
| slide05 | b000-k40 | 0.0 | 0.0 |
| slide05 | b001-k20 | 7.0 | 5.953 |
| slide05 | b001-k30 | 1.5 | 1.466 |
| slide10 | b000-k15 | 3.0 | 15.852 |
| slide10 | b000-k20 | 6.0 | 12.04 |
| slide10 | b000-k40 | 0.0 | 0.0 |
| slide10 | b001-k20 | -4.0 | -4.158 |
| slide10 | b001-k30 | -1.5 | -1.954 |

