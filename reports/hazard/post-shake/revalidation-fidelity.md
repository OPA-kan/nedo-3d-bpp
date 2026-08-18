# Post-shake instrument fidelity verdict

Protocol: `reports/hazard/post-shake-instrument-protocol.md`. Cloned = official shake re-run on the rebuilt final state; recorded = the episode's own end-of-run shake_response. Reconstruction mode: `snapshots` (last pose_snapshot trace event, settle_final supplement for placements the snapshot postdates).

- episodes joined: 42 (arms: {"base": 21, "quiet_guard": 21})
- Spearman shake_max_shift: 0.7615 (gate >= 0.8: False)
- Spearman shake_items_shifted: 0.9307 (gate >= 0.8: True)
- toppled within +-1: 40/42 = 0.9524 (gate >= 0.8: True)
- peak-KE excess quiet_guard over base: recorded 0.1933, cloned -0.2495 (sign match: False)

## Verdict: **fail**

## Non-binding diagnostic: low re-settle-drift episodes

Same arithmetic on episodes whose rebuilt poses moved <= 0.3 m during the pre-shake re-settle (recorded poses still consistent with the live end state). Localizes failure between state reconstruction and the shake clone; carries NO verdict weight.

- episodes: 30
- Spearman shake_max_shift: 0.9128
- Spearman shake_items_shifted: 0.9736
- toppled within +-1: 28/30 = 0.9333
- peak-KE excess sign match: False (recorded 0.1272, cloned -0.2668)

| label | arm | max shift c/r | shifted c/r | toppled c/r | peak KE c/r | resettle drift | soft clean | priority clean |
|---|---|---|---|---|---|---:|---:|---:|
| b000-k15-base-r0 | base | 0.105/0.175 | 11/8 | 0/0 | 6.35/8.57 | 0.361 | 1.000 | 0.750 |
| b000-k15-base-r1 | base | 0.105/0.175 | 11/8 | 0/0 | 6.35/8.57 | 0.361 | 1.000 | 0.750 |
| b000-k15-base-r2 | base | 0.357/0.372 | 10/9 | 0/0 | 118.11/32.74 | 0.040 | 1.000 | 0.750 |
| b000-k15-quiet_guard-r0 | quiet_guard | 0.065/0.065 | 3/3 | 0/0 | 8.55/9.30 | 0.010 | 1.000 | 0.000 |
| b000-k15-quiet_guard-r1 | quiet_guard | 0.065/0.065 | 3/3 | 0/0 | 8.55/9.30 | 0.010 | 1.000 | 0.000 |
| b000-k15-quiet_guard-r2 | quiet_guard | 0.105/0.175 | 11/8 | 0/0 | 6.35/8.57 | 0.361 | 1.000 | 0.750 |
| b000-k20-base-r0 | base | 0.307/0.236 | 3/4 | 2/0 | 49.39/8.63 | 0.069 | 0.909 | 0.750 |
| b000-k20-base-r1 | base | 0.075/0.312 | 1/2 | 0/0 | 2.89/8.24 | 0.957 | 1.000 | 0.750 |
| b000-k20-base-r2 | base | 0.075/0.312 | 1/2 | 0/0 | 2.89/8.24 | 0.957 | 1.000 | 0.750 |
| b000-k20-quiet_guard-r0 | quiet_guard | 0.631/0.632 | 8/8 | 1/1 | 55.53/54.94 | 0.010 | 1.000 | 1.000 |
| b000-k20-quiet_guard-r1 | quiet_guard | 0.307/0.236 | 3/4 | 2/0 | 49.39/8.63 | 0.069 | 0.909 | 0.750 |
| b000-k20-quiet_guard-r2 | quiet_guard | 0.631/0.632 | 8/8 | 1/1 | 55.53/54.94 | 0.010 | 1.000 | 1.000 |
| b000-k40-base-r0 | base | 0.387/0.353 | 11/10 | 0/0 | 60.45/52.49 | 0.004 | 1.000 | 1.000 |
| b000-k40-base-r1 | base | 0.275/0.307 | 5/11 | 1/0 | 97.93/21.79 | 3.030 | 1.000 | 1.000 |
| b000-k40-base-r2 | base | 0.134/0.334 | 11/11 | 0/0 | 10.26/25.99 | 0.018 | 1.000 | 0.750 |
| b000-k40-quiet_guard-r0 | quiet_guard | 0.134/0.334 | 11/11 | 0/0 | 10.26/25.99 | 0.018 | 1.000 | 0.750 |
| b000-k40-quiet_guard-r1 | quiet_guard | 0.134/0.334 | 11/11 | 0/0 | 10.26/25.99 | 0.018 | 1.000 | 0.750 |
| b000-k40-quiet_guard-r2 | quiet_guard | 0.134/0.334 | 11/11 | 0/0 | 10.26/25.99 | 0.018 | 1.000 | 0.750 |
| b001-k20-base-r0 | base | 0.065/0.065 | 2/2 | 0/0 | 7.43/14.86 | 0.054 | 0.900 | 0.500 |
| b001-k20-base-r1 | base | 0.065/0.065 | 2/2 | 0/0 | 7.47/14.13 | 0.049 | 0.900 | 0.500 |
| b001-k20-base-r2 | base | 0.065/0.065 | 2/2 | 0/0 | 7.47/14.13 | 0.049 | 0.900 | 0.500 |
| b001-k20-quiet_guard-r0 | quiet_guard | 0.065/0.065 | 2/2 | 0/0 | 7.43/14.86 | 0.054 | 0.900 | 0.500 |
| b001-k20-quiet_guard-r1 | quiet_guard | 0.065/0.065 | 2/2 | 0/0 | 7.47/14.13 | 0.049 | 0.900 | 0.500 |
| b001-k20-quiet_guard-r2 | quiet_guard | 0.065/0.065 | 2/2 | 0/0 | 7.43/14.86 | 0.054 | 0.900 | 0.500 |
| b001-k30-base-r0 | base | 0.073/0.085 | 4/4 | 0/0 | 8.31/7.58 | 0.035 | 1.000 | 0.500 |
| b001-k30-base-r1 | base | 0.063/0.040 | 2/0 | 0/0 | 16.37/14.67 | 0.127 | 1.000 | 1.000 |
| b001-k30-base-r2 | base | 0.074/0.088 | 2/3 | 0/0 | 8.30/7.49 | 0.031 | 1.000 | 1.000 |
| b001-k30-quiet_guard-r0 | quiet_guard | 0.063/0.040 | 2/0 | 0/0 | 16.37/14.67 | 0.127 | 1.000 | 1.000 |
| b001-k30-quiet_guard-r1 | quiet_guard | 0.063/0.040 | 2/0 | 0/0 | 16.37/14.67 | 0.127 | 1.000 | 1.000 |
| b001-k30-quiet_guard-r2 | quiet_guard | 0.063/0.040 | 2/0 | 0/0 | 16.37/14.67 | 0.127 | 1.000 | 1.000 |
| c000-k1-base-r0 | base | 0.297/0.110 | 8/8 | 0/0 | 13.93/13.28 | 0.073 | 1.000 | 1.000 |
| c000-k1-base-r1 | base | 0.297/0.110 | 8/8 | 0/0 | 13.93/13.28 | 0.073 | 1.000 | 1.000 |
| c000-k1-base-r2 | base | 0.297/0.110 | 8/8 | 0/0 | 13.93/13.28 | 0.073 | 1.000 | 1.000 |
| c000-k1-quiet_guard-r0 | quiet_guard | 0.297/0.110 | 8/8 | 0/0 | 13.93/13.28 | 0.073 | 1.000 | 1.000 |
| c000-k1-quiet_guard-r1 | quiet_guard | 0.297/0.110 | 8/8 | 0/0 | 13.93/13.28 | 0.073 | 1.000 | 1.000 |
| c000-k1-quiet_guard-r2 | quiet_guard | 0.297/0.110 | 8/8 | 0/0 | 13.93/13.28 | 0.073 | 1.000 | 1.000 |
| c001-k1-base-r0 | base | 0.117/0.160 | 5/6 | 0/0 | 14.93/13.29 | 1.243 | 1.000 | - |
| c001-k1-base-r1 | base | 0.117/0.160 | 5/6 | 0/0 | 14.93/13.29 | 1.243 | 1.000 | - |
| c001-k1-base-r2 | base | 0.117/0.160 | 5/6 | 0/0 | 14.93/13.29 | 1.243 | 1.000 | - |
| c001-k1-quiet_guard-r0 | quiet_guard | 0.117/0.160 | 5/6 | 0/0 | 14.93/13.29 | 1.243 | 1.000 | - |
| c001-k1-quiet_guard-r1 | quiet_guard | 0.117/0.160 | 5/6 | 0/0 | 14.93/13.29 | 1.243 | 1.000 | - |
| c001-k1-quiet_guard-r2 | quiet_guard | 0.117/0.160 | 5/6 | 0/0 | 14.93/13.29 | 1.243 | 1.000 | - |

Coverage columns are the POST-shake soft/priority clean ratios recomputed under the published rules (see module docstring for the contract source). They are the instrument's payload once the gate passes; they take no part in the gate itself.
