# Paired comparison: stable-core-repeat minus stable-core

Scenes paired: 48

Negative control (same arm both sides): **PASS: identical step for step**

Leading placements identical (item, container, orientation, pose within 2 cm): mean 22.8 steps per scene

End reasons stable-core: `{'declined': 46, 'settle': 2}`
End reasons stable-core-repeat: `{'declined': 46, 'settle': 2}`

| metric | better is | mean A | mean B | mean diff | 95% CI | better / equal / worse | evidence |
|---|---|---:|---:|---:|---|---|---|
| placed_count | up | 21.77 | 21.77 | +0 | [+0, +0] | 0 / 48 / 0 | none |
| fill_volume | up | 23.8 | 23.8 | +0 | [+0, +0] | 0 / 48 / 0 | none |
| fill_evaluator_tolerant | up | 21.83 | 21.83 | +0 | [+0, +0] | 0 / 48 / 0 | none |
| fill_evaluator_shipped | up | 14.4 | 14.4 | +0 | [+0, +0] | 0 / 48 / 0 | none |
| com_z_above_floor_ratio | down | 0.3362 | 0.3362 | +0 | [+0, +0] | 0 / 48 / 0 | none |
| priority_covered | down | 0.0625 | 0.0625 | +0 | [+0, +0] | 0 / 48 / 0 | none |
| priority_misrouted | down | 0 | 0 | +0 | [+0, +0] | 0 / 48 / 0 | none |
| soft_covered | down | 0.125 | 0.125 | +0 | [+0, +0] | 0 / 48 / 0 | none |
| shake_mean_shift | down | 0.03089 | 0.03089 | +0 | [+0, +0] | 0 / 48 / 0 | none |
| shake_topples | down | 0.1458 | 0.1458 | +0 | [+0, +0] | 0 / 48 / 0 | none |
| shake_peak_kinetic_energy | down | 13.54 | 13.54 | +0 | [+0, +0] | 0 / 48 / 0 | none |
| policy_time_max | timing | 3.959 | 4.056 | +0.0968 | [-0.008657, +0.2033] | 0 / 0 / 0 | timing-only |

`evidence` is `none` whenever the interval contains zero.  A count of scenes that moved is not evidence on its own.  `timing-only` rows are wall clock and depend on the machine.
