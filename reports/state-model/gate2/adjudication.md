# Safety rerank development adjudication (Gate 2)

Protocol: `reports/state-model/gate2-rerank-protocol.md`

- episodes: 63 across arms ['base', 'safety_null', 'safety_rerank']
- pooled placed: {"base": 389, "safety_null": 380, "safety_rerank": 383}
- pooled channels: {"base": {"slide": 3, "topple": 10, "transport_invalid": 8}, "safety_null": {"slide": 4, "topple": 9, "transport_invalid": 8}, "safety_rerank": {"slide": 3, "topple": 9, "transport_invalid": 9}}
- paired placed: 6 wins / 3 losses over 21 pairs
- swap activity: {"base": {"episodes": 21, "triggered": 0, "would_swap": 0, "enforced": 0}, "safety_null": {"episodes": 21, "triggered": 79, "would_swap": 2, "enforced": 0}, "safety_rerank": {"episodes": 21, "triggered": 85, "would_swap": 0, "enforced": 0}}
- gates: {"mechanism_topple_slide_lower": true, "direction_pooled_placed_higher": false, "no_harm_per_config": true, "fallback_conservation": false, "negative_control_within_floor": true}
- **verdict: inert_arm_closed**

## No-harm per config

| case | floor | base mean | rerank mean | ok |
|---|---|---|---|---|
| b000-k15 | 4.618 | 19.666666666666668 | 17.0 | True |
| b000-k20 | 1.966 | 19.333333333333332 | 20.666666666666668 | True |
| b000-k40 | 3.464 | 20.0 | 21.0 | True |
| b001-k20 | 3.724 | 16.666666666666668 | 14.666666666666666 | True |
| b001-k30 | 1.0 | 17.0 | 17.333333333333332 | True |
| c000-k1 | 6.26 | 16.0 | 16.0 | True |
| c001-k1 | 1.0 | 21.0 | 21.0 | True |

## Negative control per config

| case | floor | base mean | null mean | ok |
|---|---|---|---|---|
| b000-k15 | 4.618 | 19.666666666666668 | 18.333333333333332 | True |
| b000-k20 | 1.966 | 19.333333333333332 | 20.333333333333332 | True |
| b000-k40 | 3.464 | 20.0 | 19.0 | True |
| b001-k20 | 3.724 | 16.666666666666668 | 14.333333333333334 | True |
| b001-k30 | 1.0 | 17.0 | 17.666666666666668 | True |
| c000-k1 | 6.26 | 16.0 | 16.0 | True |
| c001-k1 | 1.0 | 21.0 | 21.0 | True |
