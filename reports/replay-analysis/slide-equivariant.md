# Slide S0: equivariant local-frame model vs invariant baseline

- rows 1180 in 33 snapshots; degenerate frames 86
- mean |longitudinal| 0.085 m vs mean |transverse| 0.039 m (mirror symmetry predicts small transverse)
- downhill prior alone gets 0.856 direction accuracy on moving rows

| metric | invariant baseline | equivariant |
|---|---:|---:|
| LOSO Spearman |d_xy| | 0.282 | 0.567 |
| LOSO Spearman d_long | 0.398 | 0.641 |
| direction accuracy (moving) | 0.849 | 0.860 |
| large-slide AUC (LOSO) | 0.718 | 0.787 |
| extrapolation b000 (Spearman |d|) | 0.037 | 0.568 |
| extrapolation b001 (Spearman |d|) | 0.180 | 0.476 |
| extrapolation k10 (Spearman |d|) | 0.714 | 0.437 |
| extrapolation k15 (Spearman |d|) | 0.370 | 0.559 |
| extrapolation k20 (Spearman |d|) | 0.126 | 0.526 |
| extrapolation k30 (Spearman |d|) | 0.203 | 0.399 |
| extrapolation k40 (Spearman |d|) | 0.119 | 0.490 |

