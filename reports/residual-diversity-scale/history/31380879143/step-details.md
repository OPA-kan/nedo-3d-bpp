# Observed-afterstate portfolio matrix — step details

Actions run `31380879143`, implementation commit `bf47bc7`, frozen 3x
overdraw. The final safe-positive portfolio used official replay `x_plus`
features for distance; the paired safe-random arm and all semantic/safety
guards were unchanged.

| scenario | step | positive | negative | physical NN delta | minimum NN delta | unique items delta | item-orientation delta | verdict contribution |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| dual-empty | 3 | 30 | 2 | +0.028254 | +0.001672 | 0 | +4 | pass |
| dual-empty | 9 | 13 | 4 | +0.068134 | +0.002848 | +4 | +3 | pass |
| dual-empty | 15 | 13 | 10 | +0.082274 | +0.000788 | +1 | +1 | pass |
| dual-shelf-mixed | 3 | 30 | 3 | +0.038243 | +0.000000 | +1 | +4 | pass |
| dual-shelf-mixed | 9 | 30 | 4 | +0.020220 | +0.000000 | +2 | +4 | pass |
| dual-shelf-mixed | 15 | 34 | 17 | +0.009883 | +0.000137 | +1 | +9 | pass |
| single-empty-noshelf | 3 | 30 | 0 | +0.004485 | +0.001721 | +1 | +4 | pass |
| single-empty-noshelf | 9 | 26 | 18 | **-0.004446** | +0.002102 | 0 | +3 | fail |
| single-empty-noshelf | 15 | 8 | 45 | +0.014803 | 0.000000 | +1 | +1 | pass |
| single-empty-shelf | 3 | 30 | 5 | +0.045339 | +0.001205 | +1 | +8 | pass |
| single-empty-shelf | 9 | 8 | 26 | +0.046843 | +0.190289 | +3 | +1 | pass |
| single-empty-shelf | 15 | 13 | 1 | **-0.017559** | +0.002309 | +4 | 0 | fail |

The selector fixed the previous dual-shelf late-step failure: at step 15 the
physical NN delta changed from `-0.007839` to `+0.009883`, while the
item-orientation delta changed from `-1` to `+9`. It did not establish an
unconditional sampler: two single-container steps still lost **mean** physical
NN distance even though their **minimum** NN distance and semantic coverage did
not regress.

This isolates an objective mismatch. The current construction maximizes
semantic coverage first and then greedily maximizes minimum observed distance;
the acceptance guard compares mean nearest-neighbour distance with an
independent safe-random portfolio. The next experiment should preserve the
control portfolio as a feasible seed and perform observed-state swaps that do
not reduce semantic coverage and directly improve the measured mean-NN
objective. It should not tune overdraw or start model training yet.
