# Residual-affordance phase-hybrid fourth-stream gate

Runs: **32351615182 / 32368148298 / 32372290412 / 32375696343**
Target graphs / pairs / directional rows / overlap: **23 / 837 / 64 / 0**.

| Model | Correct |
|---|---:|
| immediate_score | 37/64 |
| global_frozen_action | 45/64 |
| phase_hybrid | 35/64 |

| Root step | Immediate | Global action | Phase hybrid | Rows |
|---:|---:|---:|---:|---:|
| 6 | 12 | 10 | 10 | 16 |
| 9 | 10 | 11 | 10 | 14 |
| 12 | 11 | 16 | 11 | 18 |
| 15 | 4 | 8 | 4 | 16 |

Graph wins/ties/losses vs immediate: **0 / 13 / 1**.
Global action confirmation: **PASS**, gain **+8**, graph W/T/L **5/6/3**.

Promotion gate: **FAIL**; gain vs immediate **-2**, vs global action **-10** (do_not_connect_phase_hybrid).
