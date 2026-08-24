# Single-agent mainline contract (Phase 2)

Status: active contract. Supersedes the two-player scaffold as the
mainline; the two-player modules stay in the tree as frozen instruments
(Phase 0) and are not extended.

## Why

The two-player shared-board game was scaffolding: it manufactured an
adversarial objective (zero-sum attribute penalties, terminal +-50) and
a chance process (handoff draws) around what is physically a
single-agent sequential packing problem. Every measurement that now
matters — raw joint component vectors, paired counterfactual
evaluation, coverage support — is defined without it, and the terminal
probes proved the physical trajectory under rank-0 is independent of
handoff bookkeeping. Phase 2 makes the mainline say what the problem
is: one agent, one stream, vector-valued physical outcomes.

## Removed (not deprecated — removed from the mainline)

- players, turns, `current_player`, mover/next_player bookkeeping;
- handoff chance, `minimum_block`, block lengths, `handoff_count`;
- zero-sum attribute rewards and the `attribute_penalty` exchange rate;
- terminal +-`terminal_reward`, winner/loser, `game_reward` /
  `game_return` / `return_to_go` heads and the value-scale built from
  them;
- `player_to_move` (and the other game features) as model inputs;
- Dirichlet noise, visit policy targets, and the scalar PUCT tree from
  the mainline loop (they remain in the frozen two-player instruments;
  vector edge statistics arrive at Phase 4 with their own contract).

Attribute events themselves are not removed: soft/priority counters
stay measured as raw component heads. What is removed is the
hand-chosen penalty weight that converted them into a scalar game.
Official weighting returns only at Phase 10 (W/G/tau calibration).

## The single-agent loop

```
state -> candidates = legacy top-k  ∪  coverage (same physical filter)
      -> measurement: every union candidate, paired per world replica,
         one bounded physical step (+ optional frozen leaf-V shadow)
      -> execute rank-0 legacy candidate
      -> repeat until genuine termination
```

- Execution policy: rank-0 legacy, unchanged (execution improvements
  are Phase 6, gated).
- Genuine termination: `stream_exhausted` or no safe legacy candidate
  (`no_retained_candidate` / `no_safe_retained_candidate`); a step cap
  censors. No terminal reward exists; termination is an outcome
  boundary, not a loss.
- Objective: none scalar. The record of an episode is its raw component
  vector stream and terminal evaluation (fill, placed, soft/priority
  counters, surface TV, CoM, post-shake stability).

## Chance, redefined

With handoff gone the configured environment is deterministic: same
stream, same actions, same physics. The agent's real uncertainty is the
**unseen stream suffix** beyond the look-ahead window. `ExogenousWorld`
survives as exactly that: a world is a realization of the unobserved
future stream, addressed semantically as before
(`future_stream_id` already sits in the world identity). Two honest
consequences:

- In the current dev configs the look-ahead covers essentially the
  whole stream, so there is one degenerate world; paired evaluation
  still compares sibling candidates at the same state, and replicas are
  declared `world_realization = "degenerate_deterministic_stream"`
  rather than pretending variance.
- When stream-suffix uncertainty is modeled (competition setting),
  replicas become genuine future draws and the whole paired machinery
  (blocks, confidence Pareto, Wilson gates) applies unchanged.

## Data schema

`JointOutcomeSample` moves to `schema_version: 3`,
`behavior_contract: "single_agent_v1"`:

- dropped: `root_player`, per-player rewards, game heads;
- kept: `candidate_set_id`, `outcome_sample_id`, candidate provenance
  (source/coverage fields), world identity + replica index,
  `raw_outcome_vector` + `head_eligibility` over the component heads,
  termination/censor semantics (`bounded_candidate_exhaustion` stays
  censored — search support exhaustion is still not a world fact);
- state tensors unchanged (`observed_set_tensors_*`); game features are
  gone from every model input contract.

Trajectory suffix value targets keep the component returns,
`stream_completed`, and terminal stability heads; `return_to_go` and
`game_return` end with the game that defined them.

### Additive shadow measurements (2026-08-24)

Attribute coverage is now retained at four resolutions for each of soft
and priority cargo: direct-contact violated-item count, direct-contact
violating-pair count, stack-aware violated-item count, and stack-aware
violating-pair count. The original bundled direct/item counter remains the
active published-rule proxy. The other readings are diagnostic value heads;
they are not scalar penalties and do not enter the Pareto dominance set.

Raw center-of-mass height remains in every terminal/component record but is
also excluded from search dominance. More fill mechanically raises CoG even
under an efficient bottom-up packing, so a conditional residual needs a
separate calibration before CoG can discriminate search branches honestly.

Single-agent records also carry an `item_symmetry_fingerprint` that removes
stable labels only for items with identical model-visible physical features.
Exact `board_fingerprint` remains the replay and DAG merge key; missing item
metadata keeps the stable label and therefore fails closed.

The six-cell paired gate subsequently passed at 64/64 transitions with zero
false merges. `run_vector_mcts.py --item-symmetry-cache-shadow` therefore now
measures root-local quotient-only leaf hits, potential V-call savings, and
conflicting deterministic V signatures. Learned-V caching and search-node
merging remain disabled. The passed physical gate separately licenses two
V-independent operations: root-local genuine-terminal rollout memoization and
one-representative PyBullet checks for exact identical-item action orbits. The
latter preserves every logical candidate and its rank; it only avoids repeated
physical validation.

## Compatibility with collected data

Two-player artifacts are not converted and never silently mixed:
loaders must key on `behavior_contract`. But the physical content of
rank-0 two-player trajectories is single-agent data already — handoff
only relabeled the mover — so existing collections remain usable by
reinterpretation (ignore game bookkeeping), and that reinterpretation
is exactly what the verification gate below tests.

## Verification gates for the refactor

1. Unit tests on the new loop (termination, union, provenance, schema).
2. **Physical identity**: on the union pilot cells and seeds, the
   single-agent runner must reproduce the two-player rank-0 run's
   executed action sequence and per-step component metrics exactly.
3. The paired audit (single-agent mode) passes on the new manifests:
   complete candidate x replica blocks, one world per replica,
   measurement-only coverage, no policy targets.

## Out of scope for Phase 2

Learned proposal beta (3), vector edge statistics/backup (4), adaptive
allocation (5), execution changes (6), any scalarization (10).
