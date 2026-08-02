# Live anchor scan interleave

## Why this exists

The rollout saturation experiment (`docs/ROLLOUT_SATURATION.md`) found that
the late-episode rollout silence was a property of the **anchor scan order**,
not of a full container: spreading a fixed attempt budget over the grid
reached a future placement on 28/37 late snapshots where the shipped order
reached 8/37, and reached strictly more than multiplying the budget by 8.4x
did.

The live candidate search runs through the same `support_plane` generator
with the same deterministic order. Two standing findings are the live-search
shape of the same defect:

- the post-cache coverage hole, with accepted anchors clustered in
  `x in [-0.34, 0.83]`;
- `transport-deaths-are-fallback-poison` — 45% of episode endings are the
  fixed-coordinate `unsafe_protocol_fallback`, which fires when the search
  returns **no** candidate at all.

`support_plane_anchor_positions` emits `for y descending, for x by |x|`. The
natural prefix of that order is one deep `y` band near the centre line. A
search truncated by its deadline sees that band densely and the rest of the
plane not at all.

## Interleave is not stride

This is the load-bearing distinction, and using the wrong one here would be a
silent regression.

| | `stride` | `interleave` |
| --- | --- | --- |
| operation | subsample: skip every non-phase anchor | permute: reorder, drop nothing |
| correct when the cap is | an attempt count | a deadline |
| at exhaustion | a strict subset | the identical set |
| used by | the rollout's future search | the live candidate search |

The rollout's future search is capped by `attempts_per_step`, which it can
never exhaust, so an anchor it skips is one it was never going to reach
anyway — skipping is free reach. The live search is capped by a deadline it
often *does* exhaust on a unit, so an anchor it skips is a candidate it would
otherwise have found. Subsampling the live search would trade recall for
coverage. Permuting trades nothing: it changes only which anchors a truncated
search reaches first.

## Contract

- `LIVE_SEARCH_INTERLEAVE`, default `1` — the shipped order.
- Applied in `PlacementCore.choose` and `PlacementCore.top_candidates` only.
  The rollout keeps its own `VISIBLE_POOL_ROLLOUT_STRIDE`;
  `rescue_choose` is untouched and stays default-off.
- Implemented in `iter_support_plane_attempts` and
  `iter_release_plane_attempts`, which build their anchors as a list per
  connected component. The interleave applies per component, so the
  round-robin across components is unchanged.
- `ANCHOR_GENERATOR_MODE=cartesian` **raises** on `interleave > 1`. That
  generator streams a nested product rather than a materialised list and
  cannot honour a permutation; running the shipped order under a name that
  says otherwise would corrupt any comparison built on it.
- `interleaved_scan_order` is a pure permutation and is tested as one: the
  reordered list is `sorted`-equal to the input for every interleave.

## Ablation arms

`live_interleave4` and `live_interleave8` in `scripts/run_risk_ablation.py`
differ from `base` by `LIVE_SEARCH_INTERLEAVE` and nothing else, which is
asserted by a test. `LIVE_SEARCH_INTERLEAVE` is scrubbed from the arm
environment like every other experiment control, so an arm cannot inherit
whatever the caller's shell held.

```bash
python3 scripts/run_risk_ablation.py \
  --config <task-b config> --arm live_interleave4 --repeat 1 \
  --output-dir reports/live-interleave/<run>
```

## Standing warning before reading any result

`aabb-cache-guard-mixed` in the ledger is the precedent: the packed-AABB
cache raised candidate throughput 6.4x and produced a *mixed* guard result
(+10 placed on one config, -12 on another), because with a defective utility
a larger candidate pool can select worse trajectories — the starved search
was acting as an accidental regulariser.

A scan-order change is a milder version of the same intervention: it does not
enlarge the candidate set at exhaustion, but it does change which candidate a
deadline-truncated search settles on, and therefore which trajectory is
taken. Expect heterogeneity across configurations, and do not read a total
without the per-configuration split.

The registered development baseline is placed 88 / fill 114.6 across the five
development configurations (`reports/benchmarks/baseline.json`).

## Correction (2026-08-02): the rejection below is NOT established

`reports/stream-variance/base-vs-item-cap16.json` measured the noise floor
this screening was read against. The unchanged agent, on 8 permutations of a
single item multiset - same items, same class mix, same total volume, only
arrival order varied - produced placed **sd 2.315 with a range of 7** and
fill **sd 3.948 with a range of 12.5**.

Every per-configuration delta below (+5, -4, -3, -1, 0) lies inside that
band, and the screening was **unpaired**: each configuration is a different
item stream, so its delta mixes the intervention with arrival-order variance
that was never estimated. Repeats do not help - the same configuration
repeated is bit-identical, so a 3-repeat design samples none of this source.

So the result below does not establish a negative. It is **not established**
in either direction. `LIVE_SEARCH_INTERLEAVE` stays 1 because nothing
established a positive either, not because a negative was measured. The
design that would settle it is the paired permutation sweep now available:
`build_stream_variants.py --mode permute` with both arms on each stream.

The mechanism discussion below stands on its own - the search diagnostics and
the b000-k40 pattern match are observations, not inferences from the totals.

## Result as originally reported (read with the correction above)

`reports/live-interleave/local-20260801-screening/`. Local Linux, PyBullet
3.2.7, one repeat per cell, `base` versus `live_interleave4` on the five
development configurations.

| case | base placed | il4 placed | d | base fill | il4 fill | d |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `b000-k15` | 17 | 14 | -3 | 23.119 | 12.655 | -10.464 |
| `b000-k20` | 16 | 12 | -4 | 17.287 | 12.804 | -4.483 |
| `b000-k40` | 14 | 19 | **+5** | 19.525 | 25.603 | **+6.078** |
| `b001-k20` | 18 | 17 | -1 | 20.989 | 19.708 | -1.281 |
| `b001-k30` | 18 | 18 | 0 | 23.822 | 21.225 | -2.597 |
| **total** | **83** | **80** | **-3** | **104.742** | **91.995** | **-12.747** |

`LIVE_SEARCH_INTERLEAVE` stays 1.

The warning above was the right one, and the outcome is the shape it
predicted. One configuration gains and it is the one the ledger already calls
search-starved: `b000-k40`, the same configuration where the packed-AABB
cache gained +10 while `b000-k20` lost 12. Two independent coverage
interventions - one enlarging the candidate set, one only reordering it - now
produce the same per-configuration signature.

The search diagnostics rule out the obvious alternative explanation. The
interleave did not make the search worse at finding candidates: both arms are
deadline-limited on most steps, the unit completion ratio does not fall, and
no episode ended in a no-candidate branch the base arm avoided. What changed
is which candidate a truncated search settles on, and so which trajectory is
taken.

The constraint is therefore the one already on the books: under the
known-defective utility, changing which candidates the search surfaces
reshuffles trajectories instead of improving them. **Selection quality is
blocking for coverage work**, and this is now the second measurement saying
so.

Scope: one repeat per cell; the two smallest deltas are on the b001 cases
that carry timing nondeterminism. Local base totals (83 / 104.742) are below
the registered development baseline (88 / 114.6) because the search is
deadline-limited and absolute totals are machine-dependent - only base-vs-arm
inside one run is comparable, which matters especially for a change whose
whole effect is about what a deadline truncates.

This rejects the interleave as an *unconditional default*. It does not
retract the coverage hole, which is measured and real, and the `b000-k40`
gain is that hole being closed where closing it helps. A targeted form -
interleaving only when the search is actually starving - is a different
design rather than a tuning of this one, and is untested.
