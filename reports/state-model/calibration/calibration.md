# Safety shadow calibration (Gate 1)

Protocol: `reports/state-model/calibration-protocol.md`

- episodes: 21 completed with shadow of 21 total
- terminal channels: {"slide": 2, "topple": 12, "transport_invalid": 7}
- events: 378 surviving, 14 fatal
- pooled AUC (surviving over fatal): 0.9333
- median logit: surviving 8.934467923842966, fatal -0.16051951951820825
- gates: {"coverage": true, "power": true, "discrimination": true, "direction": true}
- **verdict: calibration_pass_gate2_licensed**

## Calibration by logit band

| band | n | empirical survival | mean predicted survival |
|---|---|---|---|
| below_0 | 30 | 0.7333 | 0.3142 |
| 0_to_2 | 50 | 0.88 | 0.7632 |
| 2_to_5 | 50 | 1.0 | 0.966 |
| 5_to_10 | 88 | 1.0 | 0.9991 |
| 10_up | 174 | 1.0 | 1.0 |

## Split by candidate kind

| group | surviving n | fatal n | AUC | median surviving | median fatal |
|---|---|---|---|---|---|
| candidate | 192 | 0 | None | 18.762717129983077 | None |
| release_candidate | 186 | 14 | 0.8644 | 3.800719085589504 | -0.16051951951820825 |

## Split by step band

| group | surviving n | fatal n | AUC | median surviving | median fatal |
|---|---|---|---|---|---|
| early_0_7 | 147 | 0 | None | 18.948749023937 | None |
| late_16_up | 49 | 11 | 0.7384 | 1.6525230236005146 | -0.16051951951820825 |
| mid_8_15 | 143 | 3 | 0.9394 | 6.695291374875845 | 1.0513374374449738 |
| unbanded | 39 | 0 | None | 5.6637654411122025 | None |

## Per case

| group | surviving n | fatal n | AUC | median surviving | median fatal |
|---|---|---|---|---|---|
| b000-k15 | 55 | 2 | 0.8909 | 10.467833115486208 | -0.2503864308440906 |
| b000-k20 | 61 | 2 | 0.9508 | 3.1147226180456498 | -0.16051951951820825 |
| b000-k40 | 50 | 2 | 0.95 | 11.146716981390679 | -1.167237602593142 |
| b001-k20 | 50 | 2 | 0.96 | 10.291752849752148 | 1.0513374374449738 |
| b001-k30 | 51 | 3 | 0.9412 | 9.20113011040711 | 1.8434313933693398 |
| c000-k1 | 48 | 3 | 1.0 | 8.394961971251764 | -1.4825918907593427 |
| c001-k1 | 63 | 0 | None | 7.81749554835506 | None |

## Fatal events

| case | episode | channel | step | logit | kind |
|---|---|---|---|---|---|
| b000-k15 | b000-k15-base-r0 | topple | 17 | -0.25 | release_candidate |
| b000-k15 | b000-k15-base-r2 | topple | 17 | -0.25 | release_candidate |
| b000-k20 | b000-k20-base-r1 | topple | 20 | -0.161 | release_candidate |
| b000-k20 | b000-k20-base-r2 | topple | 20 | -0.161 | release_candidate |
| b000-k40 | b000-k40-base-r0 | topple | 16 | 0.064 | release_candidate |
| b000-k40 | b000-k40-base-r2 | topple | 13 | -2.398 | release_candidate |
| b001-k20 | b001-k20-base-r0 | slide | 14 | 1.051 | release_candidate |
| b001-k20 | b001-k20-base-r1 | slide | 14 | 1.051 | release_candidate |
| b001-k30 | b001-k30-base-r0 | topple | 17 | 1.843 | release_candidate |
| b001-k30 | b001-k30-base-r1 | topple | 17 | 1.843 | release_candidate |
| b001-k30 | b001-k30-base-r2 | topple | 17 | 1.843 | release_candidate |
| c000-k1 | c000-k1-base-r0 | topple | 16 | -1.483 | release_candidate |
| c000-k1 | c000-k1-base-r1 | topple | 16 | -1.483 | release_candidate |
| c000-k1 | c000-k1-base-r2 | topple | 16 | -1.483 | release_candidate |
