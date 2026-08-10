# Online policy ablation

- episode rows: 60; paired differences use `base` as the baseline arm.

- fill_score / num_placed_items are the only official components the bundled simulator computes; cog / stability / placement / soft_item scores exist only in the official environment and are captured automatically when present (score_components). final CoM z is the local cog proxy.

## Per arm

Lower is better for the three shake columns. They are the veto in AGENT_OPERATIONS 5.05: a selection, ordering or allocation change that worsens them is not adopted on a placed gain.

`final CoM z` is retained for continuity but its direction has been falsified once against an official submission pair (it improved while official cog fell 20.7%). Do not read it as a cog proxy.

| arm | episodes | placed mean | fill mean | steps mean | shake max shift | shake peak KE | shake shifted | final CoM z | near-miss settles (5-30 deg) | surface TV |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| base | 15 | 19.4 | 22.151 | 20.4 | 0.323 | 54.027 | 4.467 | 0.722 | 3.2 | 0.031 |
| base_null | 15 | 17.267 | 20.427 | 18.267 | 0.317 | 50.001 | 4.533 | 0.685 | 2.0 | 0.03 |
| multi_axis_enforce | 15 | 17.333 | 20.454 | 18.333 | 0.306 | 55.459 | 4.8 | 0.685 | 2.2 | 0.031 |
| multi_axis_shadow | 15 | 17.333 | 19.921 | 18.333 | 0.303 | 49.39 | 5.933 | 0.671 | 1.8 | 0.03 |

## Full local proxy vector

No weighted total is formed. Higher is better for the two clean ratios; lower is better for shake and policy cost.

| arm | shake toppled | shifted fraction | priority clean | soft clean | included rate | valid rate | placed-safe rate | policy seconds |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| base | 0.8 | 0.242 | 0.717 | 0.953 | 1.0 | 0.4 | 0.0 | 6.425 |
| base_null | 0.933 | 0.264 | 0.767 | 0.976 | 1.0 | 0.733 | 0.0 | 6.164 |
| multi_axis_enforce | 1.333 | 0.286 | 0.917 | 1.0 | 1.0 | 0.733 | 0.0 | 6.346 |
| multi_axis_shadow | 1.0 | 0.351 | 0.85 | 0.981 | 1.0 | 0.867 | 0.0 | 6.211 |

## Terminal channels

Counts remain categorical and are not folded into a score.

| arm | channels |
|---|---|
| base | `{"slide": 1, "topple": 5, "transport_invalid": 9}` |
| base_null | `{"slide": 3, "topple": 8, "transport_invalid": 4}` |
| multi_axis_enforce | `{"slide": 6, "topple": 5, "transport_invalid": 4}` |
| multi_axis_shadow | `{"slide": 3, "topple": 10, "transport_invalid": 2}` |

## Mean totals and registered development guard

| arm | development cases | dev placed total | dev fill total | suite cases | suite placed total | suite fill total |
|---|---:|---:|---:|---:|---:|---:|
| base | 5 | 97.001 | 110.754 | 5 | 97.001 | 110.754 |
| base_null | 5 | 86.333 | 102.137 | 5 | 86.333 | 102.137 |
| multi_axis_enforce | 5 | 86.666 | 102.271 | 5 | 86.666 | 102.271 |
| multi_axis_shadow | 5 | 86.666 | 99.604 | 5 | 86.666 | 99.604 |

Registered current-default development baseline: placed `88.0`, fill `114.6`. This is a historical guard; the simultaneously executed base arm is the causal comparator for this run.

## Search work

| arm | decisions | structured records | attempts total | attempts/decision | max attempts |
|---|---:|---:|---:|---:|---:|
| base | 306 | 0 | 2603608 | 8508.523 | 21074 |
| base_null | 274 | 0 | 2351684 | 8582.788 | 19360 |
| multi_axis_enforce | 275 | 271 | 2438532 | 8867.389 | 24576 |
| multi_axis_shadow | 275 | 273 | 2205861 | 8021.313 | 16575 |

## Cross-step incumbent telemetry

| arm | steps | carried | pool survived | static valid | static survival | would prevent fallback | validation ms/step | deadline overruns |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| base | 0 | 0 | 0 | 0 | None | 0 | None | 0 |
| base_null | 0 | 0 | 0 | 0 | None | 0 | None | 0 |
| multi_axis_enforce | 0 | 0 | 0 | 0 | None | 0 | None | 0 |
| multi_axis_shadow | 0 | 0 | 0 | 0 | None | 0 | None | 0 |

## Temporal chunk ensemble telemetry

| arm | steps | scheduled | static valid | survival | multi-origin | action consensus | action match/disagree | any action/item match | item consensus | item match/disagree | fallback rescue | generated | ms/step | survival by delay |
|---|---:|---:|---:|---:|---:|---:|---|---|---:|---|---:|---:|---:|---|
| base | 0 | 0 | 0 | None | 0 | 0 | 0/0 | 0/0 | 0 | 0/0 | 0 | 0 | None | `{}` |
| base_null | 0 | 0 | 0 | None | 0 | 0 | 0/0 | 0/0 | 0 | 0/0 | 0 | 0 | None | `{}` |
| multi_axis_enforce | 0 | 0 | 0 | None | 0 | 0 | 0/0 | 0/0 | 0 | 0/0 | 0 | 0 | None | `{}` |
| multi_axis_shadow | 0 | 0 | 0 | None | 0 | 0 | 0/0 | 0/0 | 0 | 0/0 | 0 | 0 | None | `{}` |

## Visible-pool rollout telemetry

| arm | steps | candidates | eligible | non-degenerate | would change item | unrestricted change | within band | enforced | ms/step | max seconds |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| base | 0 | 0 | 0 | 0 | 0 | 0 | None | 0 | None | 0.0 |
| base_null | 0 | 0 | 0 | 0 | 0 | 0 | None | 0 | None | 0.0 |
| multi_axis_enforce | 0 | 0 | 0 | 0 | 0 | 0 | None | 0 | None | 0.0 |
| multi_axis_shadow | 0 | 0 | 0 | 0 | 0 | 0 | None | 0 | None | 0.0 |

## Multi-axis selector shadow

| arm | observed | multi-candidate | candidates | Pareto front | rank0 dominated | selected dominated | selected changes | item changes | enforced | change rate |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| base | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | None |
| base_null | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | None |
| multi_axis_enforce | 271 | 270 | 811 | 600 | 56 | 57 | 57 | 8 | 57 | 0.211111 |
| multi_axis_shadow | 273 | 270 | 813 | 578 | 40 | 40 | 40 | 9 | 0 | 0.148148 |

### Rollout telemetry by step index

| arm | step | observed | non-degenerate | rate | would change | enforced | unrestricted change | ms/step | max seconds |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|

## Paired per-case difference vs base

| arm | case | placed diff | fill diff |
|---|---|---:|---:|
| base_null | b000-k15 | -1.334 | -1.54 |
| base_null | b000-k20 | -3.334 | -2.531 |
| base_null | b000-k40 | -3.667 | -3.939 |
| base_null | b001-k20 | -3.0 | -2.752 |
| base_null | b001-k30 | 0.667 | 2.145 |
| multi_axis_enforce | b000-k15 | -1.334 | -3.546 |
| multi_axis_enforce | b000-k20 | -3.667 | -5.152 |
| multi_axis_enforce | b000-k40 | -1.0 | 2.274 |
| multi_axis_enforce | b001-k20 | -4.334 | -3.526 |
| multi_axis_enforce | b001-k30 | 0.0 | 1.467 |
| multi_axis_shadow | b000-k15 | -2.667 | -3.08 |
| multi_axis_shadow | b000-k20 | -1.334 | -0.424 |
| multi_axis_shadow | b000-k40 | -2.0 | -1.281 |
| multi_axis_shadow | b001-k20 | -4.334 | -6.365 |
| multi_axis_shadow | b001-k30 | 0.0 | 0.0 |
