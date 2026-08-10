# Online policy ablation

- episode rows: 30; paired differences use `base` as the baseline arm.

- fill_score / num_placed_items are the only official components the bundled simulator computes; cog / stability / placement / soft_item scores exist only in the official environment and are captured automatically when present (score_components). final CoM z is the local cog proxy.

## Per arm

Lower is better for the three shake columns. They are the veto in AGENT_OPERATIONS 5.05: a selection, ordering or allocation change that worsens them is not adopted on a placed gain.

`final CoM z` is retained for continuity but its direction has been falsified once against an official submission pair (it improved while official cog fell 20.7%). Do not read it as a cog proxy.

| arm | episodes | placed mean | fill mean | steps mean | shake max shift | shake peak KE | shake shifted | final CoM z | near-miss settles (5-30 deg) | surface TV |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| base | 15 | 18.133 | 21.362 | 19.133 | 0.306 | 55.939 | 4.6 | 0.701 | 2.6 | 0.031 |
| temporal_chunk_shadow | 15 | 18.467 | 20.956 | 19.467 | 0.333 | 58.341 | 4.667 | 0.704 | 3.0 | 0.031 |

## Mean totals and registered development guard

| arm | development cases | dev placed total | dev fill total | suite cases | suite placed total | suite fill total |
|---|---:|---:|---:|---:|---:|---:|
| base | 5 | 90.667 | 106.809 | 5 | 90.667 | 106.809 |
| temporal_chunk_shadow | 5 | 92.333 | 104.778 | 5 | 92.333 | 104.778 |

Registered current-default development baseline: placed `88.0`, fill `114.6`. This is a historical guard; the simultaneously executed base arm is the causal comparator for this run.

## Cross-step incumbent telemetry

| arm | steps | carried | pool survived | static valid | static survival | would prevent fallback | validation ms/step | deadline overruns |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| base | 0 | 0 | 0 | 0 | None | 0 | None | 0 |
| temporal_chunk_shadow | 0 | 0 | 0 | 0 | None | 0 | None | 0 |

## Temporal chunk ensemble telemetry

| arm | steps | scheduled | static valid | survival | multi-origin steps | consensus steps | selected match | selected disagree | fallback rescue | generated | ms/step | survival by delay |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| base | 0 | 0 | 0 | None | 0 | 0 | 0 | 0 | 0 | 0 | None | `{}` |
| temporal_chunk_shadow | 292 | 84 | 48 | 0.571429 | 3 | 0 | 0 | 0 | 0 | 84 | 30.486 | `{"1": 0.725806, "2": 0.136364}` |

## Visible-pool rollout telemetry

| arm | steps | candidates | eligible | non-degenerate | would change item | unrestricted change | within band | enforced | ms/step | max seconds |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| base | 0 | 0 | 0 | 0 | 0 | 0 | None | 0 | None | 0.0 |
| temporal_chunk_shadow | 0 | 0 | 0 | 0 | 0 | 0 | None | 0 | None | 0.0 |

### Rollout telemetry by step index

| arm | step | observed | non-degenerate | rate | would change | enforced | unrestricted change | ms/step | max seconds |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|

## Paired per-case difference vs base

| arm | case | placed diff | fill diff |
|---|---|---:|---:|
| temporal_chunk_shadow | b000-k15 | -1.334 | -1.54 |
| temporal_chunk_shadow | b000-k20 | 1.0 | -1.965 |
| temporal_chunk_shadow | b000-k40 | 0.0 | 0.0 |
| temporal_chunk_shadow | b001-k20 | 2.0 | 1.474 |
| temporal_chunk_shadow | b001-k30 | 0.0 | 0.0 |
