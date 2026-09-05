# Paired comparison: stable-wall8 minus stable

Scenes paired: 48

Leading placements identical (item, container, orientation, pose within 2 cm): mean 2.8 steps per scene

End reasons stable: `{'declined': 46, 'settle': 2}`
End reasons stable-wall8: `{'declined': 47, 'settle': 1}`

| metric | better is | mean A | mean B | mean diff | 95% CI | better / equal / worse | evidence |
|---|---|---:|---:|---:|---|---|---|
| placed_count | up | 21.77 | 21.35 | -0.4167 | [-1.688, +0.75] | 14 / 18 / 16 | none |
| fill_volume | up | 23.8 | 23.78 | -0.02463 | [-1.354, +1.324] | 14 / 18 / 16 | none |
| fill_evaluator_tolerant | up | 21.83 | 21.8 | -0.02758 | [-1.23, +1.173] | 18 / 11 / 19 | none |
| fill_evaluator_shipped | up | 14.4 | 13.93 | -0.4675 | [-1.489, +0.5616] | 19 / 4 / 25 | none |
| com_z_above_floor_ratio | down | 0.3362 | 0.329 | -0.00726 | [-0.01826, +0.003764] | 28 / 0 / 20 | none |
| priority_covered | down | 0.0625 | 0.04167 | -0.02083 | [-0.1042, +0.04167] | 2 / 45 / 1 | none |
| priority_misrouted | down | 0 | 0 | +0 | [+0, +0] | 0 / 48 / 0 | none |
| soft_covered | down | 0.125 | 0.1042 | -0.02083 | [-0.1458, +0.1042] | 5 / 39 / 4 | none |
| shake_mean_shift | down | 0.03089 | 0.03233 | +0.001437 | [-0.00509, +0.007341] | 18 / 0 / 30 | none |
| shake_topples | down | 0.1458 | 0.2917 | +0.1458 | [-0.0625, +0.375] | 5 / 36 / 7 | none |
| shake_peak_kinetic_energy | down | 13.54 | 11.23 | -2.311 | [-9.265, +4.94] | 28 / 0 / 20 | none |
| policy_time_max | timing | 3.959 | 3.23 | -0.729 | [-1.188, -0.2952] | 0 / 0 / 0 | timing-only |

`evidence` is `none` whenever the interval contains zero.  A count of scenes that moved is not evidence on its own.  `timing-only` rows are wall clock and depend on the machine.
