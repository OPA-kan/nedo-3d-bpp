# Offline adaptive no-NN PUCT schedule

- roots: 58
- Q-top matches deep bounded reference: 54 / 58
- visit-top matches deep bounded reference: 54 / 58
- both tops match: 54 / 58
- mean rollout-step upper bound: 151.4
- reference wider-safe rescue nodes: 151

## Rule comparison

| rule | both tops match | mean rollout-step upper bound |
|---|---:|---:|
| aggressive_budget_top | 54 / 58 | 151.4 |
| horizon_top_confirmed | 57 / 58 | 345.9 |
| full_order_guarded | 58 / 58 | 958.3 |

## Stop conditions

| condition | roots |
|---|---:|
| h2-s24 | 0 |
| h2-s48 | 55 |
| h3-s48 | 3 |
| h5-s48 | 0 |
| h2-s96 | 0 |
| h3-s96 | 0 |
| h5-s96 | 0 |

## Caveats

- All three stopping rules are posthoc development diagnostics on these same 58 roots; none is a preregistered or independently confirmed policy.
- The full-order guarded rule reproduces 58/58 by construction because it uses the promotion rule that defines the measured deep reference.
- The 58 roots are a Q-discriminating capability set, not an unbiased on-policy evaluation set.
- Horizon times simulations is an upper bound on rollout steps; candidate proposal and physical-filter cost is not included.
- The reference search used candidate rescue at exhausted Top-K nodes (limits=[64], applied nodes=151); adaptive H/S agreement is conditional on that enlarged support.
- Agreement is measured against the deepest bounded condition, not Q*.
