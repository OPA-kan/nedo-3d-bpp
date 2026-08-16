# Safety rerank development adjudication (Gate 2)

Protocol: `reports/state-model/gate2-rerank-protocol.md`

- episodes: 63 across arms ['base', 'safety_null', 'safety_rerank']
- pooled placed: {"base": 404, "safety_null": 385, "safety_rerank": 367}
- pooled channels: {"base": {"slide": 2, "topple": 8, "transport_invalid": 11}, "safety_null": {"slide": 1, "topple": 12, "transport_invalid": 8}, "safety_rerank": {"slide": 4, "topple": 7, "transport_invalid": 10}}
- paired placed: 7 wins / 13 losses over 21 pairs
- swap activity: {"base": {"episodes": 21, "triggered": 0, "would_swap": 0, "enforced": 0}, "safety_null": {"episodes": 21, "triggered": 91, "would_swap": 40, "enforced": 0}, "safety_rerank": {"episodes": 21, "triggered": 83, "would_swap": 35, "enforced": 35}}
- gates: {"mechanism_topple_slide_lower": false, "direction_pooled_placed_higher": false, "no_harm_per_config": false, "fallback_conservation": true, "negative_control_within_floor": true}
- **verdict: development_fail_arm_closed**

## No-harm per config

| case | floor | base mean | rerank mean | ok |
|---|---|---|---|---|
| b000-k15 | 4.618 | 19.666666666666668 | 15.666666666666666 | True |
| b000-k20 | 1.966 | 20.333333333333332 | 17.0 | False |
| b000-k40 | 3.464 | 20.0 | 19.666666666666668 | True |
| b001-k20 | 3.724 | 16.0 | 17.0 | True |
| b001-k30 | 1.0 | 17.0 | 19.0 | True |
| c000-k1 | 6.26 | 20.666666666666668 | 17.0 | True |
| c001-k1 | 1.0 | 21.0 | 17.0 | False |

## Negative control per config

| case | floor | base mean | null mean | ok |
|---|---|---|---|---|
| b000-k15 | 4.618 | 19.666666666666668 | 19.666666666666668 | True |
| b000-k20 | 1.966 | 20.333333333333332 | 20.0 | True |
| b000-k40 | 3.464 | 20.0 | 20.0 | True |
| b001-k20 | 3.724 | 16.0 | 14.666666666666666 | True |
| b001-k30 | 1.0 | 17.0 | 17.0 | True |
| c000-k1 | 6.26 | 20.666666666666668 | 16.0 | True |
| c001-k1 | 1.0 | 21.0 | 21.0 | True |
