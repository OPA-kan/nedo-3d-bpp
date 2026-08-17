# Physics probe fidelity gates

Protocol: `reports/hazard/physics-probe-protocol.md`

- probe episodes: 14 (arm `physics_probe`); base episodes: 14 (arm `base`)
- joined steps: 260 (13 actually unsafe, 247 safe)
- join audit: {"events": 260, "events_failed": 0, "events_out_of_range": 0, "events_without_settle": 0, "step_field_mismatches": 0}
- probe elapsed seconds: {"mean": 0.149772, "max": 0.540255}
- **verdict: fidelity_fail_line_closed**

## Gates

| gate | measured | requirement | pass |
|---|---|---|---|
| 1 discrimination | AUC 0.9801 | >= 0.8 | True |
| 2 fatal recall | 8/10 = 0.8 | >= 0.5 | True |
| 3 calibration direction | {"displacement_unsafe": 0.262225, "displacement_safe": 0.059086, "angle_unsafe": 27.996117, "angle_safe": 1.956954} | unsafe means strictly higher | True |
| 4 zero footprint | probe s mean 0.149772 max 0.540255 | within base floors and mean <= 0.3 s/probe | False |

## Confusion (official thresholds)

| | actual unsafe | actual safe |
|---|---|---|
| predicted unsafe | 11 | 1 |
| predicted safe | 2 | 246 |

## Zero footprint by case

| case | probe placed | base placed floor | placed ok | probe steps | base steps floor | steps ok |
|---|---|---|---|---|---|---|
| b000-k15 | [21, 17] | 17 | True | [22, 18] | 18 | True |
| b000-k20 | [21, 18] | 20 | False | [22, 19] | 21 | False |
| b000-k40 | [16, 20] | 18 | False | [17, 21] | 19 | False |
| b001-k20 | [15, 14] | 15 | False | [16, 15] | 16 | False |
| b001-k30 | [17, 17] | 17 | True | [18, 18] | 18 | True |
| c000-k1 | [16, 16] | 16 | True | [17, 17] | 17 | True |
| c001-k1 | [21, 21] | 21 | True | [22, 22] | 22 | True |

## Fatal steps

| case | episode | channel | flagged | predicted angle | predicted disp | actual angle | actual disp |
|---|---|---|---|---|---|---|---|
| b000-k15 | b000-k15-physics_probe-r1 | topple | True | 39.76459837580522 | 0.29311641930876203 | 46.41042217420548 | 0.3471812382246107 |
| b000-k20 | b000-k20-physics_probe-r1 | slide | True | 0.9699198226687492 | 0.30754172724412066 | 1.3506846713929934 | 0.3126918753717764 |
| b000-k40 | b000-k40-physics_probe-r0 | topple | True | 69.73844596967291 | 0.7245410181945561 | 91.94008158011802 | 0.965264631827733 |
| b000-k40 | b000-k40-physics_probe-r1 | topple | True | 39.58871109991071 | 0.1820000527301867 | 90.10786870749938 | 0.9853199212193766 |
| b001-k20 | b001-k20-physics_probe-r0 | topple | True | 56.71249084947476 | 0.2671495684293117 | 56.27667930424417 | 0.25838094448855053 |
| b001-k20 | b001-k20-physics_probe-r1 | topple | True | 33.32754250701125 | 0.12885689849455492 | 71.36848595559584 | 0.4740291701243605 |
| b001-k30 | b001-k30-physics_probe-r0 | topple | False | 3.2630136056545287 | 0.1155112126588343 | 90.21713723313816 | 1.3195148552226545 |
| b001-k30 | b001-k30-physics_probe-r1 | topple | False | 3.2630136056545287 | 0.1155112126588343 | 90.21713723313816 | 1.3195148552226545 |
| c000-k1 | c000-k1-physics_probe-r0 | topple | True | 6.63110417262269 | 0.3328699940801504 | 46.338709567779574 | 0.4794718329069125 |
| c000-k1 | c000-k1-physics_probe-r1 | topple | True | 6.63110417262269 | 0.3328699940801504 | 46.338709567779574 | 0.4794718329069125 |
