# Loss structure: official safe judgment vs rotation magnitude

- release rows with settle metrics: 1121 (all non-holdout datasets; exploratory, not frozen-split)

| angle band (deg) | n | not_placed_safe rate | median displacement (m) |
|---|---:|---:|---:|
| 0-5 | 609 | 0.053 | 0.052 |
| 5-10 | 62 | 0.065 | 0.117 |
| 10-20 | 82 | 0.122 | 0.145 |
| 20-30 | 107 | 0.159 | 0.171 |
| 30-45 | 32 | 0.375 | 0.248 |
| 45-60 | 45 | 1.000 | 0.307 |
| 60-80 | 26 | 1.000 | 0.594 |
| 80-100 | 128 | 1.000 | 0.558 |
| 100-181 | 30 | 1.000 | 0.678 |

## Below the rotation threshold (<30 deg)

- rows: 860, unsafe rate 0.073
- median displacement among unsafe 0.432 m vs safe 0.062 m: low-angle failures are displacement (slide) failures, i.e. the unresolved d_xy channel, not small rotations.

## Reading

- The official judgment is close to a step function of angle: every band at or above 45 deg is unconditionally unsafe, 30-45 deg is mixed, and below 30 deg the rate is small and displacement-driven. A damage model that grows smoothly with rotation magnitude has little room: the label-side loss is effectively binary in angle with a threshold near 45 deg.
- rotated_over_30 is therefore a slightly conservative but structurally faithful proxy for the angle channel of the official loss.
- The remaining loss mass below the threshold belongs to the slide channel (d_xy), which stays unresolved -- prioritizing it above rotation-magnitude modelling.

