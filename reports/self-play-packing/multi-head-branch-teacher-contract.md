# Multi-head physical branch teacher contract

Status: joint-outcome schema v2 implemented. Scalar PUCT scoring and allocation
formulae are unchanged, but chance scheduling changed from one sequential RNG
to semantic exogenous worlds; bit-identical parity with older searches is not
expected.

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

Schema v2 additionally treats the unaggregated row as the durable source of
truth. It stores `outcome_sample_id`, `candidate_set_id`, candidate/path
provenance, `raw_outcome_vector`, per-head eligibility, and one
`exogenous_world_id`. The raw row, rather than component means or covariance,
is what permits later reconstruction of gate/component interactions such as
`E[1(placed >= tau) * stability]` for a newly calibrated threshold.

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

## Exogenous-world pairing

At each root, the nth rollout of every root candidate is assigned the same
exogenous-world sample index. A world draw is addressed by

```text
(root_id, world_sample_index, future_stream_id,
 event_type, event_index, draw_index)
```

rather than by consuming one global RNG. The first implemented event is the
handoff opportunity after each post-root placement. Branches may skip or
reorder other events later without shifting this draw. This makes overlapping
world indices directly pairable across sibling candidates.

This change does **not** make PUCT allocation objective-neutral: the scalar
PUCT still decides which candidates receive rollouts, so some sibling pairs
may have no overlapping world index. A later paired round-robin instrument is
required before claiming complete common-random-number coverage.

Old and new PUCT runs must not be pooled as repeated samples of one instrument.
Any decision-quality comparison after this migration requires a fresh paired
baseline generated under this same exogenous-world contract.

`candidate_set_id` hashes only the canonical action support and is independent
of proposal order, source, policy probability, and mixture weight. Those are
stored separately in `proposal_provenance`. The current legacy provider is
labelled `legacy_provider`; widening and provider-zero actions are labelled
`widening_rescue` and `provider_zero_rescue` when they enter a path.

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

`build_self_play_pv_dataset.py` schema v3 exports:

- the played root state and search policy;
- per-candidate multi-head aggregates;
- raw `bounded_branch_outcomes` containing replayable leaf set tensors and
  root-to-leaf outcome masks, joint outcome IDs and exogenous-world IDs;
- `candidate_set_id` plus proposal source/behavior provenance without treating
  that provenance as an action-value target;
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
