# Paired comparison: analytic minus physics

Scenes paired: 48

Negative control (same arm both sides): **FAIL: steps differ**

Leading placements identical (item, container, orientation, pose within 2 cm): mean 12.9 steps per scene

End reasons physics: `{'declined': 46, 'settle': 2}`
End reasons analytic: `{'declined': 48}`

| metric | better is | mean A | mean B | mean diff | 95% CI | better / equal / worse | evidence |
|---|---|---:|---:|---:|---|---|---|
| placed_count | up | 21.77 | 21.77 | +0 | [-0.8542, +0.7917] | 13 / 26 / 9 | none |
| fill_volume | up | 23.8 | 23.99 | +0.1901 | [-0.579, +0.9043] | 16 / 23 / 9 | none |
| com_z_above_floor_ratio | down | 0.3362 | 0.3381 | +0.001876 | [-0.004049, +0.007735] | 14 / 0 / 34 | none |
| priority_covered | down | 0.0625 | 0.02083 | -0.04167 | [-0.1042, +0] | 2 / 46 / 0 | none |
| priority_misrouted | down | 0 | 0 | +0 | [+0, +0] | 0 / 48 / 0 | none |
| soft_covered | down | 0.125 | 0.1667 | +0.04167 | [-0.1042, +0.2083] | 4 / 40 / 4 | none |
| policy_time_max | timing | 3.959 | 3.183 | -0.7764 | [-0.9626, -0.5841] | 0 / 0 / 0 | timing-only |

`evidence` is `none` whenever the interval contains zero.  A count of scenes that moved is not evidence on its own.  `timing-only` rows are wall clock and depend on the machine.
