# Online policy ablation

- episode rows: 45; paired differences use `base` as the baseline arm.

- fill_score / num_placed_items are the only official components the bundled simulator computes; cog / stability / placement / soft_item scores exist only in the official environment and are captured automatically when present (score_components). final CoM z is the local cog proxy.

## Per arm

Lower is better for the three shake columns. They are the veto in AGENT_OPERATIONS 5.05: a selection, ordering or allocation change that worsens them is not adopted on a placed gain.

`final CoM z` is retained for continuity but its direction has been falsified once against an official submission pair (it improved while official cog fell 20.7%). Do not read it as a cog proxy.

| arm | episodes | placed mean | fill mean | steps mean | shake max shift | shake peak KE | shake shifted | final CoM z | near-miss settles (5-30 deg) | surface TV |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| base | 15 | 18.267 | 21.164 | 19.267 | 0.32 | 56.511 | 5.533 | 0.699 | 3.2 | 0.031 |
| base_null | 15 | 19.067 | 21.264 | 20.067 | 0.335 | 53.787 | 4.933 | 0.719 | 3.267 | 0.031 |
| structured_noop | 15 | 19.2 | 21.756 | 20.2 | 0.371 | 59.236 | 5.0 | 0.719 | 2.8 | 0.031 |

## Full local proxy vector

No weighted total is formed. Higher is better for the two clean ratios; lower is better for shake and policy cost.

| arm | shake toppled | shifted fraction | priority clean | soft clean | included rate | valid rate | placed-safe rate | policy seconds |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| base | 1.467 | 0.315 | 0.767 | 0.988 | 1.0 | 0.6 | 0.0 | 6.219 |
| base_null | 0.867 | 0.264 | 0.717 | 0.973 | 1.0 | 0.533 | 0.0 | 6.372 |
| structured_noop | 1.0 | 0.27 | 0.7 | 0.967 | 1.0 | 0.467 | 0.0 | 6.338 |

## Terminal channels

Counts remain categorical and are not folded into a score.

| arm | channels |
|---|---|
| base | `{"slide": 4, "topple": 5, "transport_invalid": 6}` |
| base_null | `{"slide": 1, "topple": 7, "transport_invalid": 7}` |
| structured_noop | `{"topple": 7, "transport_invalid": 8}` |

## Mean totals and registered development guard

| arm | development cases | dev placed total | dev fill total | suite cases | suite placed total | suite fill total |
|---|---:|---:|---:|---:|---:|---:|
| base | 5 | 91.333 | 105.821 | 5 | 91.333 | 105.821 |
| base_null | 5 | 95.333 | 106.321 | 5 | 95.333 | 106.321 |
| structured_noop | 5 | 96.0 | 108.782 | 5 | 96.0 | 108.782 |

Registered current-default development baseline: placed `88.0`, fill `114.6`. This is a historical guard; the simultaneously executed base arm is the causal comparator for this run.

## Search work

| arm | decisions | structured records | attempts total | attempts/decision | max attempts |
|---|---:|---:|---:|---:|---:|
| base | 289 | 0 | 2325810 | 8047.785 | 16509 |
| base_null | 301 | 0 | 2582972 | 8581.302 | 24840 |
| structured_noop | 303 | 295 | 2648509 | 8740.954 | 25335 |

## Cross-step incumbent telemetry

| arm | steps | carried | pool survived | static valid | static survival | would prevent fallback | validation ms/step | deadline overruns |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| base | 0 | 0 | 0 | 0 | None | 0 | None | 0 |
| base_null | 0 | 0 | 0 | 0 | None | 0 | None | 0 |
| structured_noop | 0 | 0 | 0 | 0 | None | 0 | None | 0 |

## Temporal chunk ensemble telemetry

| arm | steps | scheduled | static valid | survival | multi-origin | action consensus | action match/disagree | any action/item match | item consensus | item match/disagree | fallback rescue | generated | ms/step | survival by delay |
|---|---:|---:|---:|---:|---:|---:|---|---|---:|---|---:|---:|---:|---|
| base | 0 | 0 | 0 | None | 0 | 0 | 0/0 | 0/0 | 0 | 0/0 | 0 | 0 | None | `{}` |
| base_null | 0 | 0 | 0 | None | 0 | 0 | 0/0 | 0/0 | 0 | 0/0 | 0 | 0 | None | `{}` |
| structured_noop | 0 | 0 | 0 | None | 0 | 0 | 0/0 | 0/0 | 0 | 0/0 | 0 | 0 | None | `{}` |

## Visible-pool rollout telemetry

| arm | steps | candidates | eligible | non-degenerate | would change item | unrestricted change | within band | enforced | ms/step | max seconds |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| base | 0 | 0 | 0 | 0 | 0 | 0 | None | 0 | None | 0.0 |
| base_null | 0 | 0 | 0 | 0 | 0 | 0 | None | 0 | None | 0.0 |
| structured_noop | 0 | 0 | 0 | 0 | 0 | 0 | None | 0 | None | 0.0 |

### Rollout telemetry by step index

| arm | step | observed | non-degenerate | rate | would change | enforced | unrestricted change | ms/step | max seconds |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|

## Paired per-case difference vs base

| arm | case | placed diff | fill diff |
|---|---|---:|---:|
| base_null | b000-k15 | 0.0 | 0.0 |
| base_null | b000-k20 | 1.333 | 3.025 |
| base_null | b000-k40 | 2.667 | -1.656 |
| base_null | b001-k20 | 0.0 | -0.869 |
| base_null | b001-k30 | 0.0 | 0.0 |
| structured_noop | b000-k15 | -2.667 | -3.08 |
| structured_noop | b000-k20 | 1.667 | -0.485 |
| structured_noop | b000-k40 | 2.0 | 1.282 |
| structured_noop | b001-k20 | 3.667 | 5.244 |
| structured_noop | b001-k30 | 0.0 | 0.0 |
