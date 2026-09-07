# Paired comparison: wedge-core minus stable-core

Scenes paired: 48

Leading placements identical (item, container, orientation, pose within 2 cm): mean 0.3 steps per scene

End reasons stable-core: `{'declined': 46, 'settle': 2}`
End reasons wedge-core: `{'declined': 47, 'settle': 1}`

| metric | better is | mean A | mean B | mean diff | 95% CI | better / equal / worse | evidence |
|---|---|---:|---:|---:|---|---|---|
| placed_count | up | 21.77 | 21.04 | -0.7292 | [-1.771, +0.2083] | 15 / 11 / 22 | none |
| fill_volume | up | 23.8 | 23.06 | -0.7481 | [-1.844, +0.2932] | 15 / 11 / 22 | none |
| fill_evaluator_tolerant | up | 21.83 | 21.55 | -0.284 | [-1.255, +0.6562] | 21 / 2 / 25 | none |
| fill_evaluator_shipped | up | 14.4 | 14 | -0.4033 | [-1.281, +0.4384] | 19 / 1 / 28 | none |
| com_z_above_floor_ratio | down | 0.3362 | 0.2983 | -0.03795 | [-0.05011, -0.02648] | 40 / 0 / 8 | b-better |
| priority_covered | down | 0.0625 | 0 | -0.0625 | [-0.1458, +0] | 3 / 45 / 0 | none |
| priority_misrouted | down | 0 | 0 | +0 | [+0, +0] | 0 / 48 / 0 | none |
| soft_covered | down | 0.125 | 0.04167 | -0.08333 | [-0.1875, +0] | 5 / 42 / 1 | none |
| shake_mean_shift | down | 0.03089 | 0.02739 | -0.003499 | [-0.01056, +0.005118] | 31 / 0 / 17 | none |
| shake_topples | down | 0.1458 | 0.2917 | +0.1458 | [-0.04167, +0.375] | 4 / 37 / 7 | none |
| shake_peak_kinetic_energy | down | 13.54 | 18.09 | +4.545 | [-3.528, +13.26] | 27 / 0 / 21 | none |
| policy_time_max | timing | 3.959 | 2.994 | -0.9652 | [-1.5, -0.4239] | 0 / 0 / 0 | timing-only |

`evidence` is `none` whenever the interval contains zero.  A count of scenes that moved is not evidence on its own.  `timing-only` rows are wall clock and depend on the machine.
