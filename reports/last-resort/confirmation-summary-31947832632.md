# Online policy ablation

- episode rows: 24; paired differences use `base` as the baseline arm.

- fill_score / num_placed_items are the only official components the bundled simulator computes; cog / stability / placement / soft_item scores exist only in the official environment and are captured automatically when present (score_components). final CoM z is the local cog proxy.

## Per arm

Lower is better for the three shake columns. They are the veto in AGENT_OPERATIONS 5.05: a selection, ordering or allocation change that worsens them is not adopted on a placed gain.

`final CoM z` is retained for continuity but its direction has been falsified once against an official submission pair (it improved while official cog fell 20.7%). Do not read it as a cog proxy.

| arm | episodes | placed mean | fill mean | steps mean | shake max shift | shake peak KE | shake shifted | final CoM z | near-miss settles (5-30 deg) | surface TV |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| base | 12 | 17.167 | 20.226 | 18.167 | 0.131 | 20.084 | 6.417 | 0.68 | 0.833 | 0.029 |
| last_resort | 12 | 16.667 | 19.471 | 17.667 | 0.161 | 18.515 | 6.083 | 0.675 | 0.75 | 0.029 |

## Full local proxy vector

No weighted total is formed. Higher is better for the two clean ratios; lower is better for shake and policy cost.

| arm | shake toppled | shifted fraction | priority clean | soft clean | included rate | valid rate | placed-safe rate | policy seconds |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| base | 0.0 | 0.376 | 0.917 | 1.0 | 1.0 | 0.5 | 0.0 | 6.393 |
| last_resort | 0.0 | 0.37 | 0.875 | 1.0 | 1.0 | 0.583 | 0.0 | 6.954 |

## Terminal channels

Counts remain categorical and are not folded into a score.

| arm | channels |
|---|---|
| base | `{"slide": 1, "topple": 5, "transport_invalid": 6}` |
| last_resort | `{"slide": 1, "topple": 6, "transport_invalid": 5}` |

## Mean totals and registered development guard

| arm | development cases | dev placed total | dev fill total | suite cases | suite placed total | suite fill total |
|---|---:|---:|---:|---:|---:|---:|
| base | 0 | - | - | 6 | 103.0 | 121.358 |
| last_resort | 0 | - | - | 6 | 100.0 | 116.829 |

Registered current-default development baseline: placed `88.0`, fill `114.6`. This is a historical guard; the simultaneously executed base arm is the causal comparator for this run.

## Search work

| arm | decisions | structured records | attempts total | attempts/decision | max attempts |
|---|---:|---:|---:|---:|---:|
| base | 218 | 0 | 1737697 | 7971.087 | 15896 |
| last_resort | 207 | 0 | 1700790 | 8216.377 | 16063 |

## Cross-step incumbent telemetry

| arm | steps | carried | pool survived | static valid | static survival | would prevent fallback | validation ms/step | deadline overruns |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| base | 0 | 0 | 0 | 0 | None | 0 | None | 0 |
| last_resort | 0 | 0 | 0 | 0 | None | 0 | None | 0 |

## Temporal chunk ensemble telemetry

| arm | steps | scheduled | static valid | survival | multi-origin | action consensus | action match/disagree | any action/item match | item consensus | item match/disagree | fallback rescue | generated | ms/step | survival by delay |
|---|---:|---:|---:|---:|---:|---:|---|---|---:|---|---:|---:|---:|---|
| base | 0 | 0 | 0 | None | 0 | 0 | 0/0 | 0/0 | 0 | 0/0 | 0 | 0 | None | `{}` |
| last_resort | 0 | 0 | 0 | None | 0 | 0 | 0/0 | 0/0 | 0 | 0/0 | 0 | 0 | None | `{}` |

## Visible-pool rollout telemetry

| arm | steps | candidates | eligible | non-degenerate | would change item | unrestricted change | within band | enforced | ms/step | max seconds |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| base | 0 | 0 | 0 | 0 | 0 | 0 | None | 0 | None | 0.0 |
| last_resort | 0 | 0 | 0 | 0 | 0 | 0 | None | 0 | None | 0.0 |

## Multi-axis selector shadow

| arm | observed | multi-candidate | candidates | Pareto front | rank0 dominated | selected dominated | selected changes | item changes | enforced | change rate |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| base | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | None |
| last_resort | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | None |

### Rollout telemetry by step index

| arm | step | observed | non-degenerate | rate | would change | enforced | unrestricted change | ms/step | max seconds |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|

## Paired per-case difference vs base

| arm | case | placed diff | fill diff |
|---|---|---:|---:|
| last_resort | syn000-per00-k20 | 0.0 | 0.0 |
| last_resort | syn000-per01-k20 | 0.0 | 0.0 |
| last_resort | syn000-per02-k20 | 0.0 | 0.0 |
| last_resort | syn001-per00-k20 | 0.0 | 0.0 |
| last_resort | syn001-per01-k20 | 0.0 | 0.0 |
| last_resort | syn001-per02-k20 | -3.0 | -4.529 |
