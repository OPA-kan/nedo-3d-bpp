# Cross-step incumbent survival instrument

This experiment tests whether validated candidates from step `t` remain
usable at step `t+1`.  It is motivated by the rejected deadline-reserved
rescue scan: reserving time on every step degraded the primary search, while
the rescue still returned no action when it finally triggered.

The instrument is disabled by default:

```text
CROSS_STEP_INCUMBENT_MODE=off
```

Set `CROSS_STEP_INCUMBENT_MODE=shadow` to collect candidates and revalidate
them on the next observation.  Shadow mode never returns a retained candidate
and therefore does not change the selection contract.  `enforce` is
intentionally not implemented; it requires survival and cost evidence first.

## Candidate population

The normal primary search observes every candidate that already passed its
current static admission checks.  For each stable `item.index` and each of
`settled` / `release`, it retains the top `N` by the shipped risk-adjusted
score.  `N` is controlled by `CROSS_STEP_INCUMBENT_PER_ITEM` and defaults to
2.  Duplicate commands are removed.  Candidates for the item selected at
step `t` are not carried because that item leaves the visible pool.

The stored action uses a stable item identity, not the old pool offset.  At
step `t+1` it is remapped to the current pool index.

## Revalidation contract

Each retained command is checked against the complete next observed state:

1. the stable item is still visible;
2. the target container still exists;
3. settled candidates pass containment, static geometry, support, and
   transport;
4. release candidates pass containment, static geometry, transport, and the
   configured release gate semantics;
5. the shipped Ranker/risk score is recomputed only for telemetry.

This first version deliberately uses the full static contract.  It does not
claim that checking overlap with only the newest packed item is sufficient,
and it does not call PyBullet.  A statically valid retained release remains a
candidate for later physical evaluation, not a safety guarantee.

## Trace fields

`candidate_diagnostics.cross_step_incumbent` records:

- previous candidate/item counts;
- pool-surviving candidate/item counts;
- statically valid candidate/item counts, split by settled/release;
- rejection reasons;
- validation time and deadline margin before/after validation;
- candidates retained for the next step;
- `would_prevent_protocol_fallback`, which is true only when the live policy
  returned no candidate while at least one carried candidate revalidated.

The Task B ablation runner exposes the `cross_step_shadow` arm and aggregates
these counts plus total/max validation time and deadline overruns.

## Interpretation and adoption gate

Shadow collection adds bookkeeping inside the deadline-bound primary search,
and revalidation adds work after the action has already been selected.  It is
therefore not assumed to be runtime-neutral.  `off` remains the exact shipped
path, and physical evaluation must compare `base` against
`cross_step_shadow` as well as inspect action divergence.

Do not implement or enable `enforce` unless the measurements show both:

1. retained candidates survive at the protocol-fallback steps often enough
   to matter; and
2. collection/revalidation cost does not cause an unexplained placed/fill or
   deadline regression.
