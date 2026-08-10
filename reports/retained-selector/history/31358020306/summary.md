# Online policy ablation

- episode rows: 45; paired differences use `base` as the baseline arm.

- fill_score / num_placed_items are the only official components the bundled simulator computes; cog / stability / placement / soft_item scores exist only in the official environment and are captured automatically when present (score_components). final CoM z is the local cog proxy.

## Per arm

Lower is better for the three shake columns. They are the veto in AGENT_OPERATIONS 5.05: a selection, ordering or allocation change that worsens them is not adopted on a placed gain.

`final CoM z` is retained for continuity but its direction has been falsified once against an official submission pair (it improved while official cog fell 20.7%). Do not read it as a cog proxy.

| arm | episodes | placed mean | fill mean | steps mean | shake max shift | shake peak KE | shake shifted | final CoM z | near-miss settles (5-30 deg) | surface TV |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| base | 15 | 17.8 | 21.099 | 18.8 | 0.345 | 48.101 | 6.6 | 0.687 | 2.067 | 0.031 |
| base_null | 15 | 17.933 | 20.245 | 18.933 | 0.193 | 38.281 | 2.867 | 0.695 | 3.067 | 0.03 |
| structured_retained | 15 | 18.067 | 20.582 | 19.067 | 0.348 | 63.779 | 5.533 | 0.685 | 2.733 | 0.03 |

## Full local proxy vector

No weighted total is formed. Higher is better for the two clean ratios; lower is better for shake and policy cost.

| arm | shake toppled | shifted fraction | priority clean | soft clean | included rate | valid rate | placed-safe rate | policy seconds |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| base | 1.067 | 0.378 | 0.833 | 1.0 | 1.0 | 0.733 | 0.0 | 6.224 |
| base_null | 0.667 | 0.166 | 0.733 | 0.962 | 1.0 | 0.533 | 0.0 | 6.285 |
| structured_retained | 1.6 | 0.322 | 0.833 | 0.97 | 1.0 | 0.8 | 0.0 | 6.158 |

## Terminal channels

Counts remain categorical and are not folded into a score.

| arm | channels |
|---|---|
| base | `{"slide": 2, "topple": 9, "transport_invalid": 4}` |
| base_null | `{"slide": 2, "topple": 6, "transport_invalid": 7}` |
| structured_retained | `{"slide": 4, "topple": 8, "transport_invalid": 3}` |

## Mean totals and registered development guard

| arm | development cases | dev placed total | dev fill total | suite cases | suite placed total | suite fill total |
|---|---:|---:|---:|---:|---:|---:|
| base | 5 | 89.0 | 105.497 | 5 | 89.0 | 105.497 |
| base_null | 5 | 89.666 | 101.224 | 5 | 89.666 | 101.224 |
| structured_retained | 5 | 90.333 | 102.911 | 5 | 90.333 | 102.911 |

Registered current-default development baseline: placed `88.0`, fill `114.6`. This is a historical guard; the simultaneously executed base arm is the causal comparator for this run.

## Search work

| arm | decisions | structured records | attempts total | attempts/decision | max attempts |
|---|---:|---:|---:|---:|---:|
| base | 282 | 0 | 2338271 | 8291.741 | 15966 |
| base_null | 284 | 0 | 2365322 | 8328.599 | 16710 |
| structured_retained | 286 | 283 | 2321293 | 8116.409 | 18712 |

## Cross-step incumbent telemetry

| arm | steps | carried | pool survived | static valid | static survival | would prevent fallback | validation ms/step | deadline overruns |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| base | 0 | 0 | 0 | 0 | None | 0 | None | 0 |
| base_null | 0 | 0 | 0 | 0 | None | 0 | None | 0 |
| structured_retained | 0 | 0 | 0 | 0 | None | 0 | None | 0 |

## Temporal chunk ensemble telemetry

| arm | steps | scheduled | static valid | survival | multi-origin | action consensus | action match/disagree | any action/item match | item consensus | item match/disagree | fallback rescue | generated | ms/step | survival by delay |
|---|---:|---:|---:|---:|---:|---:|---|---|---:|---|---:|---:|---:|---|
| base | 0 | 0 | 0 | None | 0 | 0 | 0/0 | 0/0 | 0 | 0/0 | 0 | 0 | None | `{}` |
| base_null | 0 | 0 | 0 | None | 0 | 0 | 0/0 | 0/0 | 0 | 0/0 | 0 | 0 | None | `{}` |
| structured_retained | 0 | 0 | 0 | None | 0 | 0 | 0/0 | 0/0 | 0 | 0/0 | 0 | 0 | None | `{}` |

## Visible-pool rollout telemetry

| arm | steps | candidates | eligible | non-degenerate | would change item | unrestricted change | within band | enforced | ms/step | max seconds |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| base | 0 | 0 | 0 | 0 | 0 | 0 | None | 0 | None | 0.0 |
| base_null | 0 | 0 | 0 | 0 | 0 | 0 | None | 0 | None | 0.0 |
| structured_retained | 0 | 0 | 0 | 0 | 0 | 0 | None | 0 | None | 0.0 |

### Rollout telemetry by step index

| arm | step | observed | non-degenerate | rate | would change | enforced | unrestricted change | ms/step | max seconds |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|

## Paired per-case difference vs base

| arm | case | placed diff | fill diff |
|---|---|---:|---:|
| base_null | b000-k15 | 1.333 | 1.54 |
| base_null | b000-k20 | -2.0 | -6.686 |
| base_null | b000-k40 | 1.333 | 0.279 |
| base_null | b001-k20 | 0.0 | 0.594 |
| base_null | b001-k30 | 0.0 | 0.0 |
| structured_retained | b000-k15 | -1.334 | -1.54 |
| structured_retained | b000-k20 | 1.667 | -3.26 |
| structured_retained | b000-k40 | 1.0 | 0.75 |
| structured_retained | b001-k20 | 0.0 | 1.464 |
| structured_retained | b001-k30 | 0.0 | 0.0 |
