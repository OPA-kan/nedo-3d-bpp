# Online policy ablation

- episode rows: 30; paired differences use `base` as the baseline arm.

- fill_score / num_placed_items are the only official components the bundled simulator computes; cog / stability / placement / soft_item scores exist only in the official environment and are captured automatically when present (score_components). final CoM z is the local cog proxy.

## Per arm

Lower is better for the three shake columns. They are the veto in AGENT_OPERATIONS 5.05: a selection, ordering or allocation change that worsens them is not adopted on a placed gain.

`final CoM z` is retained for continuity but its direction has been falsified once against an official submission pair (it improved while official cog fell 20.7%). Do not read it as a cog proxy.

| arm | episodes | placed mean | fill mean | steps mean | shake max shift | shake peak KE | shake shifted | final CoM z | near-miss settles (5-30 deg) | surface TV |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| base | 15 | 18.6 | 20.937 | 19.6 | 0.23 | 30.33 | 5.067 | 0.704 | 3.2 | 0.031 |
| residual_affordance_shadow | 15 | 18.267 | 20.437 | 19.267 | 0.292 | 37.66 | 6.533 | 0.695 | 2.467 | 0.031 |

## Same-call decision-invariance negative control

| observed | incumbent unchanged | portfolio unchanged | missing | guarded regressions | passed |
|---:|---:|---:|---:|---:|---|
| 284 | 284 | 284 | 0 | 0 | True |

## Cross-process action-sequence diagnostic

Exact hashes are retained as a nondeterminism diagnostic, not used as the same-call decision-invariance gate.

| paired | matched | mismatched | missing | passed |
|---:|---:|---:|---:|---|
| 15 | 1 | 14 | 0 | False |

## Full local proxy vector

No weighted total is formed. Higher is better for the two clean ratios; lower is better for shake and policy cost.

| arm | shake toppled | shifted fraction | priority clean | soft clean | included rate | valid rate | placed-safe rate | policy seconds |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| base | 0.733 | 0.278 | 0.794 | 0.973 | 1.0 | 0.467 | 0.0 | 6.421 |
| residual_affordance_shadow | 0.867 | 0.358 | 0.778 | 0.987 | 1.0 | 0.667 | 0.0 | 6.358 |

## Terminal channels

Counts remain categorical and are not folded into a score.

| arm | channels |
|---|---|
| base | `{"slide": 3, "topple": 4, "transport_invalid": 8}` |
| residual_affordance_shadow | `{"slide": 3, "topple": 7, "transport_invalid": 5}` |

## Mean totals and registered development guard

| arm | development cases | dev placed total | dev fill total | suite cases | suite placed total | suite fill total |
|---|---:|---:|---:|---:|---:|---:|
| base | 5 | 93.0 | 104.682 | 5 | 93.0 | 104.682 |
| residual_affordance_shadow | 5 | 91.333 | 102.183 | 5 | 91.333 | 102.183 |

Registered current-default development baseline: placed `88.0`, fill `114.6`. This is a historical guard; the simultaneously executed base arm is the causal comparator for this run.

## Search work

| arm | decisions | structured records | attempts total | attempts/decision | max attempts |
|---|---:|---:|---:|---:|---:|
| base | 294 | 0 | 2597431 | 8834.799 | 25231 |
| residual_affordance_shadow | 289 | 0 | 2516075 | 8706.142 | 19831 |

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
| residual_affordance_shadow | 284 | 847 | 135 | 27 | 135 | 27 | 0 | 0 | 0.475352 | 0.475352 | -0.01881 | -0.01881 |

### Rollout telemetry by step index

| arm | step | observed | non-degenerate | rate | would change | enforced | unrestricted change | ms/step | max seconds |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|

## Paired per-case difference vs base

| arm | case | placed diff | fill diff |
|---|---|---:|---:|
| residual_affordance_shadow | b000-k15 | 0.0 | 0.0 |
| residual_affordance_shadow | b000-k20 | -0.667 | 0.865 |
| residual_affordance_shadow | b000-k40 | -1.0 | -0.677 |
| residual_affordance_shadow | b001-k20 | 0.333 | -0.705 |
| residual_affordance_shadow | b001-k30 | -0.333 | -1.982 |
