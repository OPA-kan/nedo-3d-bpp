# probe_guard development adjudication

Protocol: `reports/hazard/probe-guard-protocol.md`

- episodes: 63 across arms ['base', 'probe_guard', 'probe_null']
- pooled placed: {"base": 390, "probe_guard": 389, "probe_null": 388}
- pooled channels: {"base": {"slide": 2, "topple": 9, "transport_invalid": 10}, "probe_guard": {"slide": 5, "topple": 11, "transport_invalid": 5}, "probe_null": {"slide": 2, "topple": 8, "transport_invalid": 11}}
- paired placed: 4 wins / 7 losses over 21 pairs
- swap activity: {"base": {"episodes": 21, "triggered": 0, "would_swap": 0, "enforced": 0}, "probe_guard": {"episodes": 21, "triggered": 114, "would_swap": 68, "enforced": 17}, "probe_null": {"episodes": 21, "triggered": 0, "would_swap": 0, "enforced": 0}}
- gates: {"mechanism_topple_slide_lower": false, "direction_pooled_placed_higher": false, "no_harm_per_config": true, "fallback_conservation": true, "negative_control_within_floor": false}
- **verdict: development_fail_arm_closed**

## No-harm per config

| case | floor | base mean | rerank mean | ok |
|---|---|---|---|---|
| b000-k15 | 4.618 | 21.0 | 19.0 | True |
| b000-k20 | 1.966 | 20.666666666666668 | 19.0 | True |
| b000-k40 | 3.464 | 17.333333333333332 | 19.0 | True |
| b001-k20 | 3.724 | 14.666666666666666 | 15.0 | True |
| b001-k30 | 1.0 | 17.0 | 17.0 | True |
| c000-k1 | 6.26 | 18.333333333333332 | 19.666666666666668 | True |
| c001-k1 | 1.0 | 21.0 | 21.0 | True |

## Negative control per config

| case | floor | base mean | null mean | ok |
|---|---|---|---|---|
| b000-k15 | 4.618 | 21.0 | 18.333333333333332 | True |
| b000-k20 | 1.966 | 20.666666666666668 | 18.0 | False |
| b000-k40 | 3.464 | 17.333333333333332 | 20.0 | True |
| b001-k20 | 3.724 | 14.666666666666666 | 16.0 | True |
| b001-k30 | 1.0 | 17.0 | 17.666666666666668 | True |
| c000-k1 | 6.26 | 18.333333333333332 | 18.333333333333332 | True |
| c001-k1 | 1.0 | 21.0 | 21.0 | True |
