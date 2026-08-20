# Online policy ablation

- episode rows: 30; paired differences use `base` as the baseline arm.

- fill_score / num_placed_items are the only official components the bundled simulator computes; cog / stability / placement / soft_item scores exist only in the official environment and are captured automatically when present (score_components). final CoM z is the local cog proxy.

## Per arm

Lower is better for the three shake columns. They are the veto in AGENT_OPERATIONS 5.05: a selection, ordering or allocation change that worsens them is not adopted on a placed gain.

`final CoM z` is retained for continuity but its direction has been falsified once against an official submission pair (it improved while official cog fell 20.7%). Do not read it as a cog proxy.

| arm | episodes | placed mean | fill mean | steps mean | shake max shift | shake peak KE | shake shifted | final CoM z | near-miss settles (5-30 deg) | surface TV |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| base | 15 | 18.2 | 20.0 | 19.2 | 0.313 | 43.176 | 5.2 | 0.686 | 3.067 | 0.03 |
| residual_affordance_shadow | 15 | 18.733 | 19.851 | 19.733 | 0.477 | 72.539 | 5.867 | 0.69 | 3.333 | 0.03 |

## Full local proxy vector

No weighted total is formed. Higher is better for the two clean ratios; lower is better for shake and policy cost.

| arm | shake toppled | shifted fraction | priority clean | soft clean | included rate | valid rate | placed-safe rate | policy seconds |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| base | 0.867 | 0.294 | 0.783 | 0.987 | 1.0 | 0.8 | 0.0 | 6.331 |
| residual_affordance_shadow | 0.867 | 0.33 | 0.828 | 0.99 | 1.0 | 0.733 | 0.0 | 6.433 |

## Terminal channels

Counts remain categorical and are not folded into a score.

| arm | channels |
|---|---|
| base | `{"slide": 2, "topple": 10, "transport_invalid": 3}` |
| residual_affordance_shadow | `{"slide": 4, "topple": 7, "transport_invalid": 4}` |

## Mean totals and registered development guard

| arm | development cases | dev placed total | dev fill total | suite cases | suite placed total | suite fill total |
|---|---:|---:|---:|---:|---:|---:|
| base | 5 | 91.001 | 100.003 | 5 | 91.001 | 100.003 |
| residual_affordance_shadow | 5 | 93.666 | 99.256 | 5 | 93.666 | 99.256 |

Registered current-default development baseline: placed `88.0`, fill `114.6`. This is a historical guard; the simultaneously executed base arm is the causal comparator for this run.

## Search work

| arm | decisions | structured records | attempts total | attempts/decision | max attempts |
|---|---:|---:|---:|---:|---:|
| base | 288 | 0 | 2362347 | 8202.594 | 24259 |
| residual_affordance_shadow | 296 | 283 | 2666816 | 9009.514 | 19638 |

## Cross-step incumbent telemetry

| arm | steps | carried | pool survived | static valid | static survival | would prevent fallback | validation ms/step | deadline overruns |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| base | 0 | 0 | 0 | 0 | None | 0 | None | 0 |
| residual_affordance_shadow | 0 | 0 | 0 | 0 | None | 0 | None | 0 |

## Temporal chunk ensemble telemetry

| arm | steps | scheduled | static valid | survival | multi-origin | action consensus | action match/disagree | any action/item match | item consensus | item match/disagree | fallback rescue | generated | ms/step | survival by delay |
|---|---:|---:|---:|---:|---:|---:|---|---|---:|---|---:|---:|---:|---|
| base | 0 | 0 | 0 | None | 0 | 0 | 0/0 | 0/0 | 0 | 0/0 | 0 | 0 | None | `{}` |
| residual_affordance_shadow | 0 | 0 | 0 | None | 0 | 0 | 0/0 | 0/0 | 0 | 0/0 | 0 | 0 | None | `{}` |

## Visible-pool rollout telemetry

| arm | steps | candidates | eligible | non-degenerate | would change item | unrestricted change | within band | enforced | ms/step | max seconds |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| base | 0 | 0 | 0 | 0 | 0 | 0 | None | 0 | None | 0.0 |
| residual_affordance_shadow | 0 | 0 | 0 | 0 | 0 | 0 | None | 0 | None | 0.0 |

## Multi-axis selector shadow

| arm | observed | multi-candidate | candidates | Pareto front | rank0 dominated | selected dominated | selected changes | item changes | enforced | change rate |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| base | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | None |
| residual_affordance_shadow | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | None |

## Residual-affordance action shadow

| arm | observed | candidates | changes | item changes | guarded changes | guarded item changes | attr blocked | contract regressions | change rate | guarded rate | immediate delta | guarded immediate delta |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| base | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | None | None | None | None |
| residual_affordance_shadow | 292 | 871 | 129 | 21 | 126 | 18 | 3 | 3 | 0.441781 | 0.431507 | -0.016728 | -0.014755 |

### Rollout telemetry by step index

| arm | step | observed | non-degenerate | rate | would change | enforced | unrestricted change | ms/step | max seconds |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|

## Paired per-case difference vs base

| arm | case | placed diff | fill diff |
|---|---|---:|---:|
| residual_affordance_shadow | b000-k15 | 0.0 | 0.0 |
| residual_affordance_shadow | b000-k20 | 4.666 | -0.6 |
| residual_affordance_shadow | b000-k40 | -2.667 | -3.067 |
| residual_affordance_shadow | b001-k20 | 0.666 | 2.92 |
| residual_affordance_shadow | b001-k30 | 0.0 | 0.0 |
