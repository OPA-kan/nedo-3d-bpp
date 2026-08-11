# Residual metric: the two coordinate frames, and what they cost

- Verdict: **optimizer_gain_survives_one_frame**

| board set | boards | mean delta as reported | mean delta in one frame | boards > 0 reported | boards > 0 one frame |
|---|---:|---:|---:|---:|---:|
| all | 454 | +0.074200 | +0.071780 | 452 | 452 |
| multi-container | 294 | +0.075168 | +0.071431 | 294 | 294 |
| single-container (control) | 160 | +0.072421 | +0.072421 | 158 | 158 |

## the two components the sum was averaging together

Occupancy is where the item landed and in which container; consumption is which item was taken out of the pool. A single Gower sum averages them, and cannot say which one moved.

| board set | mean Δ occupancy | win/tie/loss | mean Δ consumption | win/tie/loss |
|---|---:|---:|---:|---:|
| all | +0.049909 | 452/0/2 | +0.095786 | 294/81/79 |
| multi-container | +0.048838 | 294/0/0 | +0.076124 | 162/62/70 |
| single-container | +0.051877 | 158/0/2 | +0.131914 | 132/19/9 |

delta_as_reported is the acceptance guard's own number: mean nearest-neighbour distance of the positive arm minus the paired control, over settled x_plus in WORLD coordinates. delta_single_frame is the same quantity with settled positions shifted back into their own container's frame, so container membership is carried once, by container_index, instead of also by a 2.5 m offset in the position term. Single-container boards are unaffected by construction and are reported separately as the control on this control.
