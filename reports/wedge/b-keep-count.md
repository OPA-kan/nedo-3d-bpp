# Task B's content levers without the lost count

Branch `claude/rl-packing-policy-ftogt3-bkeep`; fields
`pool_defer_soft_only` and `pool_defer_floor_secured` (both off by
default) and the existing `count_mode_stream_volume`; arms `arm_bkeep1_b`
.. `arm_bkeep4_b` (`reports/bench/arms/README.md`); records
`reports/bench/bkeep<n>-{hard2-b,core-b,sample-b}`, priced with
`bench.platform_score` against the v60 form's records `nck-*` and against
the pre-v60 bases `shipr-hard2-b`, `shipr-core-b`, `ship-sample-b`.

## 1. The question

v60 shipped Task B's content levers (`count_cover_priority=false` and
`pool_defer_max=6`, `reports/wedge/b-content.md`).  On the platform they
gained placement +10.95 and soft +10.55 and pushed one counted B episode
under the count threshold (stability 78.04 -> 74.68, 19 -> 18 counted; a
counted episode is worth about 2.7 points).  On the bench the same showed
as hard2-b's crossings 7 up / 7 down (net 0) while core-b and sample-b
lost none.  Which lever loses those crossings, on what kind of scene, and
is there a form of the levers that keeps the placement and soft gains
while losing no crossing?

## 2. The diagnosis from the records

### 2.1 The seven scenes that dropped under the count

`nck-hard2-b` against `shipr-hard2-b`, scene by scene (the threshold is
half the stream plus one; the agent's estimate of it is the count mode's
fixed prior, 41 items a container, so 21 / 42 / 62; `refused` is the
count pass's poses over a priority box dropped by the never-cover rule,
`fired` the deferral's placements; the item counts are base -> new):

| scene | stratum, mix | soft share / priority rate / pool | threshold (agent's) | placed | hard / soft / priority placed | priority covered | refused | fired (soft / priority) | the end |
|---|---|---|---|---|---|---|---:|---|---|
| s0014 | sample, big | 0.45 / 0.3 / 3 | 39 (42) | 40 -> 38 | 0/39/1 -> 0/38/0 | 1 -> 1 | 0 | 7 (7 / 0) | an all-soft stream one over the threshold; the deferral reordered soft among soft, two fewer |
| s0021 | sample, sample | 0.1 / 0.1 / 3 | 51 (42) | 54 -> 50 | 39/12/3 -> 33/14/3 | 0 -> 0 | 268 | 5 (2 / 3) | one short: three priority boxes pulled onto the floor early, the last count-pass poses refused |
| s0027 | sample, sample | 0.1 / 0.3 / 5 | 29 (21) | 33 -> 24 | 21/2/10 -> 14/1/9 | 4 -> 0 | 8 478 | 7 (0 / 7) | the base's last eight were count-pass poses over priority above the agent's threshold; refused, the episode ends at 24 |
| s0040 | sample, small | 0.1 / 0.3 / 5 | 42 (21) | 43 -> 33 | 23/6/14 -> 19/3/11 | 4 -> 0 | 20 563 | 5 (2 / 3) | the base's grid-rescue covers and count-pass poses at 38-42 refused; the agent read the count secured at 21 |
| s0050 | stretch, small | 0.2 / 0.05 / 20 | 36 (21) | 40 -> 30 | 36/4/0 -> 27/0/3 | 0 -> 0 | 1 623 | 3 (0 / 3) | three priority boxes on the floor at steps 6, 19, 20 (the base placed none); the hard cargo 36 -> 27 |
| s0059 | stretch, sample | 0.45 / 0.0 / 5 | 48 (42) | 48 -> 41 | 47/1/0 -> 36/5/0 | - | 0 | 4 (4 / 0) | four `pocket-soft` boxes on the floor at steps 12-15; the hard terraces lost 11 places; no priority, so the never-cover is inert |
| s0087 | edge, sample | 0.2 / 0.05 / 20 | 45 (42) | 48 -> 42 | 47/1/0 -> 32/1/9 | 0 -> 1 | 833 | 8 (1 / 7) | seven priority boxes pulled forward, five of them `priority-edge` on the floor (the base placed none); the hard cargo 47 -> 32 |

Two kinds.  (i) **The never-cover's**: s0027 and s0040, and the ends of
s0021 and s0087.  The rule is already the phase-aware form the question
asks for (`_priority_cover_allowed`: the covers of priority stay allowed
while the packed count is under the agent's own threshold, and stop
above it), so the loss is not in the low phase under the estimate but
in the band *above the agent's estimate and under the real threshold*:
29 against 21, 42 against 21, 51 against 42, 45 against 42.  On
hard2-b the real threshold is above the agent's prior on 65 of 96
scenes (by 1 to 234 items), and on the four scenes the count pass's
covers were what carried the base from the agent's threshold to the
real one.  (ii) **The deferral's**: s0059, s0050, s0014 and the
layouts of s0021 and s0087.  The deferred items took the floor early,
under the threshold: four 80-litre soft boxes on the floor at steps
12-15 of s0059 where the base's 73-litre hard boxes built terraces, five
`priority-edge` floor poses on s0087, three on s0050 -- priority boxes
the base never placed at all (the pool of 20 always had a hard box with
a pose), each a hard box's floor.  No settle accident is among the
seven: every end is a decline, the shadow check was skipped on none
(`skipped` 0), so the shadow-skipped stack poses at the budget's edge
that b-content.md names for the deferral at 9 play no part here.

The seven that rose (s0009, s0026, s0030, s0036, s0039, s0053, s0064)
are the high-soft-share streams (0.32-0.6 on six of seven) where the
deferral's soft boxes are the count: s0009 placed 35 soft against 19,
s0036 94 against 80, s0053 ended on a decline at 54 where the base's
settle failure ended it at 34.  The downs are the low-soft-share
streams (0.1-0.2 on five of seven) with a priority rate of 0.3 or a
pool of 20: there the typed cargo the deferral pulls forward is few and
large, and what it displaces is the hard cargo that was the count.

### 2.2 What the records say about the candidate forms

The deferral's fires on the three nck records, read off the step logs
(a soft or priority item placed by a ladder archetype after six or more
placements in the pool), by the surface the pose took and by the packed
count against the agent's threshold:

| record | fires | under the agent's threshold | of which on the floor | priority fires |
|---|---:|---:|---:|---:|
| nck-core-b (48 of 48 counted) | 613 | 556 (91 %) | 163 (29 % of those under) | 128 (21 %) |
| nck-hard2-b, the 7 scenes down | 36 | 36 | 25 (69 %) | 23 (64 %) |
| nck-hard2-b, the 7 scenes up | 102 | 95 | 47 | 5 |
| nck-hard2-b, the rest | 475 | 331 | 130 | 100 |
| nck-sample-b | 85 | 76 | 24 | 7 |

So (a) the brief's phase-aware never-cover is the shipped `ncl` form
already, and the only handle on the band above the estimate is a better
estimate: a cover margin keyed on the prior would hand back the
placement gain where the prior is right (on `shipr-core-b` the base's
37 priority covers sit at the threshold +0..+14, 31 of them above it,
so a margin of 10 restores about half of them), while the stream's
volume reading (`count_mode_stream_volume=0.54`, measured
crossing-neutral in findings.md and kept "for a lever gated on the
estimate") lengthens the estimate on the small-box streams only
(s0040's 83 items are read as 21 by the prior) and leaves core-b's prior
where it is right.  (b) The deferral suspended under the threshold
would remove 91 % of core-b's fires and with them the soft gain that is
v60's platform credit; it is rejected from the records, not run.  (c)
The shadow-skipped stack poses are not in the seven.  (d) What the
seven share is the floor under the threshold and the priority cargo:
the deferral's priority fires bought +1.2 of placement on core-b (nck
+13.8 against the never-cover alone's +12.6) with the priority boxes
placed level (4.81 -> 4.79 a scene), and they are 23 of the 36 fires on
the scenes down.

## 3. What was built

Two fields in `rule_alpha/config.py`, off by default, tests in
`tests/test_bkeep.py` (11 tests; the full set 330):

- `pool_defer_soft_only`: the deferral for the soft cargo only; a
  priority pool item keeps the pool order however often it is passed
  over (`_defer_order`'s front filter).
- `pool_defer_floor_secured`: while the packed count is under the count
  mode's threshold (`_count_threshold`: the agent's estimate, so the
  prior or the volume reading), a deferred item at the front of the
  order whose ladder pose or wedge-option pose rests on the floor is
  held (`_defer_floor_hold`): the pose is not emitted, the next item is
  tried, and the item's passed-over count restarts, so it is asked
  again after k more calls rather than costing a ladder decision every
  call.  A pose on a shelf or on cargo is emitted as before; the rescue
  stages keep their poses.  Phase stat `defer_floor_held`.

Arms, each `arm_nck_b` plus: `arm_bkeep1_b` the soft-only deferral;
`arm_bkeep2_b` the floor hold; `arm_bkeep3_b` the volume reading
(`count_mode_stream_volume=0.54`); `arm_bkeep4_b` all three.

### 3.1 The four worst dropped scenes, locally in physics (budget 4.5 s)

`--scene B:hard2:<seed>`, the placed count (the threshold in the first
column), with the never-cover alone (`ncl`), the deferral alone (`k6`)
and the variants:

| scene (threshold) | ship | nck | ncl | k6 | bkeep1 soft-only | bkeep2 floor hold | bkeep3 volume reading | bkeep4 all |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| s0027 (29; agent 21) | 33 | 24 | 23 | 36 | 25 | 29 (5 held) | 25 (estimate 49 items, so 25) | 25 |
| s0040 (42; agent 21) | 44 | 32 | 30 | 44 | 30 | 30 (1 held) | 35 (estimate 66, so 33; priority covered 5) | 35 |
| s0059 (48; agent 42) | 48 | 41 | 48 | 41 | 41 | 49 (3 held) | 41 | 49 |
| s0087 (45; agent 42) | 48 | 42 | 48 | 43 | 51 (1 priority fire against 7) | 50 (19 held) | 42 | 51 |

The split holds under the simulator's noise: on s0059 and s0087 the
never-cover alone keeps the count and the deferral alone loses it, and
the soft-only form or the floor hold recovers it (49-51 against 41-43);
on s0027 and s0040 the deferral alone keeps the count and the
never-cover alone loses it, and the volume reading's longer estimate
(49 and 66 items against the real 57 and 83) still stops the covers
short of the real threshold (25 and 33 against 29 and 42).  The floor
hold's 29 on s0027 is the threshold exactly, one pose's luck.

## 4. The suites (CI, physics, budget 4.5 s, 6 shards)

`python -m bench.platform_score`, each arm against the v60 form's record
(what is kept of its gain) and against the pre-v60 base (what is lost of
the count).  The counted column is base / nck / new.

### 4.1 Against the v60 form (`nck-*`)

| suite | arm | score | delta [95 % CI] | counted | fill | cog | stability | placement | soft | placed | policy max |
|---|---|---:|---|---|---:|---:|---:|---:|---:|---:|---:|
| hard2-b (nck 35.39, 47 of 96) | bkeep1 soft-only | 36.39 | +1.00 [-0.48, +2.82] | 47 / 47 / 50 | +0.8 | +1.9 | +3.0 | -3.0 | +1.3 | +1.10 | 7.4 s |
| | bkeep2 floor hold | 35.41 | +0.03 [-3.55, +3.55] | 47 / 47 / 47 | +1.3 | -0.6 | +0.2 | +1.0 | -2.8 | +0.32 | 7.3 s |
| | bkeep3 volume reading | 34.68 | -0.71 [-2.17, +0.09] | 47 / 47 / 46 | +0.3 | -0.9 | -1.0 | -1.5 | -1.1 | +0.19 | 7.3 s |
| | bkeep4 all | 36.50 | +1.11 [-2.51, +4.92] | 47 / 47 / 50 | +1.7 | +1.5 | +3.1 | -0.5 | -2.0 | +1.07 | 7.4 s |
| core-b (nck 66.15, 48 of 48) | bkeep1 | 63.01 | **-3.14 [-4.41, -1.82]** | 48 / 48 / 48 | +2.7 | -1.1 | +0.9 | **-28.3** | +1.4 | +1.65 | 7.2 s |
| | bkeep2 | 64.31 | **-1.84 [-4.58, -0.09]** | 48 / 48 / 47 | +2.7 | -2.6 | -1.2 | -7.8 | -4.9 | -0.31 | 6.7 s |
| | bkeep3 | 66.32 | +0.17 [-0.10, +0.47] | 48 / 48 / 48 | +0.1 | +0.3 | +0.2 | -0.3 | +0.6 | +0.12 | 7.2 s |
| | bkeep4 | 62.12 | **-4.03 [-5.44, -2.70]** | 48 / 48 / 48 | +3.6 | -1.8 | +1.4 | **-29.3** | -5.5 | +0.21 | 7.4 s |
| sample-b (nck 66.47, 12 of 12) | bkeep1 | 61.55 | **-4.92 [-8.68, -1.56]** | 11 / 12 / 12 | +0.2 | +0.5 | +0.3 | **-37.5** | +1.5 | +0.00 | 7.2 s |
| | bkeep2 | 59.62 | -6.86 [-17.32, +0.78] | 11 / 12 / 11 | +1.6 | -3.9 | -9.0 | -20.1 | -12.0 | -0.33 | 5.5 s |
| | bkeep3 | 66.44 | -0.03 [-0.09, +0.00] | 11 / 12 / 12 | +0.2 | -0.4 | +0.0 | +0.0 | +0.0 | +0.17 | 5.6 s |
| | bkeep4 | 60.79 | **-5.68 [-10.07, -1.23]** | 11 / 12 / 12 | +3.6 | +0.0 | -1.9 | **-39.6** | -4.7 | +0.92 | 5.5 s |

### 4.2 Against the pre-v60 base (`shipr-hard2-b`, `shipr-core-b`, `ship-sample-b`)

| suite | arm | score | delta [95 % CI] | counted | fill | cog | stability | placement | soft | placed |
|---|---|---:|---|---|---:|---:|---:|---:|---:|---:|
| hard2-b (base 34.67, 47 of 96) | nck (v60) | 35.39 | +0.71 [-3.56, +4.98] | 47 / 47 | -2.0 | +1.2 | -0.1 | +2.5 | +4.9 | -0.54 |
| | bkeep1 | 36.39 | +1.71 [-2.12, +5.58] | 47 / 50 | -1.3 | +3.0 | +2.9 | -0.5 | +6.2 | +0.56 |
| | bkeep2 | 35.41 | +0.74 [-1.93, +3.60] | 47 / 47 | -0.8 | +0.6 | +0.1 | +3.6 | +2.1 | -0.22 |
| | bkeep3 | 34.68 | +0.00 [-4.02, +4.01] | 47 / 46 | -1.8 | +0.3 | -1.1 | +1.1 | +3.8 | -0.35 |
| | bkeep4 | 36.50 | +1.83 [-1.11, +5.17] | 47 / 50 | -0.3 | +2.7 | +3.0 | +2.0 | +2.9 | +0.53 |
| core-b (base 62.74, 48 of 48) | nck (v60) | 66.15 | **+3.41 [+2.17, +4.78]** | 48 / 48 | -5.8 | +3.5 | -1.5 | +13.8 | +18.8 | -1.38 |
| | bkeep1 | 63.01 | +0.27 [-0.94, +1.63] | 48 / 48 | -3.1 | +2.4 | -0.6 | -14.5 | +20.3 | +0.27 |
| | bkeep2 | 64.31 | +1.57 [-1.32, +3.65] | 48 / 47 | -3.1 | +0.9 | -2.7 | +6.0 | +14.0 | -1.69 |
| | bkeep3 | 66.32 | **+3.58 [+2.38, +4.93]** | 48 / 48 | -5.7 | +3.7 | -1.3 | +13.5 | +19.5 | -1.25 |
| | bkeep4 | 62.12 | -0.62 [-1.69, +0.42] | 48 / 48 | -2.2 | +1.7 | -0.1 | -15.5 | +13.3 | -1.17 |
| sample-b (base 55.44, 11 of 12) | nck (v60) | 66.47 | **+11.03 [+1.78, +22.72]** | 11 / 12 | -7.5 | +9.5 | +8.1 | +23.6 | +42.9 | -1.42 |
| | bkeep1 | 61.55 | +6.12 [-0.77, +15.34] | 11 / 12 | -7.3 | +10.0 | +8.4 | -13.9 | +44.4 | -1.42 |
| | bkeep2 | 59.62 | +4.18 [-7.88, +16.94] | 11 / 11 | -5.9 | +5.6 | -0.9 | +3.5 | +30.9 | -1.75 |
| | bkeep3 | 66.44 | **+11.00 [+1.72, +22.68]** | 11 / 12 | -7.4 | +9.1 | +8.1 | +23.6 | +42.9 | -1.25 |
| | bkeep4 | 60.79 | +5.35 [-1.63, +14.81] | 11 / 12 | -3.9 | +9.5 | +6.2 | -16.0 | +38.2 | -0.50 |

### 4.3 The crossings

Against the pre-v60 base (placed base -> new / threshold), then against
the v60 form:

| arm | hard2-b against the base | core-b | sample-b |
|---|---|---|---|
| nck (v60) | up 7: s0009 52->59/53, s0026 14->17/16, s0030 74->79/79, s0036 80->96/83, s0039 20->22/22, s0053 34->54/47, s0064 27->31/30; down 7: s0014 40->38/39, s0021 54->50/51, s0027 33->24/29, s0040 43->33/42, s0050 40->30/36, s0059 48->41/48, s0087 48->42/45 | none | up s0010 21->27/22 |
| bkeep1 soft-only | up 7: the same seven; down 4: s0014 40->38, s0027 33->25, s0040 43->30, s0059 48->41 | none | up s0010 21->24/22 |
| bkeep2 floor hold | up 3: s0009 52->58, s0026 14->17, s0077 19->22/21; down 3: s0014 40->38, s0040 43->30, s0050 40->30 | **down b-c2-s0003 50->38/42** | up s0010 21->22/22; **down s0004 25->21/22** |
| bkeep3 volume reading | up 6: nck's seven without s0009; down 7: nck's seven (s0040 43->35) | none | up s0010 21->27/22 |
| bkeep4 all | up 5: s0009 52->58, s0026 14->17, s0063 43->56/56, s0064 27->31, s0077 19->22; down 2: s0027 33->25, s0040 43->30 | none | up s0010 21->23/22 |

| arm | hard2-b against nck | core-b | sample-b |
|---|---|---|---|
| bkeep1 | up 3: s0021 50->54/51, s0050 30->40/36, s0087 42->51/45; down 0 | none | none |
| bkeep2 | up 5: s0021 50->53, s0027 24->29/29, s0059 41->49/48, s0077 18->22, s0087 42->50; down 5: s0030 79->75/79, s0036 96->75/83, s0039 22->20/22, s0053 54->46/47, s0064 31->27/30 | down b-c2-s0003 45->38/42 | down s0004 24->21/22 |
| bkeep3 | down 1: s0009 59->49/53 | none | none |
| bkeep4 | up 7: s0014 38->39/39, s0021, s0050, s0059, s0063 47->56/56, s0077, s0087; down 4: s0030 79->78/79, s0036 96->64/83, s0039 22->20/22, s0053 54->43/47 | none | none |

### 4.4 What the variants did to the typed cargo (per episode)

| suite | run | placed | soft placed / covered | priority placed / covered | fires (soft / priority) | held | topples |
|---|---|---:|---|---|---|---:|---:|
| core-b | shipr (base) | 39.23 | 9.94 / 0.21 | 4.81 / 0.81 | - | - | 0.38 |
| | ncl | 37.31 | 8.46 / 0.08 | 4.83 / 0.08 | - | - | 0.50 |
| | k6 | 38.83 | 13.19 / 0.46 | 4.79 / 0.58 | 655 (458 / 197) | - | 0.58 |
| | nck (v60) | 37.85 | 12.88 / 0.38 | 4.79 / 0.06 | 644 (450 / 194) | - | 0.77 |
| | bkeep1 soft-only | 39.50 | 13.27 / 0.44 | **3.06** / 0.02 | 543 (473 / 70) | - | 0.54 |
| | bkeep2 floor hold | 37.54 | 12.06 / 0.29 | 4.46 / 0.12 | 571 (418 / 153) | 431 | 0.54 |
| | bkeep3 volume reading | 37.98 | 12.94 / 0.25 | 4.81 / 0.08 | 650 (454 / 196) | - | 0.73 |
| | bkeep4 all | 38.06 | 11.90 / 0.38 | **3.29** / 0.10 | 485 (426 / 59) | 246 | 0.40 |
| sample-b | ship (base) | 26.42 | 3.33 / 0.17 | 1.42 / 0.25 | - | - | 0.17 |
| | nck (v60) | 25.00 | 7.50 / 0.25 | 1.58 / 0.08 | 88 (72 / 16) | - | 0.17 |
| | bkeep1 | 25.00 | 7.50 / 0.08 | **0.75** / 0.00 | 82 (74 / 8) | - | 0.08 |
| | bkeep2 | 24.67 | 6.67 / 0.08 | 1.17 / 0.00 | 72 (60 / 12) | 48 | 0.83 |
| | bkeep3 | 25.17 | 7.50 / 0.25 | 1.58 / 0.08 | 88 (72 / 16) | - | 0.17 |
| | bkeep4 | 25.92 | 6.92 / 0.17 | **0.75** / 0.00 | 74 (67 / 7) | 41 | 0.67 |
| hard2-b | shipr (base) | 46.29 | 13.71 / 0.14 | 5.18 / 0.74 | - | - | 1.00 |
| | nck (v60) | 45.75 | 15.60 / 0.28 | 5.48 / 0.29 | 974 (704 / 270) | - | 0.97 |
| | bkeep1 | 46.85 | 15.72 / 0.23 | 4.78 / 0.18 | 758 (719 / 39) | - | 0.89 |
| | bkeep2 | 46.07 | 14.91 / 0.26 | 5.44 / 0.12 | 698 (508 / 190) | 927 | 0.76 |
| | bkeep3 | 45.94 | 15.68 / 0.31 | 5.51 / 0.47 | 986 (714 / 272) | - | 0.85 |
| | bkeep4 | 46.82 | 15.23 / 0.28 | 5.05 / 0.19 | 540 (510 / 30) | 612 | 0.82 |

The settle ends: none on core-b under bkeep1, bkeep2 and bkeep4 (nck
2), hard2-b 4 under every variant (nck 2, the base 7).  The policy time
is the v60 form's (means 0.54-0.83 s; the maxima 7.2-7.4 s on hard2-b,
under the 10 s limit).

## 5. What the measurements say

**The soft-only deferral (bkeep1)** recovers three of hard2-b's seven
crossings (s0021, s0050, s0087: the pool-20 and priority-0.3 scenes
where the priority fires took the floor) and loses none against the v60
form there (+1.00 [-0.48, +2.82]), but on core-b it costs the
placement component 28 points: the priority boxes placed fall from 4.79
to 3.06 a scene (sample-b 1.58 -> 0.75).  The records' reading in
b-content.md -- the priority fires buy nothing, the priority boxes
placed are level -- was true of the deferral against the shipped form,
and false of the soft deferral on its own: once the soft fires take the
shelves and the pockets at steps 3-20, the priority boxes that the pool
order would have placed at the end find no surface, and the priority
fires are what kept them level.  The two halves of the deferral are
not separable: the priority fires cost counts on hard2-b's low-soft
streams and earn the placement credit on core-b's.

**The floor hold (bkeep2)** recovers the deferral's five hard2-b losses
against the v60 form (s0021, s0027, s0059, s0077, s0087) and loses five
of its gains (s0030, s0036, s0039, s0053, s0064: the high-soft-share
streams where the deferred soft boxes on the floor *are* the count, and
the hold keeps them off it until the agent's threshold, which on those
scenes is far under the real one), net zero, and it loses one crossing
each on core-b (b-c2-s0003 50 -> 38 of 42: a two-container scene, so
the hold runs to 42 placed, nearly the whole episode) and sample-b
(s0004 25 -> 21 of 22), with placement -7.8 and soft -4.9 on core-b.
The threshold the hold reads is the fixed prior, and the floor under it
is the count on one kind of scene and the hard cargo's on the other.

**The volume reading (bkeep3)** changes nothing on core-b and sample-b
(+0.17 and -0.03 against nck, the same crossings: the core streams'
reading is under the prior) and on hard2-b lengthens the estimate on
the small-box streams without reaching their thresholds (s0040 66 items
read against 83: the covers stop at 33, the count is 42), while the
longer count pass itself lost s0009 (59 -> 49 of 53, a no-priority
stream where the never-cover is inert and the count mode's rules ran
longer).  -0.71 [-2.17, +0.09] on hard2-b, nothing kept, nothing
recovered.

**All three (bkeep4)** is hard2-b's best count (50 of 96, +3 against the
base and nck; the two left under are the never-cover's s0027 and s0040)
at the soft-only form's price on core-b (-4.03 [-5.44, -2.70] against
nck, -0.62 against the pre-v60 base) and sample-b (-5.68).

## 6. Verdict

**No ship candidate.**  No arm meets the ship rule (no crossing lost
against the pre-v60 base on any suite while keeping v60's gain): the
four variants lose 2-7 hard2-b crossings against the base, and the two
that recover the most (bkeep1, bkeep4: 4 and 2 down, 3 up net against
nck) give back the placement gain that is the levers' platform credit
(core-b -3.1 / -4.0 against the v60 form, placement -28 / -29).  The v60
form (`arm_nck_b`) stays: core-b +3.41 [+2.17, +4.78] and sample-b
+11.03 against the base with every crossing kept, hard2-b +0.71 n.s.
with 7 up / 7 down.

Why the losses are not recoverable without the gains:

1. The never-cover's losses (s0027, s0040, and the ends of s0021 and
   s0087) sit in the band between the agent's count estimate and the
   real threshold -- 21 against 29 and 42, 42 against 51 and 45.  The
   covers of priority are already allowed under the agent's estimate
   (the phase-aware form the question asks for is the shipped `ncl`
   rule), the stream's volume reading cannot see a stream of the
   sample's boxes that is simply longer (findings.md, the count
   estimate), and a cover margin on the prior would restore the covers
   above the threshold on core-b, where the prior is right and 31 of
   the base's 37 priority covers sit at +0..+14 over it: that is the
   placement credit v60 earned.  A count the agent cannot observe
   cannot be secured by a rule that reads it.
2. The deferral's losses (s0059, s0050, s0087, s0021's layout) are the
   typed cargo on the floor under the threshold, and so are its gains
   on the high-soft-share streams (s0009, s0036, s0053: 15, 4 and 13
   soft floor fires under the threshold).  The floor hold swaps the one
   set for the other (5 up / 5 down against nck on hard2-b) and costs a
   crossing on core-b and sample-b.  The priority half of the deferral
   loses the counts on the low-soft, priority-0.3 and pool-20 streams
   and keeps the priority boxes placed level on core-b once the soft
   half has taken the surfaces; without it the placement component
   falls 28 points.

What the platform's lost episode most likely is: by the bench, a B
stream whose count threshold is above 41 a container (the agent's
prior) with a priority rate high enough that the count pass's covers
were carrying the base across, or a low-soft stream with a large pool
-- hard2-b's s0027 / s0040 / s0087 kind, not core-b's.  At 2.7 points an
episode it is worth about 1.6 of v60's +1.76 net, and the levers' gain
on the other ten (+4.5 by the official-results reading) is the larger
side.

The one form the records suggest and this round did not measure: the
floor hold on the priority fires only (the soft floor fires kept, since
they are the count on the high-soft streams; the priority floor fires
held under the threshold, since they are 16 of the 25 floor fires on
the seven scenes down and 49 of 613 fires on core-b, 8 %).  It would
recover s0087, s0050 and s0021 at most (s0059's four soft floor boxes
stay) and would be priced on core-b by how many of the 49 held priority
boxes fire later on a shelf or a top rather than not at all.  The
first-order reading from bkeep1 (70 priority fires instead of 194: the
priority boxes placed 3.06 against 4.79) says the held boxes mostly do
not come back, so the expected price is a share of the -28, which the
+3 counts on hard2-b (about +8 of hard2-b's score, at the task shares
+0.3 on the platform if the platform's B streams were hard2's kind,
which they are not) does not pay for.

Records: `reports/bench/bkeep{1,2,3,4}-{hard2-b,core-b,sample-b}`; arms
`arm_bkeep1_b` .. `arm_bkeep4_b`; fields `pool_defer_soft_only`,
`pool_defer_floor_secured` (off); tests `tests/test_bkeep.py`; the
diagnosis scripts (`diag.py`, `thr.py`, `fires.py`, `covers.py`,
`steps.py`, `cross.py`) and the local probe records in the session
scratchpad.
