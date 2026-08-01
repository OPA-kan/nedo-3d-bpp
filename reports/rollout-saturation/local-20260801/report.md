# Stride x endgame rollout saturation

- snapshots: 48 (usable 48)
- depth: 3
- late band: step >= 10
- immediate Top-K budget: 4096 attempts
- Top-K: 3

`baseline` is the shipped shadow setting. `stride-S` holds the attempt budget fixed and widens the anchor scan; `budget-N` widens the budget at stride 1 and acts as the reach oracle.

## all (48 snapshots)

| arm | stride | attempts/step | non-degenerate | rate | any future placement | recovered baseline ties | would enforce | mean ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| baseline | 1 | 64 | 10 | 0.2083 | 10 | 0/38 | - | 85.375 |
| stride-2 | 2 | 64 | 15 | 0.3125 | 15 | 5/38 | - | 90.095 |
| stride-2+1 | 2 | 64 | 15 | 0.3125 | 15 | 5/38 | - | 91.959 |
| stride-4 | 4 | 64 | 25 | 0.5208 | 23 | 15/38 | - | 132.481 |
| stride-4+1 | 4 | 64 | 27 | 0.5625 | 24 | 17/38 | - | 137.055 |
| stride-4+2 | 4 | 64 | 26 | 0.5417 | 24 | 16/38 | - | 130.474 |
| stride-4+3 | 4 | 64 | 27 | 0.5625 | 23 | 17/38 | - | 135.857 |
| stride-8 | 8 | 64 | 44 | 0.9167 | 36 | 34/38 | - | 282.781 |
| stride-8+1 | 8 | 64 | 44 | 0.9167 | 33 | 34/38 | - | 283.141 |
| stride-8+2 | 8 | 64 | 44 | 0.9167 | 32 | 34/38 | - | 284.9 |
| stride-8+3 | 8 | 64 | 42 | 0.875 | 32 | 32/38 | - | 280.885 |
| budget-256 | 1 | 256 | 47 | 0.9792 | 14 | 37/38 | - | 1318.675 |
| budget-512 | 1 | 512 | 47 | 0.9792 | 15 | 37/38 | - | 2271.643 |

## early_step_lt_10 (11 snapshots)

| arm | stride | attempts/step | non-degenerate | rate | any future placement | recovered baseline ties | would enforce | mean ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| baseline | 1 | 64 | 2 | 0.1818 | 2 | 0/9 | - | 61.052 |
| stride-2 | 2 | 64 | 6 | 0.5455 | 6 | 4/9 | - | 78.801 |
| stride-2+1 | 2 | 64 | 6 | 0.5455 | 6 | 4/9 | - | 83.27 |
| stride-4 | 4 | 64 | 9 | 0.8182 | 8 | 7/9 | - | 212.201 |
| stride-4+1 | 4 | 64 | 10 | 0.9091 | 8 | 8/9 | - | 217.752 |
| stride-4+2 | 4 | 64 | 9 | 0.8182 | 8 | 7/9 | - | 187.754 |
| stride-4+3 | 4 | 64 | 10 | 0.9091 | 8 | 8/9 | - | 203.124 |
| stride-8 | 8 | 64 | 11 | 1.0 | 8 | 9/9 | - | 334.833 |
| stride-8+1 | 8 | 64 | 11 | 1.0 | 7 | 9/9 | - | 325.716 |
| stride-8+2 | 8 | 64 | 11 | 1.0 | 7 | 9/9 | - | 323.628 |
| stride-8+3 | 8 | 64 | 11 | 1.0 | 7 | 9/9 | - | 339.411 |
| budget-256 | 1 | 256 | 11 | 1.0 | 2 | 9/9 | - | 1059.135 |
| budget-512 | 1 | 512 | 11 | 1.0 | 3 | 9/9 | - | 2001.469 |

## late_step_ge_10 (37 snapshots)

| arm | stride | attempts/step | non-degenerate | rate | any future placement | recovered baseline ties | would enforce | mean ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| baseline | 1 | 64 | 8 | 0.2162 | 8 | 0/29 | - | 92.606 |
| stride-2 | 2 | 64 | 9 | 0.2432 | 9 | 1/29 | - | 93.453 |
| stride-2+1 | 2 | 64 | 9 | 0.2432 | 9 | 1/29 | - | 94.542 |
| stride-4 | 4 | 64 | 16 | 0.4324 | 15 | 8/29 | - | 108.78 |
| stride-4+1 | 4 | 64 | 17 | 0.4595 | 16 | 9/29 | - | 113.064 |
| stride-4+2 | 4 | 64 | 17 | 0.4595 | 16 | 9/29 | - | 113.445 |
| stride-4+3 | 4 | 64 | 17 | 0.4595 | 15 | 9/29 | - | 115.859 |
| stride-8 | 8 | 64 | 33 | 0.8919 | 28 | 25/29 | - | 267.305 |
| stride-8+1 | 8 | 64 | 33 | 0.8919 | 26 | 25/29 | - | 270.484 |
| stride-8+2 | 8 | 64 | 33 | 0.8919 | 25 | 25/29 | - | 273.387 |
| stride-8+3 | 8 | 64 | 31 | 0.8378 | 25 | 23/29 | - | 263.485 |
| budget-256 | 1 | 256 | 36 | 0.973 | 12 | 28/29 | - | 1395.835 |
| budget-512 | 1 | 512 | 36 | 0.973 | 12 | 28/29 | - | 2351.965 |

## Interpretation boundary

These are static-proxy rollouts on saved states, not PyBullet counterfactuals. Non-degeneracy is a property of the measurement, not a score: an arm that discriminates more is not thereby a better policy. The immediate Top-K is reconstructed under a fixed attempt budget and is not a replay of any specific deadline-limited live search, so these rates are comparable across arms but not directly equal to the live shadow rates from the enforce run.
