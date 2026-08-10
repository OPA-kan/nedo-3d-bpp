# Residual-state diversity physical pilot

- Dataset: `20260810_083315-b000-k20-weighted-class_aware-shadow-0fb74669-df2406576143`
- Sampling mode: `residual_diversity_safe_split`
- Steps measured: 3
- Steps with positive proxy/physical NN-distance delta: 3/3
- Mean physical NN-distance delta: 0.02165367149246146
- Acceptance verdict: **pass**
- Failed guards: []

| step | population | replayed | proxy ΔNN | physical ΔNN | physical Δcells | Δitems | Δitem-pose | safe pool | positive | negative | Δsettled | Δsafe |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 3 | 1776 | 87 | 0.02212334123906487 | 0.030116346588651907 | 1 | 1 | 4 | 55 | 30 | 0 | 0 | 0 |
| 6 | 3001 | 42 | 0.02753632463760544 | 0.01739643456692197 | 1 | 2 | 0 | 22 | 13 | 7 | 0 | 0 |
| 9 | 4749 | 41 | 0.02268008153862769 | 0.017448233321810502 | 0 | 2 | 0 | 16 | 12 | 15 | 0 | 0 |

Positive physical distance delta means the sampled observed settle afterstates are more dispersed. It is a dataset-coverage result, not evidence of a better live policy or score.
