# Multi-head physical branch teacher contract

Status: implemented instrument; scalar PUCT behavior unchanged.

## Unit of observation

Each physical PUCT simulation emits one `multi_head_branch_samples` row. These
are root-action bounded outcomes for Q_H/policy supervision, **not** value
targets for the recorded leaf state. The
row identifies its root candidate and complete search path, and retains:

- relative and absolute command-action prefixes;
- leaf board fingerprint and model-visible state signature;
- root/leaf player, block, handoff and placement game state;
- the exact replay contract and leaf set tensor;
- root and leaf cumulative metrics;
- termination mode and whether continuation is censored;
- one independently masked target for every head.

The policy row for each root candidate also contains a
`multi_head_target` aggregate. Means/minima/maxima use eligible samples only;
censored samples are counted but never averaged in as zero.

## Heads

| head | stored quantity | orientation |
|---|---|---|
| `game_reward` | bounded rollout attribute reward from root-player view | maximize |
| `fill_gain` | leaf minus root fill proxy | maximize |
| `placed_gain` | leaf minus root placed count | diagnostic |
| `survival_to_rollout_end` | reached requested H or true stream completion | maximize |
| `soft_violation_gain` | new soft coverage debt | minimize |
| `priority_covered_gain` | new priority coverage debt | minimize |
| `priority_misrouted_gain` | new priority routing debt | minimize |
| `center_of_mass_z_delta` | leaf minus root CoG height | diagnostic |
| `surface_total_variation_delta` | leaf minus root surface variation | minimize proxy |
| `stability_max_shift` | leaf post-shake maximum shift | minimize |
| `stability_peak_kinetic_energy` | leaf post-shake peak KE | minimize |
| `stability_items_toppled` | leaf post-shake toppled count | minimize |

No weighted sum is stored or trained by this contract.

## Censoring

`horizon` and genuine `stream_exhausted` branches are eligible H-step targets
when the requested metric is present. `bounded_candidate_exhaustion` and
`simulator_truncated` retain observed partial values for diagnosis but set
`target_eligible=false` for every head. A metric absent from an otherwise
complete branch is stored as `value=null`, `censor_reason=unmeasured`.

Search rollouts currently supply settled cumulative metrics, not a shake at
every search leaf. Consequently their three stability heads are present but
ineligible rather than silently zero. The played trajectory runs the existing
terminal shake once and exports its stability results as state-to-episode-end
value heads.

## Dataset export

`build_self_play_pv_dataset.py` schema v2 exports:

- the played root state and search policy;
- per-candidate multi-head aggregates;
- raw `bounded_branch_outcomes` containing replayable leaf set tensors and
  root-to-leaf outcome masks;
- `value_heads` containing played-state-to-episode-end fill/placed/attribute/
  stability suffix targets;
- scalar terminal suffix return for eligible completed games.

Training a leaf tensor against the preceding branch's root-to-leaf gain would
teach past accumulation and leak the outcome into the input. A Set Transformer
V must use the played root `state` with `value_heads`; leaf tensors remain for
replay, future bootstrap and search-follow collection until a genuine
leaf-to-terminal target exists.

The existing leakage audit still rejects `score`, `immediate_score`, `rank`,
`prior`, and `selection` anywhere in a learner row.
