# The platform's five components against the bench, refit over v18..v49

(Deep-dive report; scripts in the session scratchpad `deep/platform/`: summarize.py, common.py, table.py, tables.py, fits.py, q2.py, q3.py, deltas.py, lattice.py.)

Sources: `reports/submission/official-results.md` (platform results), `reports/bench/*/` (per-episode records), `docs/submission.md` and `reports/wedge/findings.md` (which records belong to which build), `simulator/README.md` "評価指標".

Definitions: counted episode = placed >= total//2 + 1; credited soft share = (soft_count - soft_covered) / the stream's soft total; credited priority share = (priority_count - covered - misrouted) / the stream's priority total; cog_c = 100 x (1 - com_z_above_floor_ratio) over counted bench episodes; bench values are the mean of the three tasks' 48-scene sample suites; the total's weights 2/7, 3/14, 3/14, 1/7, 1/7 reproduce every reported total to 0.01.

## 0. Key finding: stability counts how many episodes are over the threshold

Every platform stability score from v1 to v49 equals **4.175 x k** for a whole number k: 29 of 31 builds within +-0.2 of that; the exceptions v24 (+0.51) and v49 (-0.84). k climbs: 9 (v7), 11 (v1/v5/v24), 13 (v12/v14), 14 (v19/v25), 15 (v18-v29), 18 (v31-v40), 19 (v43/v45/v46/v49); the builds that lost one crossing sit at 17 (v34, v41) and 18 (v44). One counted episode's share of stability stayed at 4.175 +- 0.01 across very different loads.

- k is the platform's number of counted episodes: every documented single-crossing event is a step of exactly one in k (v44, v41, v34, v19, v25 each lost one; v31 gained three; v43 gained one).
- N, the platform's number of episodes, is at least 19 (k reached 19) and at most 23 (one episode's stability cannot exceed 100). The simplest reading is N = 19: the placed fraction is at the level of the bench suites that cross 48 of 48; under N = 19 the platform's cog per counted episode is about 64, close to the bench's 62 (under N = 23 it would be 79); v49 placed more items and k did not move.
- Each platform episode is about 1/19 (5.3 %) of every gated component.

## 1. Data table

(k = stab / 4.175; X = bench crossings of 48 on the sample suites; soft/prio cred. = credited shares over counted episodes; hard X = mean over hard C/B/A; hard2 X = mean over hard2 C/B; * = an inferred record mapping.)

| build | records C / B / A | fill | cog | stab | place | soft | frac | total | k | b.fill | b.frac | X C/B/A | b.cog_c | soft cred. | prio cred. | topples/ep | KE | hard X | hard2 X |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|
| v18 | v18-core-c / v18-core-b / v18-core-a | 34.82 | 54.83 | 62.69 | 35.60 | 19.85 | .5526 | 43.05 | 15 | 33.70 | .529 | 9/28/45 | 63.31 | 38.8 | 61.0 | .22 | 20.7 | - | - |
| v19 | v18-core-c / v18-core-b / v19a-core-a * | 34.82 | 50.32 | 58.50 | 30.05 | 20.20 | .5558 | 40.45 | 14 | 34.09 | .534 | 9/28/46 | 62.79 | 38.5 | 61.9 | .29 | 21.1 | - | - |
| v24 | v24s8-core-c/-b/-a | 31.78 | 40.59 | 46.43 | 24.05 | 37.90 | .5447 | 36.58 | 11 | 36.03 | .579 | 23/45/43 | 62.34 | 49.8 | 53.4 | .25 | 20.9 | - | - |
| v25 | v18fix-core-c / -b / v25r-core-a * | 35.10 | 50.59 | 58.47 | 29.30 | 20.60 | .5585 | 40.53 | 14 | 33.39 | .525 | 9/27/44 | 63.74 | 39.7 | 60.5 | .22 | 23.0 | - | - |
| v26 | shadow2-core / -b / -a | 35.85 | 53.37 | 62.55 | 38.45 | 25.35 | .5752 | 44.20 | 15 | 34.09 | .536 | 10/30/45 | 63.36 | 39.9 | 61.4 | .25 | 20.0 | - | - |
| v27 | presort-core / -b / -a | 36.18 | 52.95 | 62.64 | 39.55 | 25.90 | .5816 | 44.46 | 15 | 34.79 | .549 | 16/34/45 | 63.48 | 43.7 | 62.6 | .25 | 20.9 | - | - |
| v29 | pocket-core / -b / pocket2-core-a | 36.29 | 53.22 | 62.69 | 39.75 | 28.30 | .5848 | 44.93 | 15 | 35.31 | .557 | 20/35/44 | 63.05 | 45.3 | 63.8 | .27 | 19.9 | - | - |
| v31 | count4-core / -b / -a | 37.90 | 63.55 | 75.22 | 46.85 | 36.35 | .6104 | 52.45 | 18 | 36.47 | .575 | 37/46/47 | 63.26 | 43.9 | 62.4 | .32 | 21.7 | - | - |
| v32 | strictms-core / v33-core-b / strictfirst-core-a * | 38.08 | 63.31 | 75.16 | 48.50 | 36.60 | .6148 | 52.71 | 18 | 35.88 | .567 | 41/48/48 | 63.50 | 43.1 | 65.7 | .29 | 21.2 | - | - |
| v33 | v33-core / -b / -a | 37.81 | 63.39 | 75.21 | 44.35 | 35.65 | .6113 | 51.93 | 18 | 36.81 | .576 | 48/48/46 | 62.82 | 42.2 | 66.3 | .19 | 23.2 | - | - |
| v34 | strictms-core / v33-core-b / v34-core-a * | 36.36 | 60.21 | 71.17 | 45.95 | 38.80 | .6023 | 50.65 | 17 | 35.79 | .568 | 41/48/48 | 63.65 | 43.8 | 66.0 | .28 | 20.8 | - | - |
| v36 | v33-core / v33-core-b / strictfirst-core-a * | 37.96 | 63.23 | 75.19 | 47.80 | 36.20 | .6140 | 52.51 | 18 | 36.47 | .577 | 48/48/48 | 63.18 | 43.9 | 67.7 | .21 | 20.4 | - | - |
| v37 | same as v36 * | 38.01 | 63.27 | 75.26 | 48.25 | 36.75 | .6141 | 52.69 | 18 | 36.47 | .577 | 48/48/48 | 63.18 | 43.9 | 67.7 | .21 | 20.4 | - | - |
| v38 | softres-core / -b / -a | 37.95 | 63.26 | 75.15 | 47.80 | 36.45 | .6140 | 52.54 | 18 | 37.07 | .589 | 48/48/48 | 62.94 | 47.1 | 68.1 | .26 | 21.2 | .410 | - |
| v39 | softgate35-core / -b / abase-core-a * | 38.05 | 63.20 | 75.15 | 48.60 | 36.75 | .6153 | 52.71 | 18 | 36.95 | .588 | 48/48/48 | 62.97 | 47.8 | 68.1 | .27 | 22.1 | .417 | - |
| v40 | softgate35-core / -b / v40c-core-a | 37.85 | 63.53 | 75.19 | 47.60 | 36.70 | .6121 | 52.58 | 18 | 36.98 | .591 | 48/48/48 | 62.91 | 49.2 | 68.5 | .31 | 22.9 | .431 | - |
| v41 | near-core / -b / abase-core-a * | 37.04 | 59.51 | 70.87 | 45.20 | 37.40 | .6034 | 50.32 | 17 | 36.99 | .589 | 47/47/48 | 63.07 | 47.8 | 67.9 | .30 | 24.1 | .424 | - |
| v43 | phase2-core / -b / abase-core-a * | 39.18 | 65.08 | 79.28 | 49.55 | 42.20 | .6370 | 55.24 | 19 | 38.80 | .621 | 48/48/48 | 62.07 | 52.5 | 64.5 | .33 | 31.5 | .458 | .359 |
| v44 | seal-core / -b / abase-core-a * | 39.01 | 61.45 | 75.19 | 47.50 | 41.40 | .6348 | 53.13 | 18 | 39.25 | .629 | 48/48/48 | 61.71 | 52.7 | 65.2 | .36 | 28.0 | .479 | .396 |
| v45 | grid2-core / -b / abase-core-a * | 39.18 | 65.04 | 79.23 | 49.45 | 42.30 | .6370 | 55.22 | 19 | 38.73 | .620 | 48/48/48 | 62.06 | 52.3 | 64.7 | .26 | 24.2 | .431 | .385 |
| v46 | grid2-core / -b / adrop-core-a | 39.14 | 65.66 | 79.26 | 49.45 | 42.30 | .6363 | 55.34 | 19 | 39.04 | .625 | 48/48/48 | 62.00 | 53.4 | 65.2 | .29 | 24.7 | .451 | .385 |
| v49 | bandnt-core / -b / adrop-core-a | 39.65 | 64.25 | 78.48 | 49.45 | 46.50 | .6475 | 55.62 | 19 | 39.52 | .633 | 48/48/48 | 61.70 | 54.0 | 62.5 | .38 | 28.2 | .514 | .490 |
| v50 | gate0-core / -b / adrop-core-a | - | - | - | - | - | - | - | - | 39.62 | .634 | 48/48/48 | 61.91 | 54.4 | 63.5 | .26 | 24.5 | - | .474 |

Inferred mappings: v19 and v25 use v18's B/C records (Task A changes only); v32's B uses `v33-core-b` (the record named for v32's B carries a later configuration); v34 uses v32's B/C; v36 and v37 share records; v39, v41, v43, v44, v45 use `abase-core-a` for A; v44 uses `seal-*`; v45 shares v46's B/C records. Left out: v28, and builds before v18. With the old mapping the numbers reproduce the findings' H1 table (v18 21.1 / 35.9 / 36.4; v31 39.2 / 57.0 / 57.2).

## 2. Which bench quantity tracks each component

Each build one point; least squares over all 22 builds and over the 15 from v31 on; gated components fitted per counted episode (component / k).

| component | best tracker | slope | r (all / v31+) | rmse | what does not track it |
|---|---|---|---|---|---|
| fill | bench fill | 0.80 (all); 0.60 (v31+); 0.76 without v24 | .77 / .86 | 1.19 / .43 | - |
| cog | k x bench cog_c | cog/k = 0.074 cog_c - 1.16, i.e. 1.41 platform cog points per bench point at k = 19 | .60 / .94; cog vs k alone .994 | .02 per episode | H1 gated by the bench's own crossings (.81 all, .07 v31+); plain cog (-.57) |
| stability | k | 4.175 per episode | 1.000 | .19 | topples (.33 / .19), max shift (.52 / .42), peak kinetic energy (.48 / .53); the lattice residual vs topples is carried by v49 alone |
| placement | k x credited priority share | 0.038 per episode (all); 0.011, not significant (v31+) | .72 / .38 | .12 / .05 | gated H1 over v31+: r .02 |
| soft | k x credited soft share | 0.059 per episode (all), 1.13 per bench point; 0.024 (v31+), 0.46 per bench point | .69 / .73 | .30 / .09 | - |

- Fill is the one ungated component and behaves; the outlier is v24 (-5.0).
- Cog is k times a per-episode value that falls about 1.4 times faster than the bench's cog_c (v31 -> v49: bench 63.3 -> 61.7, platform per episode 3.53 -> 3.38, i.e. 67.1 -> 64.3 at k = 19). H1 holds in level, not in slope.
- Stability does not track cog: their .995 correlation is k on both sides; at fixed k they separate (v44 cog -1.8 per episode with stability flat; v46 cog +0.62 with stability +0.03).
- Placement is flat: placement / k has been 2.60-2.70 since v26; it reads exactly 49.45 on v45, v46 and v49 while the bench's credited priority share moved C -3.6 and B -4.6 (the count pass's covers). Since v31 it moved only with k and with Task A changes (v32 +1.65, v33 -4.15, v40 -1.0).
- Soft follows H1 in structure (v24: +18 on the platform, +16 under H1); since v31 it moves at less than half the bench's rate, with v49 the big miss.

Residuals from the v31+ fits (gated residuals x k):

| build | k | stab - 4.175k | fill | cog | placement | soft |
|---|---:|---:|---:|---:|---:|---:|
| v31 | 18 | +.07 | +.25 | +.09 | +.19 | -.45 |
| v32 | 18 | +.01 | +.78 | -.47 | +1.15 | +.13 |
| v33 | 18 | +.06 | -.04 | +.53 | -3.11 | -.45 |
| v34 | 17 | +.20 | -.89 | -.20 | +1.18 | +4.06 |
| v36 | 18 | +.04 | +.31 | -.12 | +.04 | -.62 |
| v37 | 18 | +.11 | +.36 | -.08 | +.49 | -.07 |
| v38 | 18 | .00 | -.06 | +.23 | -.05 | -1.75 |
| v39 | 18 | .00 | +.11 | +.14 | +.75 | -1.73 |
| v40 | 18 | +.04 | -.10 | +.54 | -.33 | -2.39 |
| v41 | 17 | -.10 | -.92 | -.18 | +.05 | +1.04 |
| v43 | 19 | -.05 | +.15 | -.22 | -.17 | -.59 |
| v44 | 18 | +.04 | -.30 | +.07 | +.26 | +.80 |
| v45 | 19 | -.09 | +.18 | -.25 | -.32 | -.40 |
| v46 | 19 | -.06 | -.04 | +.45 | -.42 | -.89 |
| v49 | 19 | -.84 | +.19 | -.54 | +.17 | +3.07 |

The platform moved and the bench did not: v49 soft +4.2 against a bench +0.53 (C -0.9, B +2.5), cog -1.41 against -0.30, stability -0.84 off the lattice with k unchanged (the only clear case); v46 cog +0.62 against -0.06; v34 soft +2.2 against about +0.4; v43 one platform crossing while every bench suite stayed 48 of 48. The bench moved and the platform did not: v38-v40 bench soft 43.9 -> 49.2, platform 36.2-36.75; v46 -> v49 bench credited priority -2.7, platform placement 0; v44 the best hard C / hard2 C crossing shares, yet a platform crossing lost; v24 bench crossings 82 -> 111 of 144, k 15 -> 11; v33 bench placement +2, platform -4.15 (the Task A leak).

## 3. Does the platform average over counted episodes?

Yes, but the bench's own crossing counts do not say which platform episodes count.

| predictor of the platform total | r, all 22 | rmse | r, v31+ | rmse |
|---|---:|---:|---:|---:|
| plain mean, no gating | .873 | 2.69 | .613 | 1.25 |
| H1 gated by the bench's crossings | .893 | 2.49 | .502 | 1.36 |
| H1 gated by the platform's k/19, bench values per counted episode | .995 | .56 | .970 | .39 |
| platform k alone | .989 | .83 | .982 | .30 |
| platform placed fraction alone | .971 | 1.33 | .936 | .56 |

What predicts k: the platform's placed fraction (r .944, about 0.67 of a crossing per 0.01), the bench sample crossing share (.82), the hard suites' share (.49, 9 builds), the hard2 share (.08, 5 builds). v49's +11 and +9 hard2 crossings bought no platform crossing; v44's best hard shares came with a lost one.

The placed fractions on v49: core C .617 (c1 .624, c1s .598, c2 .599, c2p .646), core B .647, core A .635 (all 48 of 48 with margins +4 to +12); hard C / B / A .513 / .513 / .529 (23 / 24 / 27 of 48); hard2 C .495 (sample .574, stretch .463, edge .38, fill-only .26), hard2 B .505. The platform's 0.6475 is at or above the sample suites' 0.633; no mixture with hard2-like streams can reach it. So the platform's streams are sample-like (about 0.54 of the container volume, sample-suite margins); since v43 every platform episode counts (k = 19 = N) with one edge episode within one or two items of its threshold (v44 lost it with the fraction falling 0.0022; v45 regained it). The stretch, edge and fill-only strata are not the platform's population. Under N = 19 no crossing is left to gain; any crossing lever can only lose one (-2.34 each).

## 4. Prices, the v49 lever, the v50 prediction

Prices in total points; a "bench point" is one point of the three-task mean (one task's suite alone counts a third). Structural prices use N = 19.

| unit | refit, v31 on | refit, all | old price |
|---|---:|---:|---:|
| one platform crossing | 2.34 (cog .72, stability .89, placement .37, soft .35) | - | about 2.4 |
| observed one-crossing steps | v44 -2.11, v41 -2.39, v34 -2.06, v19 -2.61, v25 -2.53 (v31 +7.52 for +3) | - | - |
| +1 bench fill point | .170 (one task .057) | .228 (.076) | .287 (.096) |
| -0.01 CoM ratio, all three tasks | .30 (one task .10) | .29 (.10) | 1.7 (.57) |
| +0.01 credited soft share, one task's suite | .022 | .054 | .047 |
| +0.01 credited priority share, one task's suite | .010 (not significant) | .034 | .048 |
| one uncovered soft box in one platform episode (stream soft total S) | 100/(7 x 19 x S) = .050 at S = 15 | - | 14/S to its episode |
| one priority box in one platform episode (priority total P) | .150 at P = 5 | - | 14/P to its episode |
| +1 topple per episode, all three tasks | -.48 resting on v49 alone; -.07 without it | -.48 | about -.37 |

CoM is about 6 times cheaper than the old price (the old 1.7 came from v19's step, which was a lost crossing). A crossing is still worth 2.3-2.4, but the unit is 1/19 of the episodes, and bench crossings map to platform crossings only when they hit the platform's marginal episode. Soft is underpriced by the bench share but the structural per-box price is confirmed by v49. Priority has not paid for any B/C lever since v31. Topples have no reliable price.

Does the refit explain v49 (bench deltas three-task means, A unchanged)?

| comparison | dfill | dcog_c | dtopples/ep | dpriority cred. | dsoft cred. | refit fill / cog / stab / place / soft -> total |
|---|---:|---:|---:|---:|---:|---|
| v46 -> v49 (`grid2-*` -> `bandnt-*`) | +.47 | -.30 | +.09 | -2.72 | +.53 | +.28 / -.42 / -.20 / -.59 / +.24 -> -.10 |
| v48 -> v49, the band alone | +.22 | -.13 | +.05 | -1.97 | +.92 | +.13 / -.18 / -.11 / -.43 / +.42 -> -.03 |
| platform, observed | | | | | | +.51 / -1.41 / -.78 / 0 / +4.20 -> +.28 |

Not from the sample-suite deltas (soft underpredicted 17 times, cog 3.4 times, placement the wrong sign; the hard suites do not close it). What explains v49 is the structural per-item price with k fixed: soft +4.2 at k = 19 is +0.22 per counted episode, about one more credited soft box per B/C episode (100/15 x 2/3 = 4.4); fill +0.51 is about 0.6 of a soft box's volume per B/C episode; the fraction +0.011 is about one item per B/C episode. On the platform the band's extra placement was a soft box; on the bench it was mostly hard (C placed +1.17 for +0.1 soft box, B +0.46 for +0.3). Cog is not explained: -2.1 cog points per B/C episode means a CoM ratio about 0.02 higher, where one 9 kg box at 0.9 m explains 0.004 and the bench read +0.007 (C) / +0.002 (B).

v50 prediction (`gate0-core`, `gate0-core-b`, A unchanged) against v49:

| comparison | dfill | dcog | dstab | dplace | dsoft | dtotal |
|---|---:|---:|---:|---:|---:|---:|
| bench, gate0 vs bandnt | +.10 | cog_c +.21 | topples -.125 | prio +.99 | soft +.46 | |
| refit, v31 on | +.06 | +.29 | +.28 | +.22 | +.21 | +.20 |
| refit, all builds | +.08 | +.28 | +.28 | +.71 | +.52 | +.32 |
| refit, v31 on, against the concurrent v49 rerun (`estbase-*`) | +.10 | +.37 | +.09 | +.12 | +.04 | +.15 |

The stability +0.28 assumes v49's -0.84 came from the Task B topples the band added (bench B topples .375 -> .604 under the band, .271 under gate0); without it the total is about +0.15. Soft is the swing: on C the gate halves the covered soft boxes (45 -> 20) and lifts the credited share +2.8, on B the share falls 1.4; at v49's platform-to-bench ratio of about 8 the soft could move +3.6 (+0.5 total) but B's loss could amplify the same way. With k already 19 a crossing can only be lost; the sample suites stay 48 of 48; the deterministic hard2 C pair nets -1 of 96; the official sample C scene flips between 25 and 24 placed and stays above its threshold of 22. Prediction: v50 about v49 + 0.2 (about 55.8), range -0.1 to +0.7 on the continuous terms, -2.3 per platform crossing lost.

## 5. Headroom per unit of bench movement (N = 19)

| component | v49 value | gap to 100 | gap in total points | total points per bench point (v31 on) | platform total per typical lever |
|---|---:|---:|---:|---:|---|
| crossings | 19 of N | 0 (at most 4 if N <= 23) | 0 (at most 9.4) | 2.34 per platform crossing | can only be lost |
| cog | 64.3 | 35.7 | 7.7 | .30 | .03-.09 |
| fill | 39.7 | 60 | about 17 (limited by geometry) | .17 | .02-.09 |
| soft | 46.5 | 53.5 | 7.6 | .065 per bench share point; .05 per soft box per episode | .02-.07 by bench share; +0.6 seen in v49 |
| placement | 49.45 | 50.6 | 7.2 | .03 (not significant) | about 0 |
| stability | about 79 per episode, fixed | not reachable | - | moves only with k | - |

The crossing channel is exhausted: it produced every large step (v12, v18, v31, v43), and k has been 19 since v43. Cog pays the most per bench point, but the bench's cog barely moves (1.9 points in 18 builds). Soft has the most usable headroom, and the platform responds at the structural rate: judge soft levers by uncovered soft boxes added per B/C episode, not by the suite share; the targets are the leftover soft cargo in Task B's pool and the soft surfaces at height. Placement has the least headroom per unit of bench movement (frozen at 49.45; only Task A changes or crossings move it). Stability is not a lever.

## 7. The v50 check (added after the platform scored v50)

v50 scored 56.04, +0.41 against v49: fill -1.03, cog +0.57, stability -0.29, placement +0.95, soft +3.60, fraction 0.6475 -> 0.6446, policy 6.75 s. The total sits inside the predicted range (-0.1 to +0.7) above the point prediction (+0.2), and soft moved by the upper case named in section 4 (+3.6). Three claims above are corrected by it: placement is not frozen (it moved with no Task A change and no crossing, so a B/C component exists); the stability +0.28 assumption (v49's topples leaving with the gate) was wrong in sign (-0.29, the continuous part now -1.14 under the lattice); fill fell with the fraction flat, so a soft lever's price must carry the hard volume it displaces (here -0.30 weighted against soft's +0.51). The lattice claim holds: k = 19 of 19, no crossing moved.
