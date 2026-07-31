# Loss structure: official safe judgment vs rotation magnitude

- release rows with settle metrics: 1180 (all non-holdout datasets; exploratory, not frozen-split)

| angle band (deg) | n | not_placed_safe rate | median displacement (m) |
|---|---:|---:|---:|
| 0-5 | 641 | 0.050 | 0.052 |
| 5-10 | 64 | 0.062 | 0.116 |
| 10-20 | 83 | 0.120 | 0.145 |
| 20-30 | 109 | 0.165 | 0.172 |
| 30-45 | 33 | 0.364 | 0.243 |
| 45-60 | 58 | 1.000 | 0.328 |
| 60-80 | 29 | 1.000 | 0.563 |
| 80-100 | 131 | 1.000 | 0.554 |
| 100-181 | 32 | 1.000 | 0.690 |

## Below the rotation threshold (<30 deg)

- rows: 897, unsafe rate 0.071
- median displacement among unsafe 0.443 m vs safe 0.062 m: low-angle failures are displacement (slide) failures, i.e. the unresolved d_xy channel, not small rotations.

## Reading

- The official judgment is close to a step function of angle: every band at or above 45 deg is unconditionally unsafe, 30-45 deg is mixed, and below 30 deg the rate is small and displacement-driven. A damage model that grows smoothly with rotation magnitude has little room: the label-side loss is effectively binary in angle with a threshold near 45 deg.
- rotated_over_30 is therefore a slightly conservative but structurally faithful proxy for the angle channel of the official loss.
- The remaining loss mass below the threshold belongs to the slide channel (d_xy), which stays unresolved -- prioritizing it above rotation-magnitude modelling.

