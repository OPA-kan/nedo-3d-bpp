# Paired comparison: analytic minus physics

Scenes paired: 48

Negative control (same arm both sides): **FAIL: steps differ**

Leading placements identical (item, container, orientation, pose within 2 cm): mean 10.2 steps per scene

End reasons physics: `{'declined': 47, 'settle': 1}`
End reasons analytic: `{'declined': 48}`

| metric | better is | mean A | mean B | mean diff | 95% CI | better / equal / worse | evidence |
|---|---|---:|---:|---:|---|---|---|
| placed_count | up | 21.35 | 21.33 | -0.02083 | [-0.875, +0.8958] | 10 / 26 / 12 | none |
| fill_volume | up | 23.78 | 23.6 | -0.1756 | [-1.001, +0.6381] | 11 / 25 / 12 | none |
| com_z_above_floor_ratio | down | 0.329 | 0.3344 | +0.005406 | [-0.002056, +0.01303] | 17 / 0 / 31 | none |
| priority_covered | down | 0.04167 | 0.04167 | +0 | [-0.08333, +0.08333] | 2 / 44 / 2 | none |
| priority_misrouted | down | 0 | 0 | +0 | [+0, +0] | 0 / 48 / 0 | none |
| soft_covered | down | 0.1042 | 0.1875 | +0.08333 | [-0.02083, +0.2083] | 2 / 40 / 6 | none |
| policy_time_max | timing | 3.23 | 2.496 | -0.734 | [-0.9188, -0.5648] | 0 / 0 / 0 | timing-only |

`evidence` is `none` whenever the interval contains zero.  A count of scenes that moved is not evidence on its own.  `timing-only` rows are wall clock and depend on the machine.
