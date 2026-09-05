# Paired comparison: ladder-core-repeat minus ladder-core

Scenes paired: 48

Negative control (same arm both sides): **PASS: identical step for step**

Leading placements identical (item, container, orientation, pose within 2 cm): mean 21.7 steps per scene

End reasons ladder-core: `{'declined': 43, 'settle': 5}`
End reasons ladder-core-repeat: `{'declined': 43, 'settle': 5}`

| metric | better is | mean A | mean B | mean diff | 95% CI | better / equal / worse | evidence |
|---|---|---:|---:|---:|---|---|---|
| placed_count | up | 20.67 | 20.67 | +0 | [+0, +0] | 0 / 48 / 0 | none |
| fill_volume | up | 22.76 | 22.76 | +0 | [+0, +0] | 0 / 48 / 0 | none |
| fill_evaluator_tolerant | up | 20.61 | 20.61 | +0 | [+0, +0] | 0 / 48 / 0 | none |
| fill_evaluator_shipped | up | 13.12 | 13.12 | +0 | [+0, +0] | 0 / 48 / 0 | none |
| com_z_above_floor_ratio | down | 0.3215 | 0.3215 | +0 | [+0, +0] | 0 / 48 / 0 | none |
| priority_covered | down | 0 | 0 | +0 | [+0, +0] | 0 / 48 / 0 | none |
| priority_misrouted | down | 0 | 0 | +0 | [+0, +0] | 0 / 48 / 0 | none |
| soft_covered | down | 0.1458 | 0.1458 | +0 | [+0, +0] | 0 / 48 / 0 | none |
| shake_mean_shift | down | 0.03126 | 0.03126 | +0 | [+0, +0] | 0 / 48 / 0 | none |
| shake_topples | down | 0.1875 | 0.1875 | +0 | [+0, +0] | 0 / 48 / 0 | none |
| shake_peak_kinetic_energy | down | 12.17 | 12.17 | +0 | [+0, +0] | 0 / 48 / 0 | none |
| policy_time_max | timing | 4.032 | 4 | -0.03169 | [-0.0774, +0.005483] | 0 / 0 / 0 | timing-only |

`evidence` is `none` whenever the interval contains zero.  A count of scenes that moved is not evidence on its own.  `timing-only` rows are wall clock and depend on the machine.
