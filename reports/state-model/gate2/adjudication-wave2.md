# Safety rerank development adjudication (Gate 2)

Protocol: `reports/state-model/gate2-rerank-protocol.md`

- episodes: 63 across arms ['base', 'safety_null', 'safety_rerank']
- pooled placed: {"base": 381, "safety_null": 377, "safety_rerank": 381}
- pooled channels: {"base": {"slide": 2, "topple": 10, "transport_invalid": 9}, "safety_null": {"slide": 4, "topple": 11, "transport_invalid": 6}, "safety_rerank": {"slide": 1, "topple": 11, "transport_invalid": 9}}
- paired placed: 3 wins / 5 losses over 21 pairs
- swap activity: {"base": {"episodes": 21, "triggered": 0, "would_swap": 0, "enforced": 0}, "safety_null": {"episodes": 21, "triggered": 77, "would_swap": 0, "enforced": 0}, "safety_rerank": {"episodes": 21, "triggered": 78, "would_swap": 0, "enforced": 0}}
- gates: {"mechanism_topple_slide_lower": false, "direction_pooled_placed_higher": false, "no_harm_per_config": true, "fallback_conservation": true, "negative_control_within_floor": true}
- **verdict: inert_arm_closed**

## No-harm per config

| case | floor | base mean | rerank mean | ok |
|---|---|---|---|---|
| b000-k15 | 4.618 | 19.666666666666668 | 18.333333333333332 | True |
| b000-k20 | 1.966 | 17.666666666666668 | 20.0 | True |
| b000-k40 | 3.464 | 21.0 | 20.0 | True |
| b001-k20 | 3.724 | 14.666666666666666 | 14.333333333333334 | True |
| b001-k30 | 1.0 | 17.0 | 17.333333333333332 | True |
| c000-k1 | 6.26 | 16.0 | 16.0 | True |
| c001-k1 | 1.0 | 21.0 | 21.0 | True |

## Negative control per config

| case | floor | base mean | null mean | ok |
|---|---|---|---|---|
| b000-k15 | 4.618 | 19.666666666666668 | 19.666666666666668 | True |
| b000-k20 | 1.966 | 17.666666666666668 | 18.666666666666668 | True |
| b000-k40 | 3.464 | 21.0 | 19.0 | True |
| b001-k20 | 3.724 | 14.666666666666666 | 14.333333333333334 | True |
| b001-k30 | 1.0 | 17.0 | 17.0 | True |
| c000-k1 | 6.26 | 16.0 | 16.0 | True |
| c001-k1 | 1.0 | 21.0 | 21.0 | True |
