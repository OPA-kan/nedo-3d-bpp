# Post-shake instrument fidelity verdict

Protocol: `reports/hazard/post-shake-instrument-protocol.md`. Cloned = official shake re-run on the rebuilt final state; recorded = the episode's own end-of-run shake_response.

- episodes joined: 63 (arms: {"base": 21, "guard_attr": 21, "quiet_guard": 21})
- Spearman shake_max_shift: 0.2561 (gate >= 0.8: False)
- Spearman shake_items_shifted: 0.8201 (gate >= 0.8: True)
- toppled within +-1: 50/63 = 0.7937 (gate >= 0.8: False)
- peak-KE excess quiet_guard over base: recorded 0.2388, cloned -0.3265 (sign match: False)

## Verdict: **fail**

## Non-binding diagnostic: low re-settle-drift episodes

Same arithmetic on episodes whose rebuilt poses moved <= 0.3 m during the pre-shake re-settle (recorded poses still consistent with the live end state). Localizes failure between state reconstruction and the shake clone; carries NO verdict weight.

- episodes: 32
- Spearman shake_max_shift: 0.0444
- Spearman shake_items_shifted: 0.8906
- toppled within +-1: 25/32 = 0.7812
- peak-KE excess sign match: False (recorded 1.0321, cloned -0.4805)

| label | arm | max shift c/r | shifted c/r | toppled c/r | peak KE c/r | resettle drift | soft clean | priority clean |
|---|---|---|---|---|---|---:|---:|---:|
| b000-k15-base-r0 | base | 0.099/0.175 | 7/8 | 0/0 | 9.24/8.57 | 0.256 | 1.000 | 0.750 |
| b000-k15-base-r1 | base | 0.099/0.175 | 7/8 | 0/0 | 9.24/8.57 | 0.256 | 1.000 | 0.750 |
| b000-k15-base-r2 | base | 0.099/0.175 | 7/8 | 0/0 | 9.24/8.57 | 0.256 | 1.000 | 0.750 |
| b000-k15-guard_attr-r0 | guard_attr | 0.066/0.065 | 2/3 | 0/0 | 8.12/9.30 | 0.066 | 1.000 | 0.000 |
| b000-k15-guard_attr-r1 | guard_attr | 0.099/0.175 | 7/8 | 0/0 | 9.24/8.57 | 0.256 | 1.000 | 0.750 |
| b000-k15-guard_attr-r2 | guard_attr | 0.099/0.175 | 7/8 | 0/0 | 9.24/8.57 | 0.256 | 1.000 | 0.750 |
| b000-k15-quiet_guard-r0 | quiet_guard | 0.099/0.175 | 7/8 | 0/0 | 9.24/8.57 | 0.256 | 1.000 | 0.750 |
| b000-k15-quiet_guard-r1 | quiet_guard | 0.099/0.175 | 7/8 | 0/0 | 9.24/8.57 | 0.256 | 1.000 | 0.750 |
| b000-k15-quiet_guard-r2 | quiet_guard | 0.066/0.065 | 2/3 | 0/0 | 8.12/9.30 | 0.066 | 1.000 | 0.000 |
| b000-k20-base-r0 | base | 0.159/0.182 | 9/5 | 0/0 | 16.99/12.80 | 0.249 | 1.000 | 1.000 |
| b000-k20-base-r1 | base | 0.520/0.632 | 10/8 | 0/1 | 28.99/54.94 | 0.583 | 1.000 | 1.000 |
| b000-k20-base-r2 | base | 0.169/0.079 | 1/2 | 1/0 | 93.57/6.54 | 0.078 | 0.909 | 1.000 |
| b000-k20-guard_attr-r0 | guard_attr | 0.169/0.079 | 1/2 | 1/0 | 93.57/6.54 | 0.078 | 0.909 | 1.000 |
| b000-k20-guard_attr-r1 | guard_attr | 0.358/0.747 | 2/4 | 1/3 | 8.60/122.04 | 0.956 | 0.889 | 0.750 |
| b000-k20-guard_attr-r2 | guard_attr | 0.169/0.079 | 1/2 | 1/0 | 93.57/6.54 | 0.078 | 0.909 | 1.000 |
| b000-k20-quiet_guard-r0 | quiet_guard | 0.520/0.632 | 10/8 | 0/1 | 28.99/54.94 | 0.583 | 1.000 | 1.000 |
| b000-k20-quiet_guard-r1 | quiet_guard | 0.358/0.747 | 2/4 | 1/3 | 8.60/122.04 | 0.956 | 0.889 | 0.750 |
| b000-k20-quiet_guard-r2 | quiet_guard | 0.090/0.312 | 1/2 | 0/0 | 3.38/8.24 | 0.972 | 0.917 | 1.000 |
| b000-k40-base-r0 | base | 0.061/0.217 | 1/4 | 0/1 | 5.44/58.70 | 0.200 | 0.800 | 0.500 |
| b000-k40-base-r1 | base | 0.045/0.045 | 0/0 | 0/0 | 10.00/12.36 | 0.109 | 1.000 | 0.750 |
| b000-k40-base-r2 | base | 0.061/0.217 | 1/4 | 0/1 | 5.44/58.70 | 0.200 | 0.800 | 0.500 |
| b000-k40-guard_attr-r0 | guard_attr | 0.061/0.217 | 1/4 | 0/1 | 5.44/58.70 | 0.200 | 0.800 | 0.500 |
| b000-k40-guard_attr-r1 | guard_attr | 0.061/0.217 | 1/4 | 0/1 | 5.44/58.70 | 0.200 | 0.800 | 0.500 |
| b000-k40-guard_attr-r2 | guard_attr | 0.822/0.490 | 6/9 | 1/5 | 33.85/171.07 | 0.768 | 1.000 | 0.750 |
| b000-k40-quiet_guard-r0 | quiet_guard | 0.061/0.217 | 1/4 | 0/1 | 5.44/58.70 | 0.200 | 0.800 | 0.500 |
| b000-k40-quiet_guard-r1 | quiet_guard | 0.060/0.889 | 4/6 | 0/1 | 8.49/316.74 | 0.024 | 1.000 | 1.000 |
| b000-k40-quiet_guard-r2 | quiet_guard | 0.163/0.334 | 11/11 | 0/0 | 10.70/25.99 | 0.063 | 1.000 | 0.750 |
| b001-k20-base-r0 | base | 0.429/0.342 | 6/6 | 0/0 | 9.38/51.15 | 1.204 | 1.000 | 1.000 |
| b001-k20-base-r1 | base | 0.099/1.380 | 10/12 | 0/4 | 9.14/184.71 | 1.269 | 1.000 | 0.500 |
| b001-k20-base-r2 | base | 0.099/1.380 | 10/12 | 0/4 | 9.14/184.71 | 1.269 | 1.000 | 0.500 |
| b001-k20-guard_attr-r0 | guard_attr | 0.075/0.336 | 3/6 | 0/3 | 5.80/62.61 | 0.143 | 1.000 | 1.000 |
| b001-k20-guard_attr-r1 | guard_attr | 0.075/0.336 | 3/6 | 0/3 | 5.80/62.61 | 0.143 | 1.000 | 1.000 |
| b001-k20-guard_attr-r2 | guard_attr | 0.075/0.336 | 3/6 | 0/3 | 5.80/62.61 | 0.143 | 1.000 | 1.000 |
| b001-k20-quiet_guard-r0 | quiet_guard | 0.189/0.524 | 6/9 | 0/4 | 5.50/117.40 | 0.790 | 1.000 | 0.500 |
| b001-k20-quiet_guard-r1 | quiet_guard | 0.065/0.065 | 2/2 | 0/0 | 7.48/14.86 | 0.071 | 0.900 | 0.500 |
| b001-k20-quiet_guard-r2 | quiet_guard | 0.065/0.065 | 2/2 | 0/0 | 7.38/14.13 | 0.070 | 0.900 | 0.500 |
| b001-k30-base-r0 | base | 0.092/0.092 | 4/3 | 0/0 | 6.22/6.40 | 0.640 | 1.000 | 1.000 |
| b001-k30-base-r1 | base | 0.092/0.092 | 4/3 | 0/0 | 6.22/6.40 | 0.640 | 1.000 | 1.000 |
| b001-k30-base-r2 | base | 0.048/0.040 | 0/0 | 0/0 | 12.92/14.67 | 0.110 | 1.000 | 1.000 |
| b001-k30-guard_attr-r0 | guard_attr | 0.092/0.092 | 4/3 | 0/0 | 6.22/6.40 | 0.640 | 1.000 | 1.000 |
| b001-k30-guard_attr-r1 | guard_attr | 0.092/0.092 | 4/3 | 0/0 | 6.22/6.40 | 0.640 | 1.000 | 1.000 |
| b001-k30-guard_attr-r2 | guard_attr | 0.092/0.092 | 4/3 | 0/0 | 6.22/6.40 | 0.640 | 1.000 | 1.000 |
| b001-k30-quiet_guard-r0 | quiet_guard | 0.092/0.092 | 4/3 | 0/0 | 6.22/6.40 | 0.640 | 1.000 | 1.000 |
| b001-k30-quiet_guard-r1 | quiet_guard | 0.048/0.040 | 0/0 | 0/0 | 12.92/14.67 | 0.110 | 1.000 | 1.000 |
| b001-k30-quiet_guard-r2 | quiet_guard | 0.092/0.092 | 4/3 | 0/0 | 6.22/6.40 | 0.640 | 1.000 | 1.000 |
| c000-k1-base-r0 | base | 0.067/0.623 | 5/6 | 0/2 | 6.89/47.06 | 0.030 | 1.000 | 1.000 |
| c000-k1-base-r1 | base | 0.152/0.606 | 7/8 | 1/1 | 11.46/217.78 | 0.623 | 0.833 | 0.667 |
| c000-k1-base-r2 | base | 0.067/0.623 | 5/6 | 0/2 | 6.89/47.06 | 0.030 | 1.000 | 1.000 |
| c000-k1-guard_attr-r0 | guard_attr | 0.067/0.623 | 5/6 | 0/2 | 6.89/47.06 | 0.030 | 1.000 | 1.000 |
| c000-k1-guard_attr-r1 | guard_attr | 0.067/0.623 | 5/6 | 0/2 | 6.89/47.06 | 0.030 | 1.000 | 1.000 |
| c000-k1-guard_attr-r2 | guard_attr | 0.152/0.606 | 7/8 | 1/1 | 11.46/217.78 | 0.623 | 0.833 | 0.667 |
| c000-k1-quiet_guard-r0 | quiet_guard | 0.151/0.110 | 9/9 | 0/0 | 9.03/13.09 | 1.972 | 0.833 | 1.000 |
| c000-k1-quiet_guard-r1 | quiet_guard | 0.152/0.606 | 7/8 | 1/1 | 11.46/217.78 | 0.623 | 0.833 | 0.667 |
| c000-k1-quiet_guard-r2 | quiet_guard | 0.152/0.606 | 7/8 | 1/1 | 11.46/217.78 | 0.623 | 0.833 | 0.667 |
| c001-k1-base-r0 | base | 0.146/0.160 | 3/6 | 0/0 | 9.77/13.29 | 1.057 | 1.000 | - |
| c001-k1-base-r1 | base | 0.146/0.160 | 3/6 | 0/0 | 9.77/13.29 | 1.057 | 1.000 | - |
| c001-k1-base-r2 | base | 0.146/0.160 | 3/6 | 0/0 | 9.77/13.29 | 1.057 | 1.000 | - |
| c001-k1-guard_attr-r0 | guard_attr | 0.146/0.160 | 3/6 | 0/0 | 9.77/13.29 | 1.057 | 1.000 | - |
| c001-k1-guard_attr-r1 | guard_attr | 0.178/0.150 | 5/5 | 0/0 | 7.82/11.49 | 0.915 | 1.000 | - |
| c001-k1-guard_attr-r2 | guard_attr | 0.178/0.150 | 5/5 | 0/0 | 7.82/11.49 | 0.915 | 1.000 | - |
| c001-k1-quiet_guard-r0 | quiet_guard | 0.146/0.160 | 3/6 | 0/0 | 9.77/13.29 | 1.057 | 1.000 | - |
| c001-k1-quiet_guard-r1 | quiet_guard | 0.146/0.160 | 3/6 | 0/0 | 9.77/13.29 | 1.057 | 1.000 | - |
| c001-k1-quiet_guard-r2 | quiet_guard | 0.146/0.160 | 3/6 | 0/0 | 9.77/13.29 | 1.057 | 1.000 | - |

Coverage columns are the POST-shake soft/priority clean ratios recomputed under the published rules (see module docstring for the contract source). They are the instrument's payload once the gate passes; they take no part in the gate itself.
