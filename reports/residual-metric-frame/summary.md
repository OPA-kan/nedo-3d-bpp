# Residual metric: the two coordinate frames, and what they cost

- Verdict: **optimizer_gain_survives_one_frame**

| board set | boards | mean delta as reported | mean delta in one frame | boards > 0 reported | boards > 0 one frame |
|---|---:|---:|---:|---:|---:|
| all | 363 | +0.074377 | +0.072051 | 361 | 361 |
| multi-container | 236 | +0.075035 | +0.071457 | 236 | 236 |
| single-container (control) | 127 | +0.073155 | +0.073155 | 125 | 125 |

delta_as_reported is the acceptance guard's own number: mean nearest-neighbour distance of the positive arm minus the paired control, over settled x_plus in WORLD coordinates. delta_single_frame is the same quantity with settled positions shifted back into their own container's frame, so container membership is carried once, by container_index, instead of also by a 2.5 m offset in the position term. Single-container boards are unaffected by construction and are reported separately as the control on this control.
