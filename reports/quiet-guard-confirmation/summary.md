# Online policy ablation

- episode rows: 24; paired differences use `base` as the baseline arm.

- fill_score / num_placed_items are the only official components the bundled simulator computes; cog / stability / placement / soft_item scores exist only in the official environment and are captured automatically when present (score_components). final CoM z is the local cog proxy.

## Per arm

Lower is better for the three shake columns. They are the veto in AGENT_OPERATIONS 5.05: a selection, ordering or allocation change that worsens them is not adopted on a placed gain.

`final CoM z` is retained for continuity but its direction has been falsified once against an official submission pair (it improved while official cog fell 20.7%). Do not read it as a cog proxy.

| arm | episodes | placed mean | fill mean | steps mean | shake max shift | shake peak KE | shake shifted | final CoM z | near-miss settles (5-30 deg) | surface TV |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| base | 12 | 15.333 | 17.799 | 16.333 | 0.192 | 22.763 | 5.5 | 0.666 | 1.083 | 0.027 |
| quiet_guard | 12 | 17.5 | 20.16 | 18.5 | 0.177 | 33.084 | 6.167 | 0.691 | 1.083 | 0.03 |

## Full local proxy vector

No weighted total is formed. Higher is better for the two clean ratios; lower is better for shake and policy cost.

| arm | shake toppled | shifted fraction | priority clean | soft clean | included rate | valid rate | placed-safe rate | policy seconds |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| base | 0.0 | 0.353 | 0.708 | 0.958 | 1.0 | 0.833 | 0.0 | 6.343 |
| quiet_guard | 0.083 | 0.352 | 0.764 | 1.0 | 0.917 | 0.583 | 0.0 | 6.48 |

## Terminal channels

Counts remain categorical and are not folded into a score.

| arm | channels |
|---|---|
| base | `{"slide": 3, "topple": 7, "transport_invalid": 2}` |
| quiet_guard | `{"slide": 1, "topple": 6, "transport_invalid": 5}` |

## Mean totals and registered development guard

| arm | development cases | dev placed total | dev fill total | suite cases | suite placed total | suite fill total |
|---|---:|---:|---:|---:|---:|---:|
| base | 0 | - | - | 6 | 92.0 | 106.797 |
| quiet_guard | 0 | - | - | 6 | 105.0 | 120.959 |

Registered current-default development baseline: placed `88.0`, fill `114.6`. This is a historical guard; the simultaneously executed base arm is the causal comparator for this run.

## Search work

| arm | decisions | structured records | attempts total | attempts/decision | max attempts |
|---|---:|---:|---:|---:|---:|
| base | 196 | 0 | 1654570 | 8441.684 | 22167 |
| quiet_guard | 222 | 0 | 1954989 | 8806.257 | 16074 |

## Cross-step incumbent telemetry

| arm | steps | carried | pool survived | static valid | static survival | would prevent fallback | validation ms/step | deadline overruns |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| base | 0 | 0 | 0 | 0 | None | 0 | None | 0 |
| quiet_guard | 0 | 0 | 0 | 0 | None | 0 | None | 0 |

## Temporal chunk ensemble telemetry

| arm | steps | scheduled | static valid | survival | multi-origin | action consensus | action match/disagree | any action/item match | item consensus | item match/disagree | fallback rescue | generated | ms/step | survival by delay |
|---|---:|---:|---:|---:|---:|---:|---|---|---:|---|---:|---:|---:|---|
| base | 0 | 0 | 0 | None | 0 | 0 | 0/0 | 0/0 | 0 | 0/0 | 0 | 0 | None | `{}` |
| quiet_guard | 0 | 0 | 0 | None | 0 | 0 | 0/0 | 0/0 | 0 | 0/0 | 0 | 0 | None | `{}` |

## Visible-pool rollout telemetry

| arm | steps | candidates | eligible | non-degenerate | would change item | unrestricted change | within band | enforced | ms/step | max seconds |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| base | 0 | 0 | 0 | 0 | 0 | 0 | None | 0 | None | 0.0 |
| quiet_guard | 0 | 0 | 0 | 0 | 0 | 0 | None | 0 | None | 0.0 |

## Multi-axis selector shadow

| arm | observed | multi-candidate | candidates | Pareto front | rank0 dominated | selected dominated | selected changes | item changes | enforced | change rate |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| base | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | None |
| quiet_guard | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | None |

### Rollout telemetry by step index

| arm | step | observed | non-degenerate | rate | would change | enforced | unrestricted change | ms/step | max seconds |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|

## Paired per-case difference vs base

| arm | case | placed diff | fill diff |
|---|---|---:|---:|
| quiet_guard | syn000-per00-k20 | 4.5 | 1.558 |
| quiet_guard | syn000-per01-k20 | 0.0 | 0.0 |
| quiet_guard | syn000-per02-k20 | 0.5 | 2.432 |
| quiet_guard | syn001-per00-k20 | 3.0 | 4.516 |
| quiet_guard | syn001-per01-k20 | 0.0 | 0.0 |
| quiet_guard | syn001-per02-k20 | 5.0 | 5.656 |
