# Orientation at the hard floor placements (orient.py)

Every step of a reference run where the agent put a hard box on the floor.  "legal standing" = floor poses with the height not the smallest side and > 0.3 m that the ladder's generator and validator produce (no vetoes); "standing survivor" = one left after the ladder's orientation policy, shortlist and vetoes.  Floor = usable floor (0.58 x 0.43 window).

| group | floor placements | agent stood the box | a legal standing pose existed | a standing survivor existed | lying chosen while a standing survivor existed | usable floor lost by the agent (mean) | by the best standing survivor (when one existed, the agent lying) | by the best legal standing pose (agent lying) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| H | 200 | 83 | 148 | 116 | 40 | 0.317 | agent 0.310 vs standing 0.171 (n=40) | agent 0.390 vs standing 0.129 (n=101) |
| X | 113 | 53 | 82 | 64 | 23 | 0.308 | agent 0.353 vs standing 0.197 (n=23) | agent 0.416 vs standing 0.144 (n=52) |

## What removed the standing floor poses that were shortlisted (veto counts)

| group | vetoes |
|---|---|
| H | reserved-zone 460, wall-front-strip 241, seals-usable-ground-behind 184, would-wall-off-the-back 107, blocks-wedge-approach 84, low-footprint-pose 78, free-standing-tipping-risk 54, corridor 46, front-would-stand-too-tall 29 |
| X | reserved-zone 313, wall-front-strip 120, would-wall-off-the-back 70, low-footprint-pose 57, seals-usable-ground-behind 53, corridor 46, blocks-wedge-approach 41, free-standing-tipping-risk 23, front-would-stand-too-tall 17 |

## The best standing survivor when the agent laid the box: its rank in the chosen rung and whether it would stand (shadow)

| group | n | rank 2-3 / 4-10 / >10 | shadow ok / soft veto / hard veto (tips or slides) | shade > 0.15 |
|---|---:|---|---|---:|
| H | 40 | 6 / 34 / 0 | 40 / 0 / 0 | 1 |
| X | 23 | 4 / 19 / 0 | 23 / 0 / 0 | 1 |
