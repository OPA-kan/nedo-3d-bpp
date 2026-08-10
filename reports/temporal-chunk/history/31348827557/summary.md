# Online policy ablation

- episode rows: 30; paired differences use `base` as the baseline arm.

- fill_score / num_placed_items are the only official components the bundled simulator computes; cog / stability / placement / soft_item scores exist only in the official environment and are captured automatically when present (score_components). final CoM z is the local cog proxy.

## Per arm

Lower is better for the three shake columns. They are the veto in AGENT_OPERATIONS 5.05: a selection, ordering or allocation change that worsens them is not adopted on a placed gain.

`final CoM z` is retained for continuity but its direction has been falsified once against an official submission pair (it improved while official cog fell 20.7%). Do not read it as a cog proxy.

| arm | episodes | placed mean | fill mean | steps mean | shake max shift | shake peak KE | shake shifted | final CoM z | near-miss settles (5-30 deg) | surface TV |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| base | 15 | 17.667 | 20.084 | 18.667 | 0.279 | 50.344 | 4.933 | 0.679 | 2.733 | 0.03 |
| temporal_chunk_shadow_stride4 | 15 | 18.333 | 21.041 | 19.333 | 0.357 | 65.731 | 4.467 | 0.706 | 3.067 | 0.03 |

## Mean totals and registered development guard

| arm | development cases | dev placed total | dev fill total | suite cases | suite placed total | suite fill total |
|---|---:|---:|---:|---:|---:|---:|
| base | 5 | 88.333 | 100.422 | 5 | 88.333 | 100.422 |
| temporal_chunk_shadow_stride4 | 5 | 91.667 | 105.205 | 5 | 91.667 | 105.205 |

Registered current-default development baseline: placed `88.0`, fill `114.6`. This is a historical guard; the simultaneously executed base arm is the causal comparator for this run.

## Cross-step incumbent telemetry

| arm | steps | carried | pool survived | static valid | static survival | would prevent fallback | validation ms/step | deadline overruns |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| base | 0 | 0 | 0 | 0 | None | 0 | None | 0 |
| temporal_chunk_shadow_stride4 | 0 | 0 | 0 | 0 | None | 0 | None | 0 |

## Temporal chunk ensemble telemetry

| arm | steps | scheduled | static valid | survival | multi-origin | action consensus | action match/disagree | any action/item match | item consensus | item match/disagree | fallback rescue | generated | ms/step | survival by delay |
|---|---:|---:|---:|---:|---:|---:|---|---|---:|---|---:|---:|---:|---|
| base | 0 | 0 | 0 | None | 0 | 0 | 0/0 | 0/0 | 0 | 0/0 | 0 | 0 | None | `{}` |
| temporal_chunk_shadow_stride4 | 290 | 192 | 148 | 0.770833 | 10 | 0 | 0/0 | 6/22 | 0 | 0/0 | 0 | 193 | 55.27 | `{"1": 0.888889, "2": 0.307692}` |

## Visible-pool rollout telemetry

| arm | steps | candidates | eligible | non-degenerate | would change item | unrestricted change | within band | enforced | ms/step | max seconds |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| base | 0 | 0 | 0 | 0 | 0 | 0 | None | 0 | None | 0.0 |
| temporal_chunk_shadow_stride4 | 0 | 0 | 0 | 0 | 0 | 0 | None | 0 | None | 0.0 |

### Rollout telemetry by step index

| arm | step | observed | non-degenerate | rate | would change | enforced | unrestricted change | ms/step | max seconds |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|

## Paired per-case difference vs base

| arm | case | placed diff | fill diff |
|---|---|---:|---:|
| temporal_chunk_shadow_stride4 | b000-k15 | 2.667 | 3.08 |
| temporal_chunk_shadow_stride4 | b000-k20 | -4.667 | -5.117 |
| temporal_chunk_shadow_stride4 | b000-k40 | 2.667 | 2.869 |
| temporal_chunk_shadow_stride4 | b001-k20 | 2.0 | 1.806 |
| temporal_chunk_shadow_stride4 | b001-k30 | 0.667 | 2.145 |
