# Residual-affordance shadow gate v3

Overall: **PASS**

Calibration runs: 32380902237, 32381957502, 32435231411
Calibration arms: `base` only (calibration shadow values are ignored).

| gate | passed | detail |
|---|---|---|
| same-call decision invariance | True | {"guarded_contract_regressions": 0, "incumbent_unchanged": 284, "minimum_observed": 50, "missing": 0, "observed": 284, "passed": true, "portfolio_unchanged": 284} |
| reach | True | observed 284; guarded changes 135 |
| attribute safety | True | unrestricted 0; blocked 0; guarded 0 |
| physical footprint | True | comparisons 65; baseline breaches 0; effect breaches 0; missing 0 |

The prospective effect is the current shadow mean minus its simultaneous base mean. The tolerance is the full spread of historical base-only runs.
Cross-process action hashes remain diagnostic only.
