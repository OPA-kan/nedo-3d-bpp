# Online policy ablation

- episode rows: 30; paired differences use `base` as the baseline arm.

- fill_score / num_placed_items are the only official components the bundled simulator computes; cog / stability / placement / soft_item scores exist only in the official environment and are captured automatically when present (score_components). final CoM z is the local cog proxy.

## Per arm

Lower is better for the three shake columns. They are the veto in AGENT_OPERATIONS 5.05: a selection, ordering or allocation change that worsens them is not adopted on a placed gain.

`final CoM z` is retained for continuity but its direction has been falsified once against an official submission pair (it improved while official cog fell 20.7%). Do not read it as a cog proxy.

| arm | episodes | placed mean | fill mean | steps mean | shake max shift | shake peak KE | shake shifted | final CoM z | near-miss settles (5-30 deg) | surface TV |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| base | 15 | 19.533 | 22.187 | 20.533 | 0.313 | 37.643 | 6.0 | 0.726 | 3.067 | 0.031 |
| residual_affordance_enforce | 15 | 17.2 | 18.758 | 18.2 | 0.261 | 85.542 | 5.267 | 0.682 | 1.733 | 0.03 |

## Same-call decision-invariance negative control

| observed | incumbent unchanged | portfolio unchanged | missing | guarded regressions | passed |
|---:|---:|---:|---:|---:|---|
| 0 | 0 | 0 | 0 | 0 | False |

## Cross-process action-sequence diagnostic

Exact hashes are retained as a nondeterminism diagnostic, not used as the same-call decision-invariance gate.

| paired | matched | mismatched | missing | passed |
|---:|---:|---:|---:|---|
| 15 | 0 | 15 | 0 | False |

## Full local proxy vector

No weighted total is formed. Higher is better for the two clean ratios; lower is better for shake and policy cost.

| arm | shake toppled | shifted fraction | priority clean | soft clean | included rate | valid rate | placed-safe rate | policy seconds |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| base | 0.533 | 0.308 | 0.767 | 0.967 | 1.0 | 0.4 | 0.0 | 6.476 |
| residual_affordance_enforce | 0.533 | 0.302 | 0.778 | 0.967 | 1.0 | 0.867 | 0.0 | 6.305 |

## Terminal channels

Counts remain categorical and are not folded into a score.

| arm | channels |
|---|---|
| base | `{"topple": 6, "transport_invalid": 9}` |
| residual_affordance_enforce | `{"slide": 4, "topple": 9, "transport_invalid": 2}` |

## Mean totals and registered development guard

| arm | development cases | dev placed total | dev fill total | suite cases | suite placed total | suite fill total |
|---|---:|---:|---:|---:|---:|---:|
| base | 5 | 97.666 | 110.935 | 5 | 97.666 | 110.935 |
| residual_affordance_enforce | 5 | 86.001 | 93.791 | 5 | 86.001 | 93.791 |

Registered current-default development baseline: placed `88.0`, fill `114.6`. This is a historical guard; the simultaneously executed base arm is the causal comparator for this run.

## Search work

| arm | decisions | structured records | attempts total | attempts/decision | max attempts |
|---|---:|---:|---:|---:|---:|
| base | 308 | 0 | 2976894 | 9665.24 | 27136 |
| residual_affordance_enforce | 273 | 0 | 2342068 | 8579.004 | 25344 |

## Cross-step incumbent telemetry

| arm | steps | carried | pool survived | static valid | static survival | would prevent fallback | validation ms/step | deadline overruns |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| base | 0 | 0 | 0 | 0 | None | 0 | None | 0 |
| residual_affordance_enforce | 0 | 0 | 0 | 0 | None | 0 | None | 0 |

## Temporal chunk ensemble telemetry

| arm | steps | scheduled | static valid | survival | multi-origin | action consensus | action match/disagree | any action/item match | item consensus | item match/disagree | fallback rescue | generated | ms/step | survival by delay |
|---|---:|---:|---:|---:|---:|---:|---|---|---:|---|---:|---:|---:|---|
| base | 0 | 0 | 0 | None | 0 | 0 | 0/0 | 0/0 | 0 | 0/0 | 0 | 0 | None | `{}` |
| residual_affordance_enforce | 0 | 0 | 0 | None | 0 | 0 | 0/0 | 0/0 | 0 | 0/0 | 0 | 0 | None | `{}` |

## Visible-pool rollout telemetry

| arm | steps | candidates | eligible | non-degenerate | would change item | unrestricted change | within band | enforced | ms/step | max seconds |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| base | 0 | 0 | 0 | 0 | 0 | 0 | None | 0 | None | 0.0 |
| residual_affordance_enforce | 0 | 0 | 0 | 0 | 0 | 0 | None | 0 | None | 0.0 |

## Multi-axis selector shadow

| arm | observed | multi-candidate | candidates | Pareto front | rank0 dominated | selected dominated | selected changes | item changes | enforced | change rate |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| base | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | None |
| residual_affordance_enforce | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | None |

## Residual-affordance action shadow

| arm | observed | candidates | changes | item changes | guarded changes | guarded item changes | enforced | attr blocked | contract regressions | change rate | guarded rate | immediate delta | guarded immediate delta |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| base | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | None | None | None | None |
| residual_affordance_enforce | 271 | 809 | 104 | 22 | 101 | 22 | 101 | 4 | 4 | 0.383764 | 0.372694 | -0.020676 | -0.020107 |

### Rollout telemetry by step index

| arm | step | observed | non-degenerate | rate | would change | enforced | unrestricted change | ms/step | max seconds |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|

## Paired per-case difference vs base

| arm | case | placed diff | fill diff |
|---|---|---:|---:|
| residual_affordance_enforce | b000-k15 | -2.333 | 0.198 |
| residual_affordance_enforce | b000-k20 | -2.666 | -7.347 |
| residual_affordance_enforce | b000-k40 | -1.333 | -7.63 |
| residual_affordance_enforce | b001-k20 | -5.333 | -3.426 |
| residual_affordance_enforce | b001-k30 | 0.0 | 1.061 |
