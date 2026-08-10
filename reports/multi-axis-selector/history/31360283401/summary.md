# Online policy ablation

- episode rows: 45; paired differences use `base` as the baseline arm.

- fill_score / num_placed_items are the only official components the bundled simulator computes; cog / stability / placement / soft_item scores exist only in the official environment and are captured automatically when present (score_components). final CoM z is the local cog proxy.

## Per arm

Lower is better for the three shake columns. They are the veto in AGENT_OPERATIONS 5.05: a selection, ordering or allocation change that worsens them is not adopted on a placed gain.

`final CoM z` is retained for continuity but its direction has been falsified once against an official submission pair (it improved while official cog fell 20.7%). Do not read it as a cog proxy.

| arm | episodes | placed mean | fill mean | steps mean | shake max shift | shake peak KE | shake shifted | final CoM z | near-miss settles (5-30 deg) | surface TV |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| base | 15 | 19.533 | 21.147 | 20.533 | 0.307 | 46.737 | 4.0 | 0.708 | 3.867 | 0.031 |
| base_null | 15 | 18.867 | 21.28 | 19.867 | 0.181 | 28.143 | 3.533 | 0.708 | 3.333 | 0.03 |
| multi_axis_shadow | 15 | 18.533 | 21.283 | 19.533 | 0.214 | 39.186 | 3.533 | 0.707 | 3.267 | 0.031 |

## Full local proxy vector

No weighted total is formed. Higher is better for the two clean ratios; lower is better for shake and policy cost.

| arm | shake toppled | shifted fraction | priority clean | soft clean | included rate | valid rate | placed-safe rate | policy seconds |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| base | 0.6 | 0.222 | 0.717 | 0.943 | 1.0 | 0.467 | 0.0 | 6.421 |
| base_null | 0.133 | 0.197 | 0.767 | 0.961 | 1.0 | 0.4 | 0.0 | 6.436 |
| multi_axis_shadow | 0.667 | 0.203 | 0.8 | 0.967 | 1.0 | 0.467 | 0.0 | 6.364 |

## Terminal channels

Counts remain categorical and are not folded into a score.

| arm | channels |
|---|---|
| base | `{"slide": 2, "topple": 5, "transport_invalid": 8}` |
| base_null | `{"slide": 1, "topple": 5, "transport_invalid": 9}` |
| multi_axis_shadow | `{"slide": 3, "topple": 4, "transport_invalid": 8}` |

## Mean totals and registered development guard

| arm | development cases | dev placed total | dev fill total | suite cases | suite placed total | suite fill total |
|---|---:|---:|---:|---:|---:|---:|
| base | 5 | 97.667 | 105.736 | 5 | 97.667 | 105.736 |
| base_null | 5 | 94.334 | 106.399 | 5 | 94.334 | 106.399 |
| multi_axis_shadow | 5 | 92.667 | 106.412 | 5 | 92.667 | 106.412 |

Registered current-default development baseline: placed `88.0`, fill `114.6`. This is a historical guard; the simultaneously executed base arm is the causal comparator for this run.

## Search work

| arm | decisions | structured records | attempts total | attempts/decision | max attempts |
|---|---:|---:|---:|---:|---:|
| base | 308 | 0 | 2636529 | 8560.159 | 21908 |
| base_null | 298 | 0 | 2680729 | 8995.735 | 26657 |
| multi_axis_shadow | 293 | 285 | 2606895 | 8897.253 | 30005 |

## Cross-step incumbent telemetry

| arm | steps | carried | pool survived | static valid | static survival | would prevent fallback | validation ms/step | deadline overruns |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| base | 0 | 0 | 0 | 0 | None | 0 | None | 0 |
| base_null | 0 | 0 | 0 | 0 | None | 0 | None | 0 |
| multi_axis_shadow | 0 | 0 | 0 | 0 | None | 0 | None | 0 |

## Temporal chunk ensemble telemetry

| arm | steps | scheduled | static valid | survival | multi-origin | action consensus | action match/disagree | any action/item match | item consensus | item match/disagree | fallback rescue | generated | ms/step | survival by delay |
|---|---:|---:|---:|---:|---:|---:|---|---|---:|---|---:|---:|---:|---|
| base | 0 | 0 | 0 | None | 0 | 0 | 0/0 | 0/0 | 0 | 0/0 | 0 | 0 | None | `{}` |
| base_null | 0 | 0 | 0 | None | 0 | 0 | 0/0 | 0/0 | 0 | 0/0 | 0 | 0 | None | `{}` |
| multi_axis_shadow | 0 | 0 | 0 | None | 0 | 0 | 0/0 | 0/0 | 0 | 0/0 | 0 | 0 | None | `{}` |

## Visible-pool rollout telemetry

| arm | steps | candidates | eligible | non-degenerate | would change item | unrestricted change | within band | enforced | ms/step | max seconds |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| base | 0 | 0 | 0 | 0 | 0 | 0 | None | 0 | None | 0.0 |
| base_null | 0 | 0 | 0 | 0 | 0 | 0 | None | 0 | None | 0.0 |
| multi_axis_shadow | 0 | 0 | 0 | 0 | 0 | 0 | None | 0 | None | 0.0 |

## Multi-axis selector shadow

| arm | observed | multi-candidate | candidates | Pareto front | baseline dominated | action changes | item changes | change rate |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| base | 0 | 0 | 0 | 0 | 0 | 0 | 0 | None |
| base_null | 0 | 0 | 0 | 0 | 0 | 0 | 0 | None |
| multi_axis_shadow | 285 | 285 | 852 | 617 | 51 | 51 | 14 | 0.178947 |

### Rollout telemetry by step index

| arm | step | observed | non-degenerate | rate | would change | enforced | unrestricted change | ms/step | max seconds |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|

## Paired per-case difference vs base

| arm | case | placed diff | fill diff |
|---|---|---:|---:|
| base_null | b000-k15 | 0.0 | 0.0 |
| base_null | b000-k20 | -3.0 | 0.065 |
| base_null | b000-k40 | -1.0 | -0.677 |
| base_null | b001-k20 | 0.0 | -0.87 |
| base_null | b001-k30 | 0.667 | 2.145 |
| multi_axis_shadow | b000-k15 | 0.666 | 1.644 |
| multi_axis_shadow | b000-k20 | -3.0 | 0.065 |
| multi_axis_shadow | b000-k40 | -1.0 | -0.677 |
| multi_axis_shadow | b001-k20 | -2.333 | -2.501 |
| multi_axis_shadow | b001-k30 | 0.667 | 2.145 |
