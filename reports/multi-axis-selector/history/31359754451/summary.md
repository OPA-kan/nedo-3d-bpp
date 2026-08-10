# Online policy ablation

- episode rows: 45; paired differences use `base` as the baseline arm.

- fill_score / num_placed_items are the only official components the bundled simulator computes; cog / stability / placement / soft_item scores exist only in the official environment and are captured automatically when present (score_components). final CoM z is the local cog proxy.

## Per arm

Lower is better for the three shake columns. They are the veto in AGENT_OPERATIONS 5.05: a selection, ordering or allocation change that worsens them is not adopted on a placed gain.

`final CoM z` is retained for continuity but its direction has been falsified once against an official submission pair (it improved while official cog fell 20.7%). Do not read it as a cog proxy.

| arm | episodes | placed mean | fill mean | steps mean | shake max shift | shake peak KE | shake shifted | final CoM z | near-miss settles (5-30 deg) | surface TV |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| base | 15 | 17.733 | 20.885 | 18.733 | 0.256 | 42.96 | 4.4 | 0.694 | 2.333 | 0.03 |
| base_null | 15 | 17.867 | 20.868 | 18.867 | 0.222 | 45.126 | 4.2 | 0.69 | 3.133 | 0.03 |
| multi_axis_shadow | 15 | 17.133 | 19.573 | 18.133 | 0.255 | 48.02 | 5.4 | 0.663 | 2.133 | 0.03 |

## Full local proxy vector

No weighted total is formed. Higher is better for the two clean ratios; lower is better for shake and policy cost.

| arm | shake toppled | shifted fraction | priority clean | soft clean | included rate | valid rate | placed-safe rate | policy seconds |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| base | 0.733 | 0.258 | 0.833 | 0.973 | 1.0 | 0.6 | 0.0 | 6.291 |
| base_null | 0.933 | 0.25 | 0.8 | 0.955 | 1.0 | 0.667 | 0.0 | 6.293 |
| multi_axis_shadow | 1.2 | 0.33 | 0.883 | 0.989 | 1.0 | 1.0 | 0.0 | 5.977 |

## Terminal channels

Counts remain categorical and are not folded into a score.

| arm | channels |
|---|---|
| base | `{"slide": 3, "topple": 6, "transport_invalid": 6}` |
| base_null | `{"slide": 6, "topple": 4, "transport_invalid": 5}` |
| multi_axis_shadow | `{"slide": 4, "topple": 11}` |

## Mean totals and registered development guard

| arm | development cases | dev placed total | dev fill total | suite cases | suite placed total | suite fill total |
|---|---:|---:|---:|---:|---:|---:|
| base | 5 | 88.667 | 104.424 | 5 | 88.667 | 104.424 |
| base_null | 5 | 89.333 | 104.341 | 5 | 89.333 | 104.341 |
| multi_axis_shadow | 5 | 85.666 | 97.863 | 5 | 85.666 | 97.863 |

Registered current-default development baseline: placed `88.0`, fill `114.6`. This is a historical guard; the simultaneously executed base arm is the causal comparator for this run.

## Search work

| arm | decisions | structured records | attempts total | attempts/decision | max attempts |
|---|---:|---:|---:|---:|---:|
| base | 281 | 0 | 2533589 | 9016.331 | 26173 |
| base_null | 283 | 0 | 2411306 | 8520.516 | 27914 |
| multi_axis_shadow | 272 | 272 | 2281053 | 8386.224 | 29693 |

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
| multi_axis_shadow | 272 | 270 | 812 | 582 | 43 | 43 | 11 | 0.159259 |

### Rollout telemetry by step index

| arm | step | observed | non-degenerate | rate | would change | enforced | unrestricted change | ms/step | max seconds |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|

## Paired per-case difference vs base

| arm | case | placed diff | fill diff |
|---|---|---:|---:|
| base_null | b000-k15 | 1.334 | 1.54 |
| base_null | b000-k20 | -0.667 | -0.339 |
| base_null | b000-k40 | 0.0 | 0.0 |
| base_null | b001-k20 | 0.333 | 0.698 |
| base_null | b001-k30 | -0.334 | -1.982 |
| multi_axis_shadow | b000-k15 | -0.666 | 0.105 |
| multi_axis_shadow | b000-k20 | 1.666 | 0.119 |
| multi_axis_shadow | b000-k40 | -3.0 | -2.398 |
| multi_axis_shadow | b001-k20 | -0.334 | -0.423 |
| multi_axis_shadow | b001-k30 | -0.667 | -3.964 |
