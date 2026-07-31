# Online risk ablation (development configurations only)

- episode rows: 30; arms compare the submission-default baseline (off) with live mechanics rerank (RELEASE_RISK_LIVE_RERANK=1, RELEASE_RISK_P_MODEL=mech).

- fill_score / num_placed_items are the only official components the bundled simulator computes; cog / stability / placement / soft_item scores exist only in the official environment and are captured automatically when present (score_components). final CoM z is the local cog proxy.

## Per arm

| arm | episodes | placed mean | fill mean | steps mean | final CoM z mean |
|---|---:|---:|---:|---:|---:|
| mech-lam1 | 5 | 16.8 | 17.058 | 17.8 | 0.677 |
| mech-lam2 | 10 | 14.0 | 16.496 | 15.0 | 0.651 |
| mech-lam4 | 5 | 15.0 | 17.44 | 16.0 | 0.66 |
| off | 10 | 13.3 | 13.768 | 14.3 | 0.639 |

## Paired per-case difference vs off

| arm | case | placed diff | fill diff |
|---|---|---:|---:|
| mech-lam1 | b000-k15 | 3.0 | 6.274 |
| mech-lam1 | b000-k20 | 15.0 | 9.781 |
| mech-lam1 | b000-k40 | 0.0 | 0.0 |
| mech-lam1 | b001-k20 | -3.0 | -3.356 |
| mech-lam1 | b001-k30 | 2.5 | 3.751 |
| mech-lam2 | b000-k15 | 0.0 | 8.124 |
| mech-lam2 | b000-k20 | 1.0 | 5.282 |
| mech-lam2 | b000-k40 | 0.0 | -0.519 |
| mech-lam2 | b001-k20 | -2.0 | -0.304 |
| mech-lam2 | b001-k30 | 4.5 | 1.059 |
| mech-lam4 | b000-k15 | 0.0 | 8.124 |
| mech-lam4 | b000-k20 | 5.0 | 9.536 |
| mech-lam4 | b000-k40 | 1.0 | 0.787 |
| mech-lam4 | b001-k20 | -1.0 | -1.538 |
| mech-lam4 | b001-k30 | 3.5 | 1.454 |

