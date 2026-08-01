# Terminal-failure post-mortem: channels, then model verdicts

- fatal placements analysed: 103 (container rebuilt from observed settle AABBs; P_rot from the frozen mech model on the commanded pose)

## Death channels

| channel | episodes |
|---|---:|
| topple | 47 |
| transport_invalid | 41 |
| slide | 15 |

The rotation model can only answer for the topple channel:

- KNOWN (P_rot >= 0.5): 9 -- flagged; failure is starvation or an insufficient penalty.
- AMBIGUOUS (0.2-0.5): 26
- MISSED (P_rot < 0.2): 12 -- rotation-model false negatives, the model-improvement targets.

transport_invalid deaths never reach physics -- they are a candidate-generation / transport-validation problem and no release-risk lambda can fix them.

| episode | arm | channel | P_rot | settle angle | displacement |
|---|---|---|---:|---:|---:|
| b000-k10-base-r51 | base | slide | 0.007 | 5.5 | 0.439 |
| b000-k10-base-r52 | base | slide | 0.007 | 5.5 | 0.439 |
| b000-k20-base-r7 | base | slide | 0.013 | 27.8 | 0.438 |
| b000-k20-base-r30 | base | slide | 0.013 | 27.8 | 0.438 |
| b000-k20-base-r31 | base | slide | 0.013 | 27.8 | 0.438 |
| b000-k20-base-r40 | base | slide | 0.013 | 27.8 | 0.438 |
| b000-k40-off-r0 | off | slide | 0.192 | 29.2 | 0.519 |
| b000-k40-off-r1 | off | slide | 0.192 | 29.2 | 0.519 |
| b000-k40-mech-lam1-r0 | mech-lam1 | slide | 0.197 | 29.2 | 0.526 |
| b000-k40-base-r0 | base | slide | 0.197 | 29.2 | 0.526 |
| b000-k40-slide05-r0 | slide05 | slide | 0.197 | 29.2 | 0.526 |
| b000-k40-mech-lam2-r0 | mech-lam2 | slide | 0.198 | 29.2 | 0.527 |
| b000-k40-mech-lam2-r1 | mech-lam2 | slide | 0.198 | 29.2 | 0.527 |
| b000-k40-mech-lam4-r0 | mech-lam4 | slide | 0.198 | 29.2 | 0.527 |
| b000-k20-base-r41 | base | slide | 0.297 | 4.3 | 0.722 |
| b001-k20-mech-lam4-r0 | mech-lam4 | topple | 0.014 | 48.7 | 0.504 |
| b001-k20-base-r7 | base | topple | 0.014 | 92.4 | 1.057 |
| b001-k20-base-r30 | base | topple | 0.014 | 92.4 | 1.057 |
| b001-k20-base-r31 | base | topple | 0.014 | 92.4 | 1.057 |
| b001-k20-base-r32 | base | topple | 0.014 | 92.4 | 1.057 |
| b001-k20-base-r40 | base | topple | 0.014 | 92.4 | 1.057 |
| b001-k20-off-r0 | off | topple | 0.068 | 62.0 | 0.988 |
| b001-k30-mech-lam2-r1 | mech-lam2 | topple | 0.072 | 45.3 | 0.721 |
| b001-k30-mech-lam4-r0 | mech-lam4 | topple | 0.182 | 98.5 | 0.961 |
| b000-k40-slide10-r0 | slide10 | topple | 0.188 | 40.2 | 0.444 |
| b000-k20-base-r32 | base | topple | 0.189 | 37.1 | 0.592 |
| b000-k20-base-r42 | base | topple | 0.192 | 44.7 | 0.525 |
| b000-k15-base-r7 | base | topple | 0.206 | 68.2 | 0.405 |
| b000-k15-base-r31 | base | topple | 0.206 | 68.2 | 0.405 |
| b000-k15-base-r30 | base | topple | 0.206 | 68.2 | 0.405 |
| b000-k15-base-r32 | base | topple | 0.206 | 68.2 | 0.405 |
| b000-k15-base-r40 | base | topple | 0.206 | 68.2 | 0.405 |
| b000-k15-slide05-r0 | slide05 | topple | 0.234 | 92.9 | 0.976 |
| b000-k15-off-r0 | off | topple | 0.267 | 90.0 | 0.438 |
| b000-k15-off-r1 | off | topple | 0.267 | 90.0 | 0.438 |
| b001-k30-slide10-r0 | slide10 | topple | 0.274 | 131.2 | 0.896 |
| b000-k20-mech-lam2-r0 | mech-lam2 | topple | 0.281 | 73.7 | 0.615 |
| b000-k20-mech-lam2-r1 | mech-lam2 | topple | 0.281 | 73.7 | 0.615 |
| b000-k15-mech-lam2-r0 | mech-lam2 | topple | 0.319 | 51.6 | 0.386 |
| b000-k15-mech-lam4-r0 | mech-lam4 | topple | 0.319 | 51.6 | 0.386 |
| b000-k15-mech-lam2-r1 | mech-lam2 | topple | 0.319 | 51.6 | 0.386 |
| b000-k15-slide10-r0 | slide10 | topple | 0.338 | 90.1 | 1.038 |
| b000-k15-base-r41 | base | topple | 0.338 | 90.1 | 1.038 |
| b000-k15-base-r42 | base | topple | 0.338 | 90.1 | 1.038 |
| b001-k40-off-r1 | off | topple | 0.340 | 180.0 | 1.303 |
| b001-k20-slide10-r0 | slide10 | topple | 0.363 | 180.0 | 0.843 |
| b000-k15-mech-lam1-r0 | mech-lam1 | topple | 0.406 | 90.0 | 0.401 |
| b000-k15-base-r0 | base | topple | 0.406 | 90.0 | 0.401 |
| b001-k20-mech-lam2-r1 | mech-lam2 | topple | 0.470 | 90.1 | 0.591 |
| b000-k20-off-r0 | off | topple | 0.470 | 57.9 | 0.321 |
| b000-k20-off-r1 | off | topple | 0.470 | 57.9 | 0.321 |
| b001-k20-mech-lam1-r0 | mech-lam1 | topple | 0.498 | 179.6 | 0.746 |
| b001-k20-mech-lam2-r0 | mech-lam2 | topple | 0.498 | 179.3 | 0.747 |
| b001-k10-off-r0 | off | topple | 0.606 | 51.0 | 0.151 |
| b001-k10-off-r1 | off | topple | 0.606 | 51.0 | 0.151 |
| b001-k30-off-r0 | off | topple | 0.606 | 90.0 | 0.396 |
| b001-k30-off-r1 | off | topple | 0.606 | 90.0 | 0.396 |
| b001-k40-off-r0 | off | topple | 0.606 | 90.0 | 0.396 |
| b001-k10-base-r60 | base | topple | 0.630 | 179.9 | 1.282 |
| b001-k10-base-r61 | base | topple | 0.630 | 179.9 | 1.282 |
| b001-k40-mech-lam1-r1 | mech-lam1 | topple | 0.689 | 90.0 | 1.268 |
| b000-k40-base-r42 | base | topple | 0.714 | 180.0 | 1.409 |
| b000-k10-mech-lam4-r0 | mech-lam4 | transport_invalid | 0.002 | 0.0 | 0.000 |
| b000-k10-mech-lam4-r1 | mech-lam4 | transport_invalid | 0.002 | 0.0 | 0.000 |
| b000-k10-mech-lam2-r0 | mech-lam2 | transport_invalid | 0.006 | 0.0 | 0.000 |
| b000-k10-mech-lam2-r1 | mech-lam2 | transport_invalid | 0.006 | 0.0 | 0.000 |
| b000-k10-base-r50 | base | transport_invalid | 0.013 | 0.0 | 0.000 |
| b001-k20-slide05-r0 | slide05 | transport_invalid | 0.014 | 0.0 | 0.000 |
| b001-k10-mech-lam1-r1 | mech-lam1 | transport_invalid | 0.014 | 0.0 | 0.000 |
| b000-k20-mech-lam4-r0 | mech-lam4 | transport_invalid | 0.015 | 0.0 | 0.000 |
| b000-k20-slide05-r0 | slide05 | transport_invalid | 0.015 | 0.0 | 0.000 |
| b000-k20-slide10-r0 | slide10 | transport_invalid | 0.015 | 0.0 | 0.000 |
| b001-k30-base-r0 | base | transport_invalid | 0.023 | 0.0 | 0.000 |
| b001-k10-mech-lam1-r0 | mech-lam1 | transport_invalid | 0.023 | 0.0 | 0.000 |
| b001-k20-base-r0 | base | transport_invalid | 0.025 | 0.0 | 0.000 |
| b001-k20-base-r41 | base | transport_invalid | 0.025 | 0.0 | 0.000 |
| b001-k20-base-r42 | base | transport_invalid | 0.025 | 0.0 | 0.000 |
| b001-k30-base-r7 | base | transport_invalid | 0.040 | 0.0 | 0.000 |
| b001-k30-base-r30 | base | transport_invalid | 0.040 | 0.0 | 0.000 |
| b001-k30-base-r31 | base | transport_invalid | 0.040 | 0.0 | 0.000 |
| b001-k30-base-r40 | base | transport_invalid | 0.040 | 0.0 | 0.000 |
| b001-k40-base-r60 | base | transport_invalid | 0.040 | 0.0 | 0.000 |
| b000-k40-base-r7 | base | transport_invalid | 0.073 | 0.0 | 0.000 |
| b000-k40-base-r30 | base | transport_invalid | 0.073 | 0.0 | 0.000 |
| b000-k40-base-r31 | base | transport_invalid | 0.073 | 0.0 | 0.000 |
| b000-k40-base-r32 | base | transport_invalid | 0.073 | 0.0 | 0.000 |
| b000-k40-base-r40 | base | transport_invalid | 0.073 | 0.0 | 0.000 |
| b001-k30-mech-lam1-r0 | mech-lam1 | transport_invalid | 0.090 | 0.0 | 0.000 |
| b001-k40-mech-lam1-r0 | mech-lam1 | transport_invalid | 0.090 | 0.0 | 0.000 |
| b000-k10-off-r0 | off | transport_invalid | 0.094 | 0.0 | 0.000 |
| b000-k10-off-r1 | off | transport_invalid | 0.094 | 0.0 | 0.000 |
| b000-k10-mech-lam1-r1 | mech-lam1 | transport_invalid | 0.094 | 0.0 | 0.000 |
| b001-k20-off-r1 | off | transport_invalid | 0.102 | 0.0 | 0.000 |
| b000-k40-base-r41 | base | transport_invalid | 0.129 | 0.0 | 0.000 |
| b001-k30-base-r41 | base | transport_invalid | 0.132 | 0.0 | 0.000 |
| b001-k30-mech-lam2-r0 | mech-lam2 | transport_invalid | 0.149 | 0.0 | 0.000 |
| b000-k20-mech-lam1-r0 | mech-lam1 | transport_invalid | 0.159 | 0.0 | 0.000 |
| b000-k20-base-r0 | base | transport_invalid | 0.159 | 0.0 | 0.000 |
| b001-k30-base-r32 | base | transport_invalid | 0.185 | 0.0 | 0.000 |
| b001-k30-base-r42 | base | transport_invalid | 0.185 | 0.0 | 0.000 |
| b001-k40-base-r61 | base | transport_invalid | 0.185 | 0.0 | 0.000 |
| b001-k30-slide05-r0 | slide05 | transport_invalid | 0.188 | 0.0 | 0.000 |
| b000-k10-mech-lam1-r0 | mech-lam1 | transport_invalid | 0.192 | 0.0 | 0.000 |

