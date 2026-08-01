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

## Result

<!-- filled in from the screening run -->
