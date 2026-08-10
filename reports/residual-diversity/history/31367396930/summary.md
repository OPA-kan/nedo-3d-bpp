# Residual-state diversity physical pilot

- Dataset: `20260810_074920-b000-k20-weighted-class_aware-shadow-0fb74669-bb1f27bb75b0`
- Steps measured: 3
- Steps with positive proxy/physical NN-distance delta: 3/3
- Mean physical NN-distance delta: 0.016838857600610102

| step | population | replayed | proxy ΔNN | physical ΔNN | physical Δcells | Δsettled | Δsafe |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 3 | 1776 | 52 | 0.01765787320818553 | 0.02270352242889373 | -2 | 0 | 0 |
| 6 | 3001 | 25 | 0.035426764703427496 | 0.019394283113107647 | 1 | 0 | 0 |
| 9 | 6211 | 45 | 0.02124940426576235 | 0.00841876725982893 | 1 | 0 | -2 |

Positive physical distance delta means the sampled observed settle afterstates are more dispersed. It is a dataset-coverage result, not evidence of a better live policy or score.
