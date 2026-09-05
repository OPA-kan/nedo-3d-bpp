# Paired comparison: ladder-smoke-repeat minus ladder-smoke

Scenes paired: 4

Negative control (same arm both sides): **PASS: identical step for step**

End reasons ladder-smoke: `{'declined': 4}`
End reasons ladder-smoke-repeat: `{'declined': 4}`

| metric | better is | mean A | mean B | mean diff | 95% CI | better / equal / worse | evidence |
|---|---|---:|---:|---:|---|---|---|
| placed_count | up | 20 | 20 | +0 | [+0, +0] | 0 / 4 / 0 | none |
| fill_volume | up | 22.37 | 22.37 | +0 | [+0, +0] | 0 / 4 / 0 | none |
| fill_evaluator_tolerant | up | 20.12 | 20.12 | +0 | [+0, +0] | 0 / 4 / 0 | none |
| fill_evaluator_shipped | up | 12.74 | 12.74 | +0 | [+0, +0] | 0 / 4 / 0 | none |
| com_z_above_floor_ratio | down | 0.3066 | 0.3066 | +0 | [+0, +0] | 0 / 4 / 0 | none |
| priority_covered | down | 0 | 0 | +0 | [+0, +0] | 0 / 4 / 0 | none |
| priority_misrouted | down | 0 | 0 | +0 | [+0, +0] | 0 / 4 / 0 | none |
| soft_covered | down | 0 | 0 | +0 | [+0, +0] | 0 / 4 / 0 | none |
| shake_mean_shift | down | 0.02642 | 0.02642 | +0 | [+0, +0] | 0 / 4 / 0 | none |
| shake_topples | down | 0 | 0 | +0 | [+0, +0] | 0 / 4 / 0 | none |
| shake_peak_kinetic_energy | down | 5.918 | 5.918 | +0 | [+0, +0] | 0 / 4 / 0 | none |
| policy_time_max | timing | 4.313 | 4.517 | +0.2037 | [+0.095, +0.368] | 0 / 0 / 0 | timing-only |

`evidence` is `none` whenever the interval contains zero.  A count of scenes that moved is not evidence on its own.  `timing-only` rows are wall clock and depend on the machine.
