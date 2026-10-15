# Counterfactual branches (cf.py)

Each branch forces the reference run up to step k, changes the placement at k, and lets the v50 agent (deterministic budgets) play to the end in the official simulator.  "lead" = placements before the reference run's end.  Margins against the count threshold (>= 0 crosses).  "null" = the agent's own answer at k replayed (the reference, up to the clocks of the resort and the shadow).

## Summary

| scene | ref margin | n | nearest rescuing k (lead) | rescuing kinds | null margins by k |
|---|---:|---:|---|---|---|
| b-hard2-s0039 | -2 | 20 | 13 (7) | most usable surface left, next in the rung, veto (agent's next answer) | 19:-2, 17:-2, 13:-2, 12:-2, 11:-2, 9:-2 |
| b-hard2-s0040 | -2 | 40 | - (-) | - | 39:-2, 37:-2, 16:-2, 15:-2, 14:-2, 12:-2 |
| b-hard2-s0067 | -3 | 68 | - (-) | - | 67:-3, 65:-3, 59:-4, 58:-4, 57:-4, 55:-4 |
| b-hard2-s0083 | -2 | 58 | - (-) | - | 57:-2, 55:-2, 53:-2, 50:-2 |
| c-hard2-s0007 | -1 | 20 | 12 (8) | a pose the ladder vetoed, ladder pick (vetoed downstream), most usable surface left, next in the rung, veto (agent's next answer) | 19:-1, 18:-1, 17:-1, 15:-1, 13:-1, 12:-1, 11:-1, 9:-1 |
| c-hard2-s0026 | +0 | 16 | - (-) | - | 15:+0 |
| c-hard2-s0028 | -1 | 13 | 12 (1) | a pose the ladder vetoed, another rung's best, most usable surface left, next in the rung, veto (agent's next answer) | 12:-1, 10:-1, 8:-1, 5:-1 |
| c-hard2-s0039 | -1 | 21 | 10 (11) | a pose the ladder vetoed, most usable surface left, veto (agent's next answer) | 20:-1, 18:-1, 10:-1, 9:-1, 8:-1, 6:-1 |
| c-hard2-s0076 | -1 | 21 | 13 (8) | most usable surface left, veto (agent's next answer) | 20:-1, 18:-1, 13:-1, 12:-1, 11:-1, 9:-1 |
| c-hard2-s0078 | -3 | 46 | 36 (10) | most usable surface left | 45:-3, 43:-3, 36:-3, 35:-3, 34:-3, 32:-3 |
| b-hard2-s0039 | -2 | 20 | - (-) | - | 13:-4 |

| alternative kind | branches | crossing | better than null |
|---|---:|---:|---:|
| veto (agent's next answer) | 112 | 9 | 15 |
| most usable surface left | 47 | 13 | 17 |
| next in the rung | 36 | 5 | 8 |
| a pose the ladder vetoed | 32 | 9 | 13 |
| ladder pick (vetoed downstream) | 20 | 1 | 1 |
| another rung's best | 8 | 2 | 2 |

## b-hard2-s0039: reference placed 20 (thr 22, margin -2); record placed 20

| k (lead) | at k the agent placed | null | alternatives: label -> margin (pose at k ok?) | best | crossing branches |
|---|---|---:|---|---:|---:|
| 19 (1) | count-mode | -2 | veto1 -2; veto2 -2 | -2 | 0 of 2 |
| 17 (3) | physics-resort | -2 | veto1 -3; veto2 -1 | -1 | 0 of 2 |
| 13 (7) | soft-edge | -2 | veto1 -2; veto2 +0; rung1 -2; rung2 -2; rung3 +0; other:elongated-wall -3; vetoed:corridor,wall-front-strip -3 | +0 | 2 of 7 |
| 12 (8) | wedge-soft-cap | -2 | veto1 -2; veto2 -2; rung1 -2; rung3 -2; rung5 -2; maxsurf1 -2; maxsurf2 -2 | -2 | 0 of 7 |
| 11 (9) | max-footprint | -2 | veto1 -2; veto2 -2; rung7 -2; vetoed:reserved-zone -2; maxsurf1 -5; maxsurf2 +0 | +0 | 1 of 6 |
| 9 (11) | max-footprint | -2 | veto1 -1; veto2 -1; rung1 -2; rung2 -2; rung3 -1; other:back-corner -2; vetoed:reserved-zone -1; maxsurf1 +2; maxsurf2 -3 | +2 | 1 of 9 |

## b-hard2-s0040: reference placed 40 (thr 42, margin -2); record placed 41

| k (lead) | at k the agent placed | null | alternatives: label -> margin (pose at k ok?) | best | crossing branches |
|---|---|---:|---|---:|---:|
| 39 (1) | stack-rl | -2 | veto1 -2; veto2 -2 | -2 | 0 of 2 |
| 37 (3) | stack-rl | -2 | veto1 -2; veto2 -2 | -2 | 0 of 2 |
| 16 (24) | max-footprint | -2 | veto1 -8; veto2 -12; rung1 -2; vetoed:wall-front-strip -2 | -2 | 0 of 4 |
| 15 (25) | terrace-extension | -2 | veto1 -22; veto2 -2; rung1 -27 (fails); rung2 -27 (fails); rung3 -27 (fails); other:max-footprint -27 (fails) | -2 | 0 of 6 |
| 14 (26) | terrace-extension | -2 | veto1 -23; veto2 -22; rung2 -28 (fails); rung3 -23; rung4 -22 | -2 | 0 of 5 |
| 12 (28) | fallback | -2 | veto1 -2; veto2 -2; vetoed:overhangs-the-shelf -10; maxsurf1 -10; maxsurf2 -11 | -2 | 0 of 5 |

## b-hard2-s0067: reference placed 68 (thr 71, margin -3); record placed 70

| k (lead) | at k the agent placed | null | alternatives: label -> margin (pose at k ok?) | best | crossing branches |
|---|---|---:|---|---:|---:|
| 67 (1) | grid-rescue | -3 | veto1 -3; veto2 -3 | -3 | 0 of 2 |
| 65 (3) | stack-rl | -3 | veto1 -3; veto2 -3 | -3 | 0 of 2 |
| 59 (9) | max-footprint | -4 | veto1 -3; veto2 -3; rung2 -3; rung3 -3; vetoed:too-many-layers -4 | -3 | 0 of 5 |
| 58 (10) | terrace-extension | -4 | veto1 -3; veto2 -5; vetoed:no-plateau-to-build-on,would-wall-off-the-back -2 | -2 | 0 of 3 |
| 57 (11) | terrace-extension | -4 | veto1 -4; veto2 -4; vetoed:too-many-layers -4 | -4 | 0 of 3 |
| 55 (13) | terrace-extension | -4 | veto1 -4; veto2 -4; vetoed:too-many-layers -2; maxsurf1 -3; maxsurf2 -3 | -2 | 0 of 5 |

## b-hard2-s0083: reference placed 58 (thr 60, margin -2); record placed 58

| k (lead) | at k the agent placed | null | alternatives: label -> margin (pose at k ok?) | best | crossing branches |
|---|---|---:|---|---:|---:|
| 57 (1) | terrace-extension | -2 | veto1 -2; veto2 -2; rung2 -2; rung3 -2; rung4 -2; other:max-footprint -2; vetoed:no-plateau-to-build-on,would-wall-off-the-back -2 | -2 | 0 of 7 |
| 55 (3) | stack-rl | -2 | veto1 -2; veto2 -2 | -2 | 0 of 2 |
| 53 (5) | stack-rl | -2 | veto1 -2; veto2 -2 | -2 | 0 of 2 |
| 50 (8) | terrace-extension | -2 | veto1 -2; veto2 -2; rung5 -2; rung6 -2; rung7 -2; other:max-footprint -2; vetoed:free-standing-tipping-risk -2 | -2 | 0 of 7 |

## c-hard2-s0007: reference placed 20 (thr 21, margin -1); record placed 20

| k (lead) | at k the agent placed | null | alternatives: label -> margin (pose at k ok?) | best | crossing branches |
|---|---|---:|---|---:|---:|
| 19 (1) | physics-resort | -1 | veto1 -1; veto2 -1; veto3 -1 | -1 | 0 of 3 |
| 18 (2) | max-footprint | -1 | veto1 -1; veto2 -1; veto3 -1; rung1 -1; rung2 -1; vetoed:reserved-zone -1 | -1 | 0 of 6 |
| 17 (3) | physics-resort | -1 | veto1 -1; veto2 -1; veto3 -1 | -1 | 0 of 3 |
| 15 (5) | count-mode | -1 | veto1 -1; veto2 -1; veto3 -1; rung1 -2; vetoed:no-plateau-to-build-on,would-wall-off-the-back -2 | -1 | 0 of 5 |
| 13 (7) | physics-resort | -1 | veto1 -1; veto2 -1; veto3 -1; rung1 -2; vetoed:free-standing-tipping-risk,seals-usable-ground-behind -1; vetoed:blocks-wedge-approach,seals-usable-ground-behind,wall-front-strip -1 | -1 | 0 of 6 |
| 12 (8) | max-footprint | -1 | veto1 -2; veto2 +3; veto3 +3; rung3 -1; rung4 +3; vetoed:wall-front-strip +3; maxsurf1 -1; maxsurf2 +3 | +3 | 5 of 8 |
| 11 (9) | pocket-soft | -1 | veto1 -1; veto2 -1; veto3 -2; rung1 +0; vetoed:wall-front-strip -1; vetoed:none -3; vetoed:seals-usable-ground-behind,wall-front-strip -3; maxsurf1 +2; maxsurf2 -1 | +2 | 2 of 9 |
| 9 (11) | soft-edge | -1 | veto1 -1; veto2 -1; veto3 -1; rung1 -1; rung2 -1; rung4 -1; vetoed:would-wall-off-the-back +0; maxsurf1 -1; maxsurf2 -1 | +0 | 1 of 9 |

## c-hard2-s0026: reference placed 16 (thr 16, margin +0); record placed 16

| k (lead) | at k the agent placed | null | alternatives: label -> margin (pose at k ok?) | best | crossing branches |
|---|---|---:|---|---:|---:|
| 15 (1) | count-mode | +0 |  | +0 | 0 of 0 |

## c-hard2-s0028: reference placed 13 (thr 14, margin -1); record placed 13

| k (lead) | at k the agent placed | null | alternatives: label -> margin (pose at k ok?) | best | crossing branches |
|---|---|---:|---|---:|---:|
| 12 (1) | terrace-extension | -1 | veto1 -1; veto2 +2; rung1 -1; rung2 +0; rung3 +0; other:front-wedge +0; vetoed:overhangs-the-shelf +3; maxsurf1 +3; maxsurf2 +3 | +3 | 7 of 9 |
| 10 (3) | wedge-step | -1 | veto1 -1; veto2 -1; rung4 -1; rung8 -1; rung11 -1; other:terrace-extension -1; vetoed:no-plateau-to-build-on -1; maxsurf1 -1; maxsurf2 -1 | -1 | 0 of 9 |
| 8 (5) | max-footprint | -1 | veto1 -1; veto2 +0; rung1 -1; rung2 -1; rung3 +0; other:back-corner +0; vetoed:overhangs-the-shelf +2; maxsurf1 +2; maxsurf2 -1 | +2 | 5 of 9 |
| 5 (8) | terrace-extension | -1 | veto1 -1; veto2 -1; vetoed:no-plateau-to-build-on -1; vetoed:overhangs-the-shelf +2; maxsurf1 +2; maxsurf2 +5 | +5 | 3 of 6 |

## c-hard2-s0039: reference placed 21 (thr 22, margin -1); record placed 21

| k (lead) | at k the agent placed | null | alternatives: label -> margin (pose at k ok?) | best | crossing branches |
|---|---|---:|---|---:|---:|
| 20 (1) | count-mode | -1 | veto1 -1; veto2 -1 | -1 | 0 of 2 |
| 18 (3) | count-mode | -1 | veto1 -1; veto2 -2 | -1 | 0 of 2 |
| 10 (11) | priority-edge | -1 | veto1 -1; veto2 -1; rung1 -1; rung4 -1; vetoed:corridor,wall-front-strip +0; vetoed:corridor,seals-usable-ground-behind,wall-front-strip +0; maxsurf1 -1; maxsurf2 +0 | +0 | 3 of 8 |
| 9 (12) | max-footprint | -1 | veto1 -1; veto2 -3; rung1 -1; rung2 -3; rung3 -1; vetoed:wall-front-strip -1; maxsurf1 -1; maxsurf2 -2 | -1 | 0 of 8 |
| 8 (13) | pocket-soft | -1 | veto1 +1; veto2 -1; rung1 -1; rung2 -1; rung5 -1; vetoed:wall-front-strip +1; maxsurf1 -1; maxsurf2 -1 | +1 | 2 of 8 |
| 6 (15) | terrace-extension | -1 | veto1 +3; veto2 -1; rung1 -1; vetoed:wall-front-strip +3; maxsurf1 -1; maxsurf2 -1 | +3 | 2 of 6 |

## c-hard2-s0076: reference placed 21 (thr 22, margin -1); record placed 21

| k (lead) | at k the agent placed | null | alternatives: label -> margin (pose at k ok?) | best | crossing branches |
|---|---|---:|---|---:|---:|
| 20 (1) | physics-resort | -1 | veto1 -1; veto2 -1 | -1 | 0 of 2 |
| 18 (3) | physics-resort | -1 | veto1 -1; veto2 -1 | -1 | 0 of 2 |
| 13 (8) | stack-rl | -1 | veto1 -1; veto2 +0 | +0 | 1 of 2 |
| 12 (9) | max-footprint | -1 | veto1 -1; veto2 -1; rung1 -1; maxsurf1 -1; maxsurf2 -1 | -1 | 0 of 5 |
| 11 (10) | shelf-space-saving | -1 | veto1 -1; veto2 -1; maxsurf1 +0; maxsurf2 +0 | +0 | 2 of 4 |
| 9 (12) | soft-edge | -1 | veto1 -1; veto2 +0; maxsurf1 -1; maxsurf2 -1 | +0 | 1 of 4 |

## c-hard2-s0078: reference placed 46 (thr 49, margin -3); record placed 46

| k (lead) | at k the agent placed | null | alternatives: label -> margin (pose at k ok?) | best | crossing branches |
|---|---|---:|---|---:|---:|
| 45 (1) | physics-resort | -3 | veto1 -3; veto2 -3 | -3 | 0 of 2 |
| 43 (3) | physics-resort | -3 | veto1 -3; veto2 -3; maxsurf1 -1 | -1 | 0 of 3 |
| 36 (10) | max-footprint | -3 | veto1 -3; veto2 -5; maxsurf1 +0; maxsurf2 -3 | +0 | 1 of 4 |
| 35 (11) | wedge-step | -3 | veto1 -3; veto2 -3; maxsurf1 -3; maxsurf2 -3 | -3 | 0 of 4 |
| 34 (12) | max-footprint | -3 | veto1 -5; veto2 -3; rung1 -3; vetoed:overhangs-the-shelf -4; maxsurf1 -3; maxsurf2 -1 | -1 | 0 of 6 |
| 32 (14) | max-footprint | -3 | veto1 -3; veto2 -3; rung1 -5; vetoed:overhangs-the-shelf -1; maxsurf1 -6; maxsurf2 -6 | -1 | 0 of 6 |

## b-hard2-s0039: reference placed 20 (thr 22, margin -2); record placed 20

| k (lead) | at k the agent placed | null | alternatives: label -> margin (pose at k ok?) | best | crossing branches |
|---|---|---:|---|---:|---:|
| 13 (7) | soft-edge | -4 |  | -4 | 0 of 0 |

