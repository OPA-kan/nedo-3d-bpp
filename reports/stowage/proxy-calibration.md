# The evaluation-side proxies point the right way — all seven, zero exceptions

`docs/BLOCKED_WORK.md` §0 named one blocker as the cause of every stalled
adoption on this branch: four of the six official components are computed
only by the evaluation service, so a change that moves them locally moves a
number nobody can read. Every decision was therefore taken on `placed`,
because `placed` is the only local quantity whose official direction had
been observed.

The procedure §0 prescribed was never run. This is it, run.

## Method

Three of the four scored submissions are reconstructible as knob settings on
the current agent, and all three have published six-component breakdowns:

| arm | submission | official total | fill | cog | stab | place | soft |
|---|---|---:|---:|---:|---:|---:|---:|
| `base` | trueenvelope | 35.375 | 34.246 | 40.683 | 53.240 | 16.95 | 21.30 |
| `death_band` | deathband | 29.959 | 33.635 | 32.243 | 41.288 | 14.70 | 17.45 |
| `box_envelope` | 3334 level | 23.246 | 31.413 | 21.505 | 29.424 | 10.85 | 12.65 |

Four scenarios, three repeats, serial, with `base_null` — a second arm
identically configured to `base` — carrying the noise floor.

Each proxy is compared to its component **within a scenario**, never pooled
across them. Pooling was the first version and it failed: the spread
*between* scenarios landed in the noise floor, which made the floor for
`fill` 15.1 against a local span of 1.7 and reported every proxy as
untested. Arms are only comparable against arms that ran on the same board.

## Result

```
proxy                       official      agrees  disagrees  untested
priority_covered_by_other   placement          3          0         1
placed                      placed             1          0         3
com_z                       cog                1          0         2
shake_max_shift             stability          1          0         2
shake_items_toppled         stability          1          0         2
soft_covered_by_other       soft               1          0         3
fill                        fill               0          0         4
```

**Not one proxy points the wrong way.** `fill` is untested everywhere
because its local spread never clears its own floor — three configurations
that differ by 2.8 official fill points are locally indistinguishable, which
is a statement about the local suite's resolution, not about the proxy.

## What this does and does not license

It licenses reading the sign of a change on `com_z`, the two shake measures,
and the two attribute-covering counts. It does **not** license trading them
against each other: three points refute directions and fit no weights, and
the cutoff-gate model means the components are not even additive below the
placement threshold.

The immediate consequence is on `reports/stowage/attr-guard-verdict.md`.
The attribute guard drives `priority_covered_by_other` to zero in all four
scenarios and costs placements in three — and `priority_covered_by_other`
is now the best-validated proxy in the table, agreeing in three scenarios.
The trade is real in both directions. It is still not adoptable, because
nothing here says how many placements one priority violation is worth.

Regenerate with:

```
python scripts/calibrate_proxies.py --root reports/stowage/calibration \
    --output reports/stowage/proxy-calibration.json
```
