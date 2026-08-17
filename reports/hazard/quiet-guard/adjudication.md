# quiet_guard development adjudication

Protocol: `reports/hazard/quiet-guard-protocol.md`

- episodes: 63 across arms ['base', 'quiet_guard', 'quiet_null']
- pooled placed: {"base": 403, "quiet_guard": 410, "quiet_null": 392}
- pooled steps: {"base": 424, "quiet_guard": 431, "quiet_null": 413}
- pooled channels: {"base": {"topple": 8, "transport_invalid": 13}, "quiet_guard": {"slide": 2, "topple": 8, "transport_invalid": 11}, "quiet_null": {"slide": 1, "topple": 12, "transport_invalid": 8}}
- paired placed: 6 wins / 4 losses over 21 pairs
- swap activity: {"base": {"episodes": 21, "triggered": 0, "would_swap": 0, "enforced": 0}, "quiet_guard": {"episodes": 21, "triggered": 103, "would_swap": 53, "enforced": 9}, "quiet_null": {"episodes": 21, "triggered": 0, "would_swap": 0, "enforced": 0}}
- gates: {"mechanism_pooled_steps_higher": true, "direction_pooled_placed_higher": true, "no_harm_per_config": true, "fallback_conservation": true, "negative_control_within_floor": true}
- **verdict: development_pass_gate3_required**

## No-harm per config

| case | floor | base mean | rerank mean | ok |
|---|---|---|---|---|
| b000-k15 | 4.618 | 20.333333333333332 | 20.333333333333332 | True |
| b000-k20 | 1.966 | 21.0 | 23.0 | True |
| b000-k40 | 3.464 | 21.0 | 20.0 | True |
| b001-k20 | 3.724 | 15.666666666666666 | 16.0 | True |
| b001-k30 | 1.0 | 17.0 | 17.666666666666668 | True |
| c000-k1 | 6.26 | 18.333333333333332 | 18.666666666666668 | True |
| c001-k1 | 1.0 | 21.0 | 21.0 | True |

## Negative control per config

| case | floor | base mean | null mean | ok |
|---|---|---|---|---|
| b000-k15 | 4.618 | 20.333333333333332 | 19.333333333333332 | True |
| b000-k20 | 1.966 | 21.0 | 20.0 | True |
| b000-k40 | 3.464 | 21.0 | 20.0 | True |
| b001-k20 | 3.724 | 15.666666666666666 | 14.666666666666666 | True |
| b001-k30 | 1.0 | 17.0 | 17.333333333333332 | True |
| c000-k1 | 6.26 | 18.333333333333332 | 18.333333333333332 | True |
| c001-k1 | 1.0 | 21.0 | 21.0 | True |
