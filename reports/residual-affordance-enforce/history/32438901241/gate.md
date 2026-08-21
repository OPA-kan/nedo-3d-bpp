# Residual-affordance guarded-enforce canary v1

Overall: **FAIL**

| gate | passed | detail |
|---|---|---|
| causal_reach | True | {"enforced": 101, "guarded_contract_regressions": 0, "minimum_enforced": 5} |
| trajectory_value | False | {"deltas": {"fill": -3.429, "placed": -2.333, "steps": -2.333}, "strict_score_gain": false} |
| attribute_safety | True | {"deltas": {"priority_clean": 0.011, "soft_clean": 0.0}} |
| physical_safety | False | {"deltas": {"shake_max_shift": -0.052, "shake_peak_ke": 47.899, "shake_shifted": -0.733, "shake_shifted_fraction": -0.006, "shake_toppled": 0.0}} |
| terminal_validity | True | {"deltas": {"terminal_included": 0.0, "terminal_placed_safe": 0.0, "terminal_valid": 0.467}} |

Missing metrics: 0
No weighted total is formed; every safety axis is an independent veto.
