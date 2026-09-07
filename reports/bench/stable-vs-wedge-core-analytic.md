# Paired comparison: wedge-core-analytic minus stable-core-analytic

Scenes paired: 48

Leading placements identical (item, container, orientation, pose within 2 cm): mean 0.3 steps per scene

End reasons stable-core-analytic: `{'declined': 48}`
End reasons wedge-core-analytic: `{'declined': 48}`

| metric | better is | mean A | mean B | mean diff | 95% CI | better / equal / worse | evidence |
|---|---|---:|---:|---:|---|---|---|
| placed_count | up | 21.77 | 21.38 | -0.3958 | [-1.146, +0.375] | 13 / 12 / 23 | none |
| fill_volume | up | 23.99 | 23.51 | -0.4799 | [-1.422, +0.4567] | 13 / 11 / 24 | none |
| com_z_above_floor_ratio | down | 0.3381 | 0.3059 | -0.03226 | [-0.04413, -0.02064] | 35 / 0 / 13 | b-better |
| priority_covered | down | 0.02083 | 0 | -0.02083 | [-0.0625, +0] | 1 / 47 / 0 | none |
| priority_misrouted | down | 0 | 0 | +0 | [+0, +0] | 0 / 48 / 0 | none |
| soft_covered | down | 0.1667 | 0.1042 | -0.0625 | [-0.2292, +0.1042] | 4 / 42 / 2 | none |
| policy_time_max | timing | 3.183 | 2.356 | -0.8271 | [-1.24, -0.4466] | 0 / 0 / 0 | timing-only |

`evidence` is `none` whenever the interval contains zero.  A count of scenes that moved is not evidence on its own.  `timing-only` rows are wall clock and depend on the machine.
