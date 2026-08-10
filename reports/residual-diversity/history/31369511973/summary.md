# Residual-state diversity physical pilot

- Dataset: `20260810_081903-b000-k20-weighted-class_aware-shadow-0fb74669-92a99a139c58`
- Sampling mode: `residual_diversity_global_constrained`
- Steps measured: 3
- Steps with positive proxy/physical NN-distance delta: 3/3
- Mean physical NN-distance delta: 0.03609075418426269
- Acceptance verdict: **fail**
- Failed guards: ['placed_safe']

| step | population | replayed | proxy ΔNN | physical ΔNN | physical Δcells | Δitems | Δitem-pose | Δsettled | Δsafe |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 3 | 1776 | 51 | 0.023322031581220398 | 0.027739259747158768 | -1 | 1 | 4 | 0 | 0 |
| 6 | 3001 | 24 | 0.06194724743538979 | 0.058523505617129615 | 2 | 3 | 1 | 0 | 1 |
| 9 | 6211 | 44 | 0.03750360179618215 | 0.02200949718849969 | 2 | 3 | 1 | 0 | -1 |

Positive physical distance delta means the sampled observed settle afterstates are more dispersed. It is a dataset-coverage result, not evidence of a better live policy or score.
