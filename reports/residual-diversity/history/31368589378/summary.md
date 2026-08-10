# Residual-state diversity physical pilot

- Dataset: `20260810_080631-b000-k20-weighted-class_aware-shadow-0fb74669-8fc2ae65b0e5`
- Sampling mode: `residual_diversity_constrained`
- Steps measured: 3
- Steps with positive proxy/physical NN-distance delta: 3/3
- Mean physical NN-distance delta: 0.014635930123647514
- Acceptance verdict: **fail**
- Failed guards: ['unique_items', 'placed_safe']

| step | population | replayed | proxy ΔNN | physical ΔNN | physical Δcells | Δitems | Δitem-pose | Δsettled | Δsafe |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 3 | 1776 | 53 | 0.01833816230746374 | 0.02543839324442744 | -2 | -1 | 0 | 0 | 0 |
| 6 | 3001 | 25 | 0.03625009599757223 | 0.01288820597823015 | 2 | 0 | 0 | 0 | 0 |
| 9 | 6211 | 45 | 0.02460018230600152 | 0.005581191148284953 | 0 | 0 | 0 | 0 | -2 |

Positive physical distance delta means the sampled observed settle afterstates are more dispersed. It is a dataset-coverage result, not evidence of a better live policy or score.
