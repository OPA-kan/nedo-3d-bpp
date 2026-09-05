# Paired comparison: ladder-stable minus ladder

Scenes paired: 48

Leading placements identical (item, container, orientation, pose within 2 cm): mean 2.1 steps per scene

End reasons ladder: `{'declined': 43, 'settle': 5}`
End reasons ladder-stable: `{'declined': 46, 'settle': 2}`

| metric | better is | mean A | mean B | mean diff | 95% CI | better / equal / worse | evidence |
|---|---|---:|---:|---:|---|---|---|
| placed_count | up | 20.67 | 21.77 | +1.104 | [-0.1042, +2.292] | 24 / 11 / 13 | none |
| fill_volume | up | 22.76 | 23.8 | +1.044 | [-0.3149, +2.398] | 24 / 11 / 13 | none |
| fill_evaluator_tolerant | up | 20.61 | 21.83 | +1.218 | [-0.07451, +2.484] | 31 / 5 / 12 | none |
| fill_evaluator_shipped | up | 13.12 | 14.4 | +1.285 | [+0.3489, +2.239] | 30 / 3 / 15 | b-better |
| com_z_above_floor_ratio | down | 0.3215 | 0.3362 | +0.01476 | [+0.004022, +0.02574] | 18 / 0 / 30 | b-worse |
| priority_covered | down | 0 | 0.0625 | +0.0625 | [+0, +0.1458] | 0 / 45 / 3 | none |
| priority_misrouted | down | 0 | 0 | +0 | [+0, +0] | 0 / 48 / 0 | none |
| soft_covered | down | 0.1458 | 0.125 | -0.02083 | [-0.1875, +0.1458] | 5 / 37 / 6 | none |
| shake_mean_shift | down | 0.03126 | 0.03089 | -0.0003676 | [-0.006159, +0.005539] | 29 / 0 / 19 | none |
| shake_topples | down | 0.1875 | 0.1458 | -0.04167 | [-0.2292, +0.125] | 4 / 39 / 5 | none |
| shake_peak_kinetic_energy | down | 12.17 | 13.54 | +1.373 | [-3.511, +6.91] | 25 / 0 / 23 | none |
| policy_time_max | timing | 4.032 | 3.959 | -0.07291 | [-0.5242, +0.3881] | 0 / 0 / 0 | timing-only |

`evidence` is `none` whenever the interval contains zero.  A count of scenes that moved is not evidence on its own.  `timing-only` rows are wall clock and depend on the machine.
