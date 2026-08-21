# Online policy ablation

- episode rows: 30; paired differences use `base` as the baseline arm.

- fill_score / num_placed_items are the only official components the bundled simulator computes; cog / stability / placement / soft_item scores exist only in the official environment and are captured automatically when present (score_components). final CoM z is the local cog proxy.

## Per arm

Lower is better for the three shake columns. They are the veto in AGENT_OPERATIONS 5.05: a selection, ordering or allocation change that worsens them is not adopted on a placed gain.

`final CoM z` is retained for continuity but its direction has been falsified once against an official submission pair (it improved while official cog fell 20.7%). Do not read it as a cog proxy.

| arm | episodes | placed mean | fill mean | steps mean | shake max shift | shake peak KE | shake shifted | final CoM z | near-miss settles (5-30 deg) | surface TV |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| base | 15 | 18.2 | 20.427 | 19.2 | 0.23 | 28.624 | 3.867 | 0.696 | 3.333 | 0.031 |
| residual_affordance_shadow | 15 | 18.6 | 21.111 | 19.6 | 0.237 | 30.77 | 4.533 | 0.71 | 3.133 | 0.03 |

## Same-call decision-invariance negative control

| observed | incumbent unchanged | portfolio unchanged | missing | guarded regressions | passed |
|---:|---:|---:|---:|---:|---|
| 287 | 287 | 287 | 0 | 0 | True |

## Cross-process action-sequence diagnostic

Exact hashes are retained as a nondeterminism diagnostic, not used as the same-call decision-invariance gate.

| paired | matched | mismatched | missing | passed |
|---:|---:|---:|---:|---|
| 15 | 5 | 10 | 0 | False |

## Full local proxy vector

No weighted total is formed. Higher is better for the two clean ratios; lower is better for shake and policy cost.

| arm | shake toppled | shifted fraction | priority clean | soft clean | included rate | valid rate | placed-safe rate | policy seconds |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| base | 0.6 | 0.226 | 0.761 | 0.987 | 1.0 | 0.6 | 0.0 | 6.302 |
| residual_affordance_shadow | 0.8 | 0.254 | 0.767 | 0.987 | 1.0 | 0.533 | 0.0 | 6.429 |

## Terminal channels

Counts remain categorical and are not folded into a score.

| arm | channels |
|---|---|
| base | `{"slide": 3, "topple": 6, "transport_invalid": 6}` |
| residual_affordance_shadow | `{"slide": 3, "topple": 5, "transport_invalid": 7}` |

## Mean totals and registered development guard

| arm | development cases | dev placed total | dev fill total | suite cases | suite placed total | suite fill total |
|---|---:|---:|---:|---:|---:|---:|
| base | 5 | 91.001 | 102.136 | 5 | 91.001 | 102.136 |
| residual_affordance_shadow | 5 | 93.0 | 105.555 | 5 | 93.0 | 105.555 |

Registered current-default development baseline: placed `88.0`, fill `114.6`. This is a historical guard; the simultaneously executed base arm is the causal comparator for this run.

## Search work

| arm | decisions | structured records | attempts total | attempts/decision | max attempts |
|---|---:|---:|---:|---:|---:|
| base | 288 | 0 | 2400728 | 8335.861 | 21745 |
| residual_affordance_shadow | 294 | 0 | 2515947 | 8557.643 | 20874 |

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
| residual_affordance_shadow | 287 | 856 | 129 | 24 | 126 | 22 | 6 | 6 | 0.449477 | 0.439024 | -0.019743 | -0.017417 |

### Rollout telemetry by step index

| arm | step | observed | non-degenerate | rate | would change | enforced | unrestricted change | ms/step | max seconds |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|

## Paired per-case difference vs base

| arm | case | placed diff | fill diff |
|---|---|---:|---:|
| residual_affordance_shadow | b000-k15 | -0.667 | -0.73 |
| residual_affordance_shadow | b000-k20 | 0.0 | 0.0 |
| residual_affordance_shadow | b000-k40 | 1.333 | 1.249 |
| residual_affordance_shadow | b001-k20 | 0.666 | 0.755 |
| residual_affordance_shadow | b001-k30 | 0.667 | 2.145 |
