# The cliff veto: a rung's pick that closes a cliff's worth of surface yields to a survivor that halves it (Tasks B and C)

The usable-surface trajectory of an online episode is a staircase
(`reports/wedge/findings.md`, "The usable surface falls in cliffs"): 3-5
placements an episode each close 0.12-0.21 of the floor area, two to three
times the box's own footprint, from many archetypes, and the ratio then sits
on a plateau (0.26, 0.14) for 5-8 placements until the decline. The surface
arbiter (`surface_arbiter`: the top-4 candidate keeping the most surface,
margin 0.05 m^2, every step) priced -0.42 on sample C and is off. This round
built the narrower lever the finding asked for -- a veto that acts only on
the cliffs, only in the middle band of the phase, and only when a survivor
of the same rung halves the cliff -- priced it with `bench.platform_score`
against the shipped-form bases on the four C and B suites, and traced what
it reads at every band step of twelve sample episodes.

## 1. What was built (commit 19bde961)

`config.cliff_veto` (off), `cliff_veto_low` 0.25, `cliff_veto_high` 0.6,
`cliff_veto_close` 0.12, `cliff_veto_k` 6, `cliff_veto_seconds` 0.3;
`surface.closed_share`, `surface.cliff_veto`; the ladder's call in
`layer1.choose_for_item` after the surface arbiter and before the selector;
the agent's band reading `RuleAlphaAgent._cliff_band`.

- **The band.** Once a policy call, before any ladder call, the agent reads
  every container's usable surface over its floor area
  (`surface.usable_surface_ratio`, the phase switch's window
  `0.40x0.55x0.24`, about 2 ms a call) and marks on the board the containers
  whose ratio lies in [0.25, 0.6] (`board.cliff_band`). Above the band the
  floor is open and a cliff costs nothing yet; under it the low phase's
  rescues place and the ladder's picks are few.
- **The measure.** `closed_share`: the rung's pick is stamped on the
  arbiter's 2 cm heightmap (`SurfaceScorer`, the same `_Load`), and what it
  closes beyond its own footprint is the usable surface before less after,
  less the cells of its footprint that were usable (the arbiter's credit: a
  flat box on a level patch is charged nothing for the cells under it), over
  the floor area. Negative when the top it offers back is more than what it
  closes beside it.
- **The veto.** In the band, when the pick closes more than
  `cliff_veto_close` of the floor beyond its footprint, the next
  `cliff_veto_k - 1` survivors of the same rung, in the rung's order, are
  read and the first that closes less than half of it takes the pick's place
  (archetype `cliff/<rung>`); otherwise the pick stands. Every step that is
  not a cliff is the ladder's.
- **The record.** `agent.cliff_stats` reaches the record's metrics as
  `cliff`: `reads` and `read_seconds` (the band reading), `band_steps`
  (calls with a container in the band), `checks` (ladder picks read),
  `cliffs` (picks over the threshold), `fired` and `fired_<rung>`,
  `timeouts`, `seconds`.
- **Arms.** `reports/bench/arms/arm_cliff_{c,b}.txt`: the shipped C and B
  forms plus `cliff_veto=true`; `arm_cliff08_{c,b}.txt`: the same at
  `cliff_veto_close=0.08`.
- **Tests.** `tests/test_cliff.py`: a 1.05 x 0.6 m strip of free floor that a
  0.55 x 0.40 box laid in the middle splits into two 0.25 m pieces (closing
  0.22 of the floor beyond its footprint) and the same box at the side does
  not (0.07); the veto takes the side pose, holds the pick when it is first,
  respects the threshold, k and the budget; the ladder asks it only with the
  switch on and the container in the band; the agent's band reading.

## 2. What the veto reads (sample C and B, seeds 0-5, local physics runs)

A probe (`scratchpad/cliff_diag.py`, the `cliff08` arms) logged, at every
ladder pick in the band, the closed share of the pick and of the next five
survivors of its rung, beside the per-step usable-surface ratio.

**The raw cliffs are the footprint.** Of 63 steps whose ratio fell by more
than 0.12 in the twelve episodes, 30 fell in the band and 20 of those were
placed by a ladder rung with more than one survivor (the steps the veto
reads). Not one of the 20 picks closes more than 0.12 of the floor *beyond
its footprint*; 4 close more than 0.08, and 4 have a survivor that halves
them. The 0.55 x 0.40 box's footprint is 0.11 of the floor and its top (0.40
across) cannot hold the 0.43 m window, so a lone flat box of the sample's
commonest class costs its footprint with nothing back, and the probe's
cliffs of 0.12-0.21 are that 0.11 plus 0.02-0.10 of pieces. At the
threshold the finding named (0.12 beyond the footprint) the veto fired on 1
of 51 band checks in the twelve episodes (c-sample-s0005, a terrace that
closed 0.21); at 0.08 on 4 (two C, two B).

**Where the other cliffs are.** 33 of the 63 fall outside the band: 30 above
0.6 (the shelf rung 11, wedge-step 6, max-footprint 5, stack-rl 3, terrace 3,
soft-edge 1, pocket-soft 1: the first cliffs of an episode, when the floor is
still open) and 3 under 0.25 (count-mode 2, terrace 1). Of the 30 in the
band, 10 came from stages the veto does not read: the stack option (4), the
physics resort (3), the front wedge (1), a plateau merge with one survivor
(1), a terrace with one survivor (1). The band's cliffs the ladder makes are
terrace-extension 9, max-footprint 5, wedge-step 2, priority-edge 1,
sp-cluster 1.

**When it fires, the gate and the compaction decide.** The four fires at
0.08 were traced (`scratchpad/cliff_fire_probe.py`: the stamp of the pick,
of the survivor taken, of the placement the ladder built, of the settled box,
and the ratio the next call read):

| scene, step | rung | before | pick after | taken after | built | settled | read next call | what happened |
|---|---|---:|---:|---:|---:|---:|---:|---|
| c-sample-s0005, 13 | terrace | 0.278 | 0.138 | 0.399 | 0.399 | 0.399 | 0.399 | the stamp exact; the ship's episode reached the same ratio at the same step |
| c-sample-s0005, 15 | terrace | 0.406 | 0.142 | 0.280 | 0.406 | - | 0.406 | the taken pose fell to the shadow's shade veto; the gate's replacement (from the survivors' list, not the rung's order) placed on the shelf side and closed nothing, as in the ship's episode |
| b-sample-s0000, 16 | max-footprint | 0.429 | 0.216 | 0.337 | 0.216 | - | 0.216 | `build_placement` slid the taken floor pose 3 cm to the wall (x 0.354 -> 0.384); the 2 cm stamp of the slid box is the vetoed pick's figure |
| b-sample-s0005, 14 | max-footprint | 0.389 | 0.144 | 0.369 | 0.365 | 0.365 | 0.365 | the stamp exact: a cliff of 0.22 avoided; the only one of the twelve trajectories that differs from the ship's, and that local episode ended at 23 against the ship's 26 |

So the veto reads the candidate before compaction and before the shadow
gate, and both can undo it: the compaction moves a floor pose by centimetres
and the usable-surface reading at 2 cm cells can flip a window on that; the
gate's replacement loop runs over `decision.survivors` in the ladder's order
and keeps the archetype, so a vetoed `cliff/` pose is replaced by whatever
survivor passes, the original pick among them. Were the lever pursued, the
veto would have to stamp the built (compacted) pose and the gate's
alternatives would have to go through the same reading.

**Time.** The band reading is 3-5 ms a call (two containers on B), the veto
1-3 ms a reading; 0.01-0.06 s an episode in all, the budget never reached.

## 3. The bench

Runs `bench-run.yml` on this branch (physics, budget 4.5 s; sample suites 3
shards, core suites 6), priced with `python -m bench.platform_score
<base> <run>` against the shipped-form records. `cliff` is the 0.12 form,
`cliff08` the 0.08 form.

**Task C** (bases `ship-sample-c` 61.84, 12 of 12 counted, policy max 4.1 s;
`ship-core` 62.31, 48 of 48, 6.1 s):

| run | n | score | delta [95 % CI] | counted | up / down | fill | cog | stability | placement | soft | placed | policy max |
|---|---:|---:|---|---:|---|---:|---:|---:|---:|---:|---:|---:|
| cliff-sample-c | 12 | 60.64 | -1.19 [-3.58, +0.00] | 12 (+0) | 0 / 1 | +0.2 | +0.0 | +0.3 | -8.3 | -0.8 | +0.17 | 3.8s |
| cliff08-sample-c | 12 | 60.64 | -1.19 [-3.58, +0.00] | 12 (+0) | 0 / 1 | +0.2 | +0.0 | +0.3 | -8.3 | -0.8 | +0.17 | 4.4s |
| cliff-core | 48 | 62.04 | -0.27 [-0.99, +0.50] | 48 (+0) | 11 / 15 | +0.1 | +0.1 | -0.3 | -1.1 | -0.7 | +0.02 | 6.3s |
| cliff08-core | 48 | 61.91 | -0.40 [-1.17, +0.39] | 48 (+0) | 10 / 15 | -0.1 | +0.4 | -0.2 | -1.8 | -1.1 | -0.21 | 6.2s |

**Task B** (bases `ship-sample-b` 55.44, 11 of 12 counted, 5.8 s;
`ship-core-b` 61.58, 47 of 48, 7.4 s):

| run | n | score | delta [95 % CI] | counted | up / down | fill | cog | stability | placement | soft | placed | policy max |
|---|---:|---:|---|---:|---|---:|---:|---:|---:|---:|---:|---:|
| cliff-sample-b | 12 | 55.42 | -0.02 [-0.06, +0.00] | 11 (+0) | 0 / 1 | +0.2 | -0.2 | +0.3 | +0.0 | -0.8 | +0.08 | 5.8s |
| cliff08-sample-b | 12 | 55.61 | +0.18 [-2.56, +3.09] | 11 (+0) | 2 / 3 | +0.2 | -0.2 | +0.0 | +4.2 | -3.0 | -0.08 | 5.9s |
| cliff-core-b | 48 | 62.65 | +1.08 [-0.38, +3.77] | 48 (+1) | 10 / 11 | +0.1 | +1.5 | +1.1 | +2.7 | +0.6 | +0.29 | 7.4s |
| cliff08-core-b | 48 | 61.24 | -0.34 [-3.51, +2.76] | 47 (+0) | 12 / 15 | -0.1 | +0.5 | -0.6 | +0.4 | -2.5 | +0.02 | 7.2s |

**How often it fired** (the records' `cliff` counters summed over the suite;
`calls` is the policy calls, `band` the calls with a container in the band,
`checks` the ladder picks read, `cliffs` the picks over the threshold):

| run | calls | band | checks | cliffs | fired (episodes) | by rung | band reads s | veto s |
|---|---:|---:|---:|---:|---:|---|---:|---:|
| cliff-sample-c | 308 | 88 | 57 | 4 | 2 (2) | terrace 2 | 0.80 | 0.27 |
| cliff08-sample-c | 308 | 88 | 57 | 9 | 3 (2) | terrace 3 | 0.74 | 0.28 |
| cliff-sample-b | 330 | 70 | 49 | 1 | 1 (1) | max-footprint 1 | 0.91 | 0.23 |
| cliff08-sample-b | 328 | 78 | 53 | 10 | 7 (5) | max-footprint 6, front-wedge 1 | 0.74 | 0.21 |
| cliff-core | 1900 | 558 | 268 | 46 | 11 (10) | max-footprint 6, wedge-step 2, terrace 2, soft-edge 1 | 6.86 | 1.13 |
| cliff08-core | 1889 | 552 | 268 | 77 | 14 (13) | max-footprint 9, wedge-step 2, terrace 2, soft-edge 1 | 7.85 | 1.46 |
| cliff-core-b | 1933 | 584 | 265 | 44 | 7 (7) | terrace 3, wedge-step 2, max-footprint 1, soft-edge 1 | 7.28 | 1.32 |
| cliff08-core-b | 1920 | 562 | 262 | 69 | 18 (15) | wedge-step 7, terrace 5, max-footprint 4, front-wedge 1, soft-edge 1 | 6.61 | 1.30 |

The band holds 29-30 % of the calls; the ladder's pick is read in about half
of those (the rest place from the stack option, the rescues or a rung with
one survivor); at 0.12 one pick in six read is a cliff and one in 24 is
replaced (0.6-1.5 % of the calls), at 0.08 one in 3.5 is a cliff and one in
15-19 replaced (0.7-2.1 %). The budget never ran out.

**What the fired episodes priced.** The paired delta split by whether the
veto fired in the episode (the unfired episodes move too: the physics
sample is not deterministic, and the shipped arm's own replicate
`softl-base-core` / `softl-base-core-b` prices -0.19 [-0.89, +0.39] with
11 of 48 scenes moved and -0.09 [-0.81, +0.68] with 19 moved):

| run | fired episodes | not fired | all |
|---|---|---|---|
| cliff-sample-c | n 1: -14.34 (c-sample-s0006: 26 -> 28 placed, the one priority box and a soft box covered by the count pass's placements) | n 11: 0.00 | -1.19 |
| cliff08-sample-c | n 2: -7.17 (the same episode, and c-sample-s0005 unchanged) | n 10: 0.00 | -1.19 |
| cliff-sample-b | n 1: -0.26 | n 11: 0.00 | -0.02 |
| cliff08-sample-b | n 5: +0.42 (-10.41, +12.26, -0.26, +0.52, 0.00) | n 7: 0.00 | +0.18 |
| cliff-core | n 10: -0.27 [-1.56, +1.01] | n 38: -0.27 [-1.21, +0.64] | -0.27 [-0.99, +0.50] |
| cliff08-core | n 13: -0.60 [-1.56, +0.43] | n 35: -0.32 [-1.31, +0.65] | -0.40 [-1.17, +0.39] |
| cliff-core-b | n 7: +0.36 [-0.97, +1.55] | n 41: +1.20 [-0.50, +4.10] | +1.08 [-0.38, +3.77]; without b-c2-s0002 -0.03 [-0.52, +0.50] |
| cliff08-core-b | n 15: -4.63 [-12.32, -0.16], one episode under the count (b-c2p-s0003, 43 -> 41 placed, -51.87) | n 33: +1.62 [-0.27, +4.92] | -0.34 [-3.51, +2.76]; without b-c2-s0002 -1.39 [-3.93, +0.17] |

`cliff-core-b`'s +1.08 is b-c2-s0002 crossing the count (41 -> 47 placed,
+52.96) in an episode where the veto never fired: the same threshold-edge
episode the phase switch at 0.3 moved (`ps03-core-b`, +1.16 and +0.05
without it), and the replicate leaves it under. Without it the 0.12 form on
core-b is -0.03 [-0.52, +0.50], the replicate's figure. The 0.08 form on
core-b is the one reading outside the noise, and it is negative: the fifteen
episodes it touched lost 4.63 a scene, one of them its crossing.

**Time.** The policy maxima are the shipped records' (C 6.3 / 6.2 against
6.1 s, B 7.4 / 7.2 against 7.4 s; the sample suites 3.8-5.9 against 4.1 /
5.8). The mean of the episode maxima is lower in every cliff run than in
the shipped record (core 2.9-3.1 against 4.1 s, core-b 4.8-4.9 against 5.7
s), as it is in `ps03-*` (3.0, 4.9) and in the replicate on C (3.7): the
runners vary and the comparison of means across runs is not a reading of
the lever. The veto's own cost is in the table: 8-9 s a 48-episode suite,
about 4 ms a call.

## 4. The trajectories

The usable-surface ratio before each placement (`probe_surface.py`, the
`min` over containers), the placed count, the raw cliffs (drops over 0.12)
and the steps the veto fired on, for the shipped form and the two cliff
forms. On C all twelve trajectories are the ship's; on B one differs.

### Task C, sample seeds 0-5

**c-sample-s0000**

- ship: placed 25, cliffs 5, fired -  
  `1.00 1.00 1.00 1.00 0.95 0.93 0.93 0.89 0.76 0.76 0.76 0.76 0.71 0.50 0.59 0.50 0.60 0.46 0.26 0.26 0.26 0.26 0.26 0.27 0.14 0.14`
- cliff: placed 25, cliffs 5, fired - (identical to ship)  
  `1.00 1.00 1.00 1.00 0.95 0.93 0.93 0.89 0.76 0.76 0.76 0.76 0.71 0.50 0.59 0.50 0.60 0.46 0.26 0.26 0.26 0.26 0.26 0.27 0.14 0.14`
- cliff08: placed 25, cliffs 5, fired - (identical to ship)  
  `1.00 1.00 1.00 1.00 0.95 0.93 0.93 0.89 0.76 0.76 0.76 0.76 0.71 0.50 0.59 0.50 0.60 0.46 0.26 0.26 0.26 0.26 0.26 0.27 0.14 0.14`

**c-sample-s0001**

- ship: placed 22, cliffs 4, fired -  
  `1.00 1.00 1.00 0.92 1.00 0.98 0.81 0.89 0.87 0.74 0.74 0.54 0.45 0.28 0.49 0.49 0.49 0.49 0.41 0.41 0.41 0.41 0.42`
- cliff: placed 22, cliffs 4, fired - (identical to ship)  
  `1.00 1.00 1.00 0.92 1.00 0.98 0.81 0.89 0.87 0.74 0.74 0.54 0.45 0.28 0.49 0.49 0.49 0.49 0.41 0.41 0.41 0.41 0.42`
- cliff08: placed 22, cliffs 4, fired - (identical to ship)  
  `1.00 1.00 1.00 0.92 1.00 0.98 0.81 0.89 0.87 0.74 0.74 0.54 0.45 0.28 0.49 0.49 0.49 0.49 0.41 0.41 0.41 0.41 0.42`

**c-sample-s0002**

- ship: placed 26, cliffs 5, fired -  
  `1.00 1.00 0.90 0.98 0.98 0.91 0.71 0.65 0.65 0.65 0.53 0.53 0.48 0.48 0.48 0.48 0.48 0.28 0.28 0.47 0.28 0.14 0.14 0.14 0.14 0.14 0.14`
- cliff: placed 26, cliffs 5, fired - (identical to ship)  
  `1.00 1.00 0.90 0.98 0.98 0.91 0.71 0.65 0.65 0.65 0.53 0.53 0.48 0.48 0.48 0.48 0.48 0.28 0.28 0.47 0.28 0.14 0.14 0.14 0.14 0.14 0.14`
- cliff08: placed 26, cliffs 5, fired - (identical to ship)  
  `1.00 1.00 0.90 0.98 0.98 0.91 0.71 0.65 0.65 0.65 0.53 0.53 0.48 0.48 0.48 0.48 0.48 0.28 0.28 0.47 0.28 0.14 0.14 0.14 0.14 0.14 0.14`

**c-sample-s0003**

- ship: placed 25, cliffs 5, fired -  
  `1.00 1.00 1.00 1.00 1.00 0.95 0.81 0.81 0.80 0.80 0.80 0.80 0.67 0.66 0.63 0.58 0.49 0.35 0.14 0.28 0.14 0.14 0.14 0.14 0.14 0.14`
- cliff: placed 25, cliffs 5, fired - (identical to ship)  
  `1.00 1.00 1.00 1.00 1.00 0.95 0.81 0.81 0.80 0.80 0.80 0.80 0.67 0.66 0.63 0.58 0.49 0.35 0.14 0.28 0.14 0.14 0.14 0.14 0.14 0.14`
- cliff08: placed 25, cliffs 5, fired - (identical to ship)  
  `1.00 1.00 1.00 1.00 1.00 0.95 0.81 0.81 0.80 0.80 0.80 0.80 0.67 0.66 0.63 0.58 0.49 0.35 0.14 0.28 0.14 0.14 0.14 0.14 0.14 0.14`

**c-sample-s0004**

- ship: placed 24, cliffs 7, fired -  
  `1.00 1.00 1.00 1.00 0.97 0.97 0.76 0.76 0.62 0.49 0.28 0.28 0.14 0.14 0.27 0.27 0.14 0.14 0.00 0.00 0.00 0.00 0.00 0.00 0.00`
- cliff: placed 24, cliffs 7, fired - (identical to ship)  
  `1.00 1.00 1.00 1.00 0.97 0.97 0.76 0.76 0.62 0.49 0.28 0.28 0.14 0.14 0.27 0.27 0.14 0.14 0.00 0.00 0.00 0.00 0.00 0.00 0.00`
- cliff08: placed 24, cliffs 7, fired - (identical to ship)  
  `1.00 1.00 1.00 1.00 0.97 0.97 0.76 0.76 0.62 0.49 0.28 0.28 0.14 0.14 0.27 0.27 0.14 0.14 0.00 0.00 0.00 0.00 0.00 0.00 0.00`

**c-sample-s0005**

- ship: placed 23, cliffs 6, fired -  
  `1.00 1.00 0.90 0.98 0.97 0.97 0.96 0.76 0.58 0.44 0.44 0.44 0.28 0.28 0.40 0.41 0.41 0.28 0.14 0.14 0.14 0.14 0.14 0.14`
- cliff: placed 23, cliffs 6, fired ['15:terrace-extension'] (identical to ship)  
  `1.00 1.00 0.90 0.98 0.97 0.97 0.96 0.76 0.58 0.44 0.44 0.44 0.28 0.28 0.40 0.41 0.41 0.28 0.14 0.14 0.14 0.14 0.14 0.14`
- cliff08: placed 23, cliffs 6, fired ['13:terrace-extension', '15:terrace-extension'] (identical to ship)  
  `1.00 1.00 0.90 0.98 0.97 0.97 0.96 0.76 0.58 0.44 0.44 0.44 0.28 0.28 0.40 0.41 0.41 0.28 0.14 0.14 0.14 0.14 0.14 0.14`

### Task B, sample seeds 0-5

**b-sample-s0000**

- ship: placed 26, cliffs 5, fired -  
  `1.00 1.00 1.00 1.00 1.00 1.00 0.90 0.90 0.72 0.72 0.71 0.79 0.74 0.74 0.60 0.59 0.43 0.22 0.22 0.22 0.22 0.22 0.22 0.34 0.22 0.18 0.18`
- cliff: placed 26, cliffs 5, fired - (identical to ship)  
  `1.00 1.00 1.00 1.00 1.00 1.00 0.90 0.90 0.72 0.72 0.71 0.79 0.74 0.74 0.60 0.59 0.43 0.22 0.22 0.22 0.22 0.22 0.22 0.34 0.22 0.18 0.18`
- cliff08: placed 26, cliffs 5, fired ['16:max-footprint'] (identical to ship)  
  `1.00 1.00 1.00 1.00 1.00 1.00 0.90 0.90 0.72 0.72 0.71 0.79 0.74 0.74 0.60 0.59 0.43 0.22 0.22 0.22 0.22 0.22 0.22 0.34 0.22 0.18 0.18`

**b-sample-s0001**

- ship: placed 26, cliffs 5, fired -  
  `1.00 1.00 1.00 1.00 1.00 1.00 0.96 0.79 0.79 0.79 0.79 0.79 0.67 0.67 0.61 0.48 0.34 0.34 0.31 0.14 0.14 0.14 0.14 0.15 0.15 0.15 0.15`
- cliff: placed 26, cliffs 5, fired - (identical to ship)  
  `1.00 1.00 1.00 1.00 1.00 1.00 0.96 0.79 0.79 0.79 0.79 0.79 0.67 0.67 0.61 0.48 0.34 0.34 0.31 0.14 0.14 0.14 0.14 0.15 0.15 0.15 0.15`
- cliff08: placed 26, cliffs 5, fired - (identical to ship)  
  `1.00 1.00 1.00 1.00 1.00 1.00 0.96 0.79 0.79 0.79 0.79 0.79 0.67 0.67 0.61 0.48 0.34 0.34 0.31 0.14 0.14 0.14 0.14 0.15 0.15 0.15 0.15`

**b-sample-s0002**

- ship: placed 23, cliffs 5, fired -  
  `1.00 1.00 1.00 1.00 1.00 1.00 0.96 0.79 0.79 0.79 0.79 0.67 0.68 0.49 0.33 0.14 0.14 0.14 0.14 0.14 0.14 0.14 0.14 0.14`
- cliff: placed 23, cliffs 5, fired - (identical to ship)  
  `1.00 1.00 1.00 1.00 1.00 1.00 0.96 0.79 0.79 0.79 0.79 0.67 0.68 0.49 0.33 0.14 0.14 0.14 0.14 0.14 0.14 0.14 0.14 0.14`
- cliff08: placed 23, cliffs 5, fired - (identical to ship)  
  `1.00 1.00 1.00 1.00 1.00 1.00 0.96 0.79 0.79 0.79 0.79 0.67 0.68 0.49 0.33 0.14 0.14 0.14 0.14 0.14 0.14 0.14 0.14 0.14`

**b-sample-s0003**

- ship: placed 28, cliffs 6, fired -  
  `1.00 1.00 1.00 1.00 1.00 1.00 0.88 0.71 0.71 0.71 0.71 0.71 0.71 0.69 0.55 0.49 0.36 0.36 0.36 0.30 0.16 0.16 0.16 0.16 0.16 0.00 0.00 0.00 0.00`
- cliff: placed 28, cliffs 6, fired - (identical to ship)  
  `1.00 1.00 1.00 1.00 1.00 1.00 0.88 0.71 0.71 0.71 0.71 0.71 0.71 0.69 0.55 0.49 0.36 0.36 0.36 0.30 0.16 0.16 0.16 0.16 0.16 0.00 0.00 0.00 0.00`
- cliff08: placed 28, cliffs 6, fired - (identical to ship)  
  `1.00 1.00 1.00 1.00 1.00 1.00 0.88 0.71 0.71 0.71 0.71 0.71 0.71 0.69 0.55 0.49 0.36 0.36 0.36 0.30 0.16 0.16 0.16 0.16 0.16 0.00 0.00 0.00 0.00`

**b-sample-s0004**

- ship: placed 25, cliffs 5, fired -  
  `1.00 1.00 1.00 1.00 1.00 1.00 0.97 0.97 0.73 0.73 0.61 0.43 0.43 0.43 0.28 0.14 0.14 0.14 0.14 0.14 0.14 0.14 0.14 0.14 0.14 0.14`
- cliff: placed 25, cliffs 5, fired - (identical to ship)  
  `1.00 1.00 1.00 1.00 1.00 1.00 0.97 0.97 0.73 0.73 0.61 0.43 0.43 0.43 0.28 0.14 0.14 0.14 0.14 0.14 0.14 0.14 0.14 0.14 0.14 0.14`
- cliff08: placed 25, cliffs 5, fired - (identical to ship)  
  `1.00 1.00 1.00 1.00 1.00 1.00 0.97 0.97 0.73 0.73 0.61 0.43 0.43 0.43 0.28 0.14 0.14 0.14 0.14 0.14 0.14 0.14 0.14 0.14 0.14 0.14`

**b-sample-s0005**

- ship: placed 26, cliffs 5, fired -  
  `1.00 1.00 1.00 1.00 1.00 1.00 0.90 0.72 0.72 0.72 0.72 0.71 0.57 0.52 0.39 0.36 0.21 0.15 0.20 0.00 0.00 0.00 0.00 0.00 0.00 0.00 0.00`
- cliff: placed 26, cliffs 5, fired - (identical to ship)  
  `1.00 1.00 1.00 1.00 1.00 1.00 0.90 0.72 0.72 0.72 0.72 0.71 0.57 0.52 0.39 0.36 0.21 0.15 0.20 0.00 0.00 0.00 0.00 0.00 0.00 0.00 0.00`
- cliff08: placed 23, cliffs 5, fired ['14:max-footprint']  
  `1.00 1.00 1.00 1.00 1.00 1.00 0.90 0.72 0.72 0.72 0.72 0.71 0.57 0.52 0.39 0.36 0.39 0.22 0.22 0.15 0.22 0.00 0.00 0.00`

## 5. Verdict

**Not shipped, on C or on B.** The platform's score says: C sample -1.19
[-3.58, +0.00] (one fire, the episode's only priority box covered), C core
-0.27 and -0.40 within the replicate's -0.19 [-0.89, +0.39]; B at 0.12
neutral (-0.02 on the sample, -0.03 on core-b without the count-edge episode
that crosses on its own), B at 0.08 negative where it acts (the fifteen
fired core-b episodes -4.63 [-12.32, -0.16], one crossing lost). The
trajectories are the shipped form's: of the twelve sample episodes probed,
all twelve are identical step for step under the 0.12 form and eleven
under the 0.08 form, and the cliffs are not fewer (C 32, B 31 raw cliffs
in six episodes under every form).

Why the lever cannot pay as specified: the probe's cliffs are the box's own
footprint. A lone 0.55 x 0.40 box (the sample's commonest class) costs its
0.11 of the floor with no window back, because its top is too narrow for
the window; what it closes *beyond* that is 0.02-0.10, under the threshold
at 0.12 for every one of 51 picks read in the twelve sample episodes and
under 0.08 for all but four. A threshold low enough to see the cliffs
(0.08 sees a quarter of the picks) replaces picks whose alternative the
stamp cannot tell apart from them after compaction and the shadow gate,
and on B the replaced episodes lose. The surface that is lost is not in
the pieces beside a box, it is in the top the box fails to offer -- which
is the pair reservation's question (the parent's other lever: the second
0.55 x 0.40 box beside the first makes a 0.80 x 0.55 top), not a veto's.

Kept, off, with its tests and counters: the band reading and the
`closed_share` stamp are the instrument wired into the ladder at the right
place (a rung's survivors, before the selector), and the two traced defects
of any stamp-based veto (read the built pose, not the candidate; make the
gate's alternatives go through the same reading) are what a next attempt
would fix first.
