# Stride x endgame rollout saturation

- snapshots: 8 (usable 8)
- depth: 3
- late band: step >= 10
- immediate Top-K budget: 4096 attempts
- Top-K: 3

`baseline` is the shipped shadow setting. `stride-S` holds the attempt budget fixed and widens the anchor scan; `budget-N` widens the budget at stride 1 and acts as the reach oracle.

## all (8 snapshots)

| arm | stride | attempts/step | non-degenerate | rate | any future placement | recovered baseline ties | mean ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| baseline | 1 | 64 | 5 | 0.625 | 5 | 0/3 | 105.069 |
| stride-2 | 2 | 64 | 6 | 0.75 | 6 | 1/3 | 104.538 |
| stride-4 | 4 | 64 | 6 | 0.75 | 6 | 1/3 | 140.834 |
| stride-8 | 8 | 64 | 8 | 1.0 | 8 | 3/3 | 250.949 |
| budget-512 | 1 | 512 | 8 | 1.0 | 5 | 3/3 | 2215.012 |

## early_step_lt_10 (1 snapshots)

| arm | stride | attempts/step | non-degenerate | rate | any future placement | recovered baseline ties | mean ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| baseline | 1 | 64 | 0 | 0.0 | 0 | 0/1 | 41.89 |
| stride-2 | 2 | 64 | 1 | 1.0 | 1 | 1/1 | 71.781 |
| stride-4 | 4 | 64 | 1 | 1.0 | 1 | 1/1 | 296.091 |
| stride-8 | 8 | 64 | 1 | 1.0 | 1 | 1/1 | 276.535 |
| budget-512 | 1 | 512 | 1 | 1.0 | 0 | 1/1 | 1982.912 |

## late_step_ge_10 (7 snapshots)

| arm | stride | attempts/step | non-degenerate | rate | any future placement | recovered baseline ties | mean ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| baseline | 1 | 64 | 5 | 0.7143 | 5 | 0/2 | 114.095 |
| stride-2 | 2 | 64 | 5 | 0.7143 | 5 | 0/2 | 109.218 |
| stride-4 | 4 | 64 | 5 | 0.7143 | 5 | 0/2 | 118.655 |
| stride-8 | 8 | 64 | 7 | 1.0 | 7 | 2/2 | 247.293 |
| budget-512 | 1 | 512 | 7 | 1.0 | 5 | 2/2 | 2248.17 |

## Interpretation boundary

These are static-proxy rollouts on saved states, not PyBullet counterfactuals. Non-degeneracy is a property of the measurement, not a score: an arm that discriminates more is not thereby a better policy. The immediate Top-K is reconstructed under a fixed attempt budget and is not a replay of any specific deadline-limited live search, so these rates are comparable across arms but not directly equal to the live shadow rates from the enforce run.
