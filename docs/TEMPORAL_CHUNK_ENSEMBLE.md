# Temporal chunk ensemble shadow

This instrument tests whether overlapping short rollout plans provide a
useful delayed ensemble for the current placement decision.  It is inspired
by action chunking, but it does **not** execute a chunk open-loop.

The mode is disabled by default:

```text
TEMPORAL_CHUNK_ENSEMBLE_MODE=off
```

Set it to `shadow` to generate and revalidate delayed proposals.  Shadow mode
never changes the returned action.  There is intentionally no `enforce` mode
until the delayed proposals show survival, disagreement, and acceptable cost.

## Contract

At policy step `t`, after the live policy has selected `a[t|t]`, a bounded
static rollout predicts up to `TEMPORAL_CHUNK_DEPTH - 1` later commands:

```text
C_t = (a[t|t], a[t+1|t], ..., a[t+H-1|t])
```

Only the first command is executed by the simulator.  Future commands are
stored with stable item IDs and target steps.  At step `u`, proposals
`a[u|u-d]` from every available delay `d` are remapped to the current pool and
checked against the complete current static contract.

The rollout uses the existing deterministic `bounded_rollout_decision` and a
fixed anchor-attempt budget.  Settled proxy transitions may extend the
rollout.  A future release command is retained as a proposal but terminates
the chunk, because its post-settle state is unknown without PyBullet.

## Temporal vote

Nearby commands are grouped by:

```text
(stable item, container, orientation, settled/release,
 coarse x cell, coarse y cell)
```

The coarse cell size defaults to 0.10 m.  This avoids treating millimetre
differences in commands predicted from different proxy states as unrelated
plans.  It is an analysis equivalence class, not a physical acceptance rule.

The trace records:

- scheduled, pool-surviving, and statically valid proposals;
- valid proposals by delay;
- number of independent origin steps represented;
- action-group count and maximum vote count;
- item-only vote count, kept separate from coarse action agreement;
- whether the live action matches any valid delayed action or item proposal;
- whether the live action matches the temporal consensus;
- whether a valid delayed proposal existed when the live policy returned no
  candidate;
- generation and revalidation cost.

## Difference from cross-step incumbent

`CROSS_STEP_INCUMBENT_MODE=shadow` retains score-top candidates that were
valid at the preceding current state.  It asks whether an old current action
survives one step.

The temporal chunk ensemble retains actions explicitly predicted for a future
step.  At step `t+2`, for example, it can compare `a[t+2|t]`, `a[t+2|t+1]`,
and the live `a[t+2|t+2]`.  Its population and question are therefore
different from the rejected score-top2 fallback experiment.

## Initial adoption gate

Keep the mode shadow-only until a paired Linux experiment establishes:

1. non-trivial static survival at delays 1 and 2;
2. multi-origin consensus on enough steps to distinguish actions;
3. interpretable disagreement with the live selection;
4. no material placed/fill regression caused by telemetry cost; and
5. preferably, at least one protocol-fallback step with a valid delayed
   proposal.

Even a positive result does not authorize direct execution of old commands.
Any later selection experiment must revalidate against the current state and
remain one-action closed-loop execution.

## First shadow run

Actions run `31348162973`, stride 1, five development configurations and
three repeats per arm.  Across 292 shadow steps it generated 84 delayed
proposals; 48 survived static revalidation.  Delay-1 survival was 45/62
(72.6%), while delay-2 survival was 3/22 (13.6%).  Only three steps had valid
proposals from multiple origin steps, no coarse action group received two
votes, and no protocol fallback had a valid delayed alternative.  Mean
generation plus validation cost was 30.5 ms/step.

This does not support enforcement, but it also did not instantiate a dense
ensemble: only 84 proposals were produced for 292 steps.  The registered
follow-up changes only the future anchor scan to stride 4, which prior rollout
coverage evidence found materially increases reach at the same attempt cap.
