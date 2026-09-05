# Paired comparison: analytic minus physics

Scenes paired: 48

Negative control (same arm both sides): **FAIL: steps differ**

Leading placements identical (item, container, orientation, pose within 2 cm): mean 6.6 steps per scene

End reasons physics: `{'declined': 43, 'settle': 5}`
End reasons analytic: `{'declined': 48}`

| metric | better is | mean A | mean B | mean diff | 95% CI | better / equal / worse | evidence |
|---|---|---:|---:|---:|---|---|---|
| placed_count | up | 20.67 | 22.08 | +1.417 | [+0.3542, +2.438] | 27 / 10 / 11 | b-better |
| fill_volume | up | 22.76 | 24.45 | +1.691 | [+0.5262, +2.863] | 29 / 8 / 11 | b-better |
| com_z_above_floor_ratio | down | 0.3215 | 0.343 | +0.02155 | [+0.01135, +0.03184] | 11 / 0 / 37 | b-worse |
| priority_covered | down | 0 | 0.02083 | +0.02083 | [+0, +0.0625] | 0 / 47 / 1 | none |
| priority_misrouted | down | 0 | 0 | +0 | [+0, +0] | 0 / 48 / 0 | none |
| soft_covered | down | 0.1458 | 0.0625 | -0.08333 | [-0.25, +0.0625] | 5 / 40 / 3 | none |
| policy_time_max | timing | 4.032 | 3.171 | -0.8607 | [-1.177, -0.5638] | 0 / 0 / 0 | timing-only |

`evidence` is `none` whenever the interval contains zero.  A count of scenes that moved is not evidence on its own.  `timing-only` rows are wall clock and depend on the machine.
