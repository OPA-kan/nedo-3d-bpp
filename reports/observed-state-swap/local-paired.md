# Observed-state swap optimizer — local paired arms

Local, single-machine rebuild of the two condition cells that failed the
frozen 3x matrix in Actions run `31380879143`. Each cell was built twice from
the same configuration: once with the control-seeded observed-state swap
optimizer and once with `--observed-swap-rounds 0`, which restores the
unseeded greedy construction that produced the failures.

**This is not the matrix run.** All arms were built one at a time on one
4-core machine, and the policy is wall-clock bound (`--policy-timeout 8`). The
candidate population is therefore not reproducible run to run: three builds of
`m-single-empty-noshelf` step 9 enumerated 5849, 6211 and 3219 candidates. Only
arms that enumerated the *same* population are a paired comparison; the rest
are separate measurements of separate states and are reported as such. The
condition matrix on `ubuntu-24.04` remains the measurement of record.

Command per arm:

```
python scripts/build_replay_dataset.py \
  --config <scenario>.json --case m-<scenario> --steps <step> \
  --per-stratum 4 --sampling-mode residual_diversity_safe_split \
  --overdraw-factor 3 --risk-gate-mode shadow --skip-optimize \
  --observed-swap-rounds {64,0}
```

## Matched pair — `m-single-empty-shelf` step 15

Both arms enumerated 1244 candidates, produced a 52-row safe union, drew the
identical 13-row paired control, and produced the identical negative-risk arm.
The construction of the positive arm is the only difference.

| arm | ΔmeanNN | ΔminNN | Δitems | Δitem-pose | Δcells | Δplaced-safe | swaps |
|---|---:|---:|---:|---:|---:|---:|---:|
| swap optimizer | **+0.080765** | +0.078368 | +2 | +2 | +2 | 0 | 11 / 12 rounds |
| greedy (`rounds 0`) | +0.001029 | +0.075703 | +3 | +2 | -1 | 0 | — |

The same cell reported **-0.017559** in run `31380879143`. The seeded search
started at exactly `+0.000000` and terminated on `no_improving_swap`.

The greedy arm covers one more unique item. That is the seed's cost: pinning
the control consumes stratum capacity the semantic matching would otherwise
spend on unseen items. Both arms clear the semantic guards, which ask only for
a non-negative delta against the control.

## Unmatched arms — `m-single-empty-noshelf` step 9

Every build of this cell enumerated a different population, so these three
rows are three states, not three treatments of one state.

| arm | population | safe union | positive / control | ΔmeanNN | ΔminNN | Δitems | Δitem-pose | swaps |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| swap optimizer | 5849 | 91 | 26 / 26 | +0.020935 | -0.000013 | 0 | +1 | 7 / 8 rounds |
| swap optimizer (repeat) | 6211 | 75 | 21 / 21 | +0.053035 | -0.002113 | +1 | 0 | 14 / 15 rounds |
| greedy (`rounds 0`) | 3219 | 35 | 12 / 12 | +0.011890 | 0.000000 | +1 | 0 | — |

The same cell reported **-0.004446** in run `31380879143`.

## What the four seeded arms show

- Every seeded arm started at a measured delta of exactly `+0.000000`. The
  control fitted the stratum quota in all four, so the seed and the control
  were the same set and the paired statistic cancelled.
- Every seeded arm terminated on `no_improving_swap`, not on the round budget,
  so the 64-round cap was not the binding constraint.
- Semantic coverage never fell during a search: unique items moved 10→10, 5→6,
  6→7 and 7→9, and item-orientations 19→20, 10→10, 7→8 and 11→13.
- Minimum nearest-neighbour distance is not tracked by the search and moved
  slightly negative in both no-shelf arms (-0.000013 and -0.002113). The
  acceptance guard does not read it. It is reported here so a mean gain
  bought with a minimum loss stays visible.
- Cost is negligible against replay: the largest search evaluated 2738
  candidate swaps and 144 exact objective re-derivations, next to hundreds of
  full PyBullet settles in the same step.

## What this does not establish

The matrix has not been rerun. Two cells rebuilt locally on an unstable
population say the mechanism works on the states they happened to reach; they
do not say the four-condition guard passes. Nothing here is evidence about the
live policy, placed count, fill, or the official score.
