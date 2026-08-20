# Counterfactual sensitivity regimes

Training / target run: **32351615182 / 32368148298**
Frozen regimes / training silhouette: **2 / 0.593**
Training regime support gate: **FAIL** (minimum 4 source states each).
Target source states / directional rows / signature overlap: **15 / 30 / 0**.

| Model | Correct |
|---|---:|
| immediate_score | 28/30 |
| sensitivity_regime | 28/30 |

| Regime | Training states | Training lower / higher | Frozen direction |
|---:|---:|---:|---|
| 0 | 1 | 0 / 2 | higher_afterstate_better |
| 1 | 31 | 15 / 49 | higher_afterstate_better |

| Regime | Frozen direction | Target states | Target lower / higher | Root steps (telemetry only) |
|---:|---|---:|---:|---|
| 0 | higher_afterstate_better | 6 | 0 / 12 | {"12": 6} |
| 1 | higher_afterstate_better | 9 | 2 / 16 | {"12": 4, "15": 2, "6": 1, "9": 2} |

Promotion gate: **FAIL** (do_not_connect_regime_model).
