# Bridge anchors that slide

Built against `reports/wedge/bridge-spots.md`: the plateau-merge (bridge)
rung offered one anchor per pair of tops and placed 1 of 1851 items on core C,
while a scan of the v50 declining boards found reachable two-point-support
spots the full-support check misses. This adds a generator that slides the
bridge along the gap, behind config flags, and measures it on the analytic
bench and on the physics bench (CI).

Scripts, arm specs and the analytic outputs are in
`reports/wedge/bridge-generator/`; the physics records in
`reports/bench/bslide-*` and `reports/bench/bslate-*`.

## Summary

1. **What was built** (all off by default; the shipped config is unchanged
   and the tests pass unchanged):
   - `bridge_slide` (m, 0 = off): for every pair of structure tops at one
     level -- hard tops *and shelf tops*, grouped at the contact tolerance --
     the box is proposed every `bridge_slide` along the slot, flush with each
     member's edges, and at the middle and both ends of the crossing range;
     any two members pair, not only neighbours, so a box over a run of tops
     reaching two of them is offered too; poses resting on the members over
     95 % of their footprint are not bridges and are dropped. The validator's
     overlap rule runs vectorised over all of them, `bridge-would-seal-floor`
     and the plateau condition are asked *before* the family quota (as the
     hole fill asks its depth rule), and the rest are validated round-robin
     over the levels. The old anchors are still offered first.
   - `bridge_slide_max` (24): legal sliding candidates per pose per call; at
     most four times as many validations.
   - `bridge_slide_orientations` (6): the slide also runs over the poses past
     the Layer 2 set of three (the one core C spot stands the box on its side).
   - `bridge_plateau_exempt`: a bridge resting on two separated supports
     (items or a shelf) is exempt from `no-plateau-to-build-on`; the layer cap
     still holds.
   - `bridge_slide_late`: the sliding bridges carry only a new `bridge-slide`
     tag whose rung sits just before the last resort, and a container whose
     only answer is a sliding bridge yields to the next container in routing
     order.
   - With the slide on, floor under a shelf is not charged to a bridge by
     `bridge_keeps_floor` (a bridge on the shelf's edge covers it no more than
     the shelf does).
   - `plateau_merge_min_gain` and `layer2_max_level_step` are read by
     nothing: they veto no bridge. The vetoes that do are
     `bridge-would-seal-floor`, `no-plateau-to-build-on` and, once the slide
     produces candidates, `would-wall-off-the-back` and
     `free-standing-tipping-risk`.
2. **The scan's bridge spots are mostly not bridges.** Re-running the scan and
   asking the stability model what each validator-accepted pose rests on: on
   core C, core B and 6 of the 9 hard2 C boards every accepted pose rests on
   **one** top -- an overhang off a single column with the centre of mass
   inside that one contact (the scan's 1 cm "tight" cells counted lower
   neighbours as support). Two-contact accepted poses exist on 5 of 48 boards
   with an accepted pose, and on 4 of those 5 they put a hard box on soft or
   priority cargo or across both shelves over cargo (the cover rule forbids
   it); the one left (c-hard2-s0082, two hard tops at 1.00 m) passes over
   0.08-0.12 m^2 of bare floor (the floor veto is 0.06). The generator now
   offers a legal bridge on the declining board of c-c1-s0003 (a column and
   the small shelf's edge at 0.85 m, the box on its side) and c-hard2-s0009;
   the old one on none.
3. **Analytic (ladder-only arm, 48 core C scenes).** As members of the
   plateau-merge rung -- the first growth rung -- the sliding bridges cost
   items: 1405 -> 1390 placed with the slide, 1384 with the exemption too,
   crossings 17 -> 15. As the last rung (`bridge_slide_late`), 1405 -> 1409,
   crossings 17 -> 17, the rung chosen 4 times; with the exemption as well
   1401 and 16. Call time is unchanged (mean 0.35 s, max 1.8-1.9 s).
4. **Physics (CI).** Four forms on core C and core B (v50 arms plus the flags, physics, budget 4.5 s, concurrent v50 base on core C), the head-rung form on hard2 as well:

| form (flags) | core C crossings | C placed vs recorded / vs concurrent base | C bridge placements (episodes) | C soft covered | C policy max | core B crossings | B placed | B bridge placements | B soft covered | B policy max |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| v50 recorded (`gate0-*`) | 48 | 38.56 | 1 (1) | 20 | 6.12 s | 48 | 39.56 | 2 (2) | 6 | 7.03 s |
| v50 concurrent (`bslide-base-core`) | 48 | -0.42 / - | 1 (1) | 22 | 6.16 s | - | - | - | - | - |
| slide on the plateau-merge rung + exempt (`bslide-*`) | 48 | -0.06 / +0.35 | 22 (18) | 22 | 6.17 s | **47** (b-c2p-s0002 -9) | -0.79 | 59 (28) | 14 | 7.38 s |
| slide as the last rung (`bslate-*`) | 48 | +0.04 / +0.46 | 9 (8) | 28 | 6.15 s | 48 | +0.08 | 4 (4) | 3 | 7.32 s |
| slide as the call's last stage + exempt (`bsresc-*`) | 48 | -0.25 / +0.17 | 6 (5) | 28 | 6.20 s | 48 | -0.94 | 18 (18) | 5 | 7.32 s |
| slide as the call's last stage (`bsresc0-*`) | 48 | -0.23 / +0.19 | 3 (3) | 26 | 5.90 s | 48 | +0.19 (10 up, 3 down; b-c2-s0007 +10, b-c2-s0004 -11) | 2 (2) | 7 | 7.40 s |

hard2, head-rung form (`bslide-hard2`, `-hard2-b`, against the recorded v50 runs, which lack the stack deadline as these do): C sample crossings 33 -> 35, stretch 9 -> 7, placed +0.62 / +0.41, bridges 195 in 53 episodes, soft covered 80 -> 48, policy max 14.9 -> 10.5 s; B sample 35 -> 35, stretch 12 -> 12, edge 1 -> 2, placed -0.54 / -1.97 (against the replicate -0.83 / -3.28), bridges 191 in 51 episodes.
5. **Verdict.** Not adopted in any form. The head-rung form loses a core B crossing (b-c2p-s0002 50 -> 41) and is flat on core C; the last-rung form keeps every crossing and reads +0.04 / +0.08 placed (within the suites' noise) while covering 8 more soft boxes on core C (20 -> 28, the wrong direction for the platform's soft term); the last-stage forms are flat to negative. The flags stay off.

## 1. Design

`layer2.bridge_slide_anchors(members, level, dx, dy, step, contact_tolerance,
min_overlap)` takes the members in contact at the level (within the contact
tolerance of it) and, for each pair and each axis on which they have a gap:

- along the spanning axis, the centres at which the box overlaps both members
  by `min_overlap` (the centre-of-mass margin, 3 cm): the gap's middle, the
  box flush with each member's outer edge, and the two extremes, clamped into
  that range;
- along the slot, every `step` over the range in which the box overlaps
  *each* member by `min_overlap` (each member's own extent, so offset tops
  still pair), plus the box flush with either edge of either member and the
  shared interval's middle; the slide is ordered coarse first (every fourth,
  every second, the rest);
- a pose whose contact with the members is 95 % of its footprint or more is
  dropped (no lower ground under it).

The pairs' queues are interleaved round-robin, so a cap taken off the front
covers every pair. `layer2.clear_of_obstacles` applies the validator's
penetration rule (vertical overlap beyond the contact tolerance and both
lateral gaps under `settled_clearance`) to all anchors against every packed
box and shelf in one array operation; three quarters of the old anchors died
on exactly that rule.

`layer1._bridge_slide_candidates` runs this per level (hard tops plus shelf
tops, `level_groups` at the contact tolerance: a box rests only on tops within
it, and at the 6 cm bridge tolerance a pair at 1.00 m under a top at 1.04 m is
a member of the 1.04 m group only), then per surviving anchor: the settled
pose inside the container, the floor it would seal (`bridge_sealed_floor`,
the same count as the veto), `validate`, and `may_build_here`. Up to
`bridge_slide_max` legal candidates are added to the Layer 2 output of the
pose, de-duplicated against the old anchors' candidates; they are role
`bridge`, family `plateau-merge`, and carry `features["bridge_slide"]`.

The family quota: the shortlist keeps `max(4, layer2_family_quota // poses)`
bridge candidates per pose, ranked by depth. Asking the floor and plateau
vetoes before that point is what keeps the four from being four that a later
veto deletes (the mistake the hole fill made and fixed with `_hole_depth_ok`).

Cost: about 220 raw anchors and 17 clear ones per Layer 2 call on core C
(860 thousand raw over 4029 calls); the analytic arm's mean call time moved
354 -> 348-352 ms and the 48-scene wall time 557 -> 544-562 s, inside the
machine's noise.

## 2. What the scan's spots rest on (`taxonomy.py`, `two_contacts.py`)

The scan (`reports/wedge/bridge-spots/bridge_scan.py`, re-run; output
`reports/wedge/bridge-spots/bridge_scan.json`) reproduces its table. For each
validator-accepted pose, `stability.evaluate` gives the contacts the agent
sees, and the generator is asked on the same rebuilt board for every pose of
every visible hard item:

| record | bridge-only boards | a pose the validator accepts | ...with two contacts | ...two contacts, hard item | generator offers a bridge: old | slide | slide + exempt |
|---|---:|---:|---:|---:|---:|---:|---:|
| gate0-core | 7 | 5 | 0 | 0 | 0 | 1 | 1 |
| gate0-core-b | 10 | 1 | 0 | 0 | 0 | 0 | 0 |
| gate0-hard2 | 16 | 9 | 2 | 1 | 0 | 1 | 1 |
| gate0-hard2-b | 21 | 13 | 3 | 3 | 0 | 0 | 0 |

The two-contact accepted poses: b-hard2-s0033 on a hard top and a soft top
(1.240 / 1.234), b-hard2-s0043 on a hard and a priority top (0.699 / 0.700),
b-hard2-s0005 across both shelves over cargo -- all three cover cargo of
another attribute, which `no_cover_other_attribute` removes from the pool --
and c-hard2-s0061 for a soft item. c-hard2-s0082's (two hard tops at
1.000 m) pass over 0.08-0.12 m^2 of bare floor, which the floor veto refuses.
The rest are overhangs: on c-c1-s0003 the scan's pose (bottom 0.85 m, 0.27 x
0.75 standing) rests on one column only, with the centre of mass 9 cm inside
its patch; on c-c2-s0011 the box hangs 0.08 m off one top's edge; c-c2p-s0001's
item is soft (Layer 2 offers soft cargo only the typed cap).

So the lever the scan measured is mostly an **overhang** generator (a box on
one top, set off its edge over lower ground as far as the hull allows), not a
bridge one; the terrace anchors are flush with the top's edges and offer the
overhang only past one edge along one axis.

## 3. Analytic signal (`probe.py`, `run_an.sh`, `cmp_an.py`)

The ladder-only analytic arm (`arm_light_c.txt` with
`soft_structure_floor_share=0.0`, the v50 form without the shadow and rescue
stages), 48 core C scenes, the bridge family counted at every Layer 2 call:

| arm | old anchors | slide anchors | ...clear of overlaps | bridge candidates | into the vetoes | surviving | chosen | placed | crossings | fill | soft placed | mean call | max call |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| v50 | 11545 | - | - | 53 | 48 | 3 | 1 | 1405 | 17 | 30.65 | 417 | 354 ms | 1.84 s |
| + slide | 11105 | 860461 | 70257 | 265 | 249 | 123 | 14 | 1390 | 15 | 30.45 | 410 | 348 ms | 1.90 s |
| + slide + exempt | 10840 | 856398 | 56469 | 801 | 337 | 231 | 23 | 1384 | 15 | 30.39 | 408 | 350 ms | 1.91 s |
| + slide, late | 11553 | 902985 | 70262 | 341 | 304 | 160 | 4 | 1409 | 17 | 30.74 | 419 | 351 ms | 1.78 s |
| + slide + exempt, late | 11222 | 888154 | 70006 | 2012 | 730 | 554 | 12 | 1401 | 16 | 30.70 | 417 | 349 ms | 1.86 s |

("chosen" is plateau-merge placements, or bridge-slide ones for the late
arms; the exempt late arm's 12 are 10 bridge-slide and 2 plateau-merge.)

Veto reasons on the bridge candidates that reached the vetoes (slide + exempt,
late): free-standing-tipping-risk 113, would-wall-off-the-back 89,
bridge-would-seal-floor 11. Without the exemption the plateau condition
refuses 33 more (it is asked before the quota, so most never reach the veto
pass).

The head-rung arms lose because a sliding bridge outranks everything below
the plateau-merge rung as soon as one survives: c-c2p-s0006 lids a slot at
step 14 instead of placing a floor box and ends 43 -> 36; c-c2p-s0012
49 -> 43; c-c1s-s0002 21 -> 19. A first late version that was last only
inside one container lost the same c-c2p-s0006 the same way (a bridge in
container 0 beat a floor box in container 1; `an48_late_v1.json`, 1402 placed);
the cross-container fallback fixed it. In the late arm the rung still fires
where the bench's stack option or a relaxed pass would have placed (the
ladder's own decline is not the episode's): c-c1-s0006 15 -> 17 and
c-c2-s0004 36 -> 40 (a bridge where the stack option placed), c-c2p-s0009
41 -> 39 (a bridge where a terrace came from a later pass). Net +4 items over
48 scenes, no crossing changed.

## 4. Physics (CI)

Four forms on core C and core B (v50 arms plus the flags, physics, budget 4.5 s, concurrent v50 base on core C), the head-rung form on hard2 as well:

| form (flags) | core C crossings | C placed vs recorded / vs concurrent base | C bridge placements (episodes) | C soft covered | C policy max | core B crossings | B placed | B bridge placements | B soft covered | B policy max |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| v50 recorded (`gate0-*`) | 48 | 38.56 | 1 (1) | 20 | 6.12 s | 48 | 39.56 | 2 (2) | 6 | 7.03 s |
| v50 concurrent (`bslide-base-core`) | 48 | -0.42 / - | 1 (1) | 22 | 6.16 s | - | - | - | - | - |
| slide on the plateau-merge rung + exempt (`bslide-*`) | 48 | -0.06 / +0.35 | 22 (18) | 22 | 6.17 s | **47** (b-c2p-s0002 -9) | -0.79 | 59 (28) | 14 | 7.38 s |
| slide as the last rung (`bslate-*`) | 48 | +0.04 / +0.46 | 9 (8) | 28 | 6.15 s | 48 | +0.08 | 4 (4) | 3 | 7.32 s |
| slide as the call's last stage + exempt (`bsresc-*`) | 48 | -0.25 / +0.17 | 6 (5) | 28 | 6.20 s | 48 | -0.94 | 18 (18) | 5 | 7.32 s |
| slide as the call's last stage (`bsresc0-*`) | 48 | -0.23 / +0.19 | 3 (3) | 26 | 5.90 s | 48 | +0.19 (10 up, 3 down; b-c2-s0007 +10, b-c2-s0004 -11) | 2 (2) | 7 | 7.40 s |

hard2, head-rung form (`bslide-hard2`, `-hard2-b`, against the recorded v50 runs, which lack the stack deadline as these do): C sample crossings 33 -> 35, stretch 9 -> 7, placed +0.62 / +0.41, bridges 195 in 53 episodes, soft covered 80 -> 48, policy max 14.9 -> 10.5 s; B sample 35 -> 35, stretch 12 -> 12, edge 1 -> 2, placed -0.54 / -1.97 (against the replicate -0.83 / -3.28), bridges 191 in 51 episodes.

## 5. Verdict

No form clears the priced reading. The head-rung slide (`bridge_slide=0.02, bridge_plateau_exempt`) fires 22 times on core C and 59 on core B and costs a core B crossing (b-c2p-s0002, 50 -> 41, a lid on the floor the later boxes needed) with placed -0.79; on core C it is flat against the recorded run and +0.35 against the concurrent base, which is the machine's drift (-0.42). The last-rung form (`bridge_slide_late`) is the only one that keeps every crossing on both suites and reads positive on both (+0.04 / +0.46 on C, +0.08 on B), but it places a bridge 9 times on C and 4 on B, and on C the covered soft boxes rise 20 -> 28: the bridge lids the soft cargo's tops, and the platform refit prices an uncovered soft box per episode above a hard item. The last-stage forms are flat to negative (C -0.25 / -0.23 against the recorded run, B -0.94 with the exemption and +0.19 without, the latter two single-scene swings). On hard2 the head-rung form gains 2 sample crossings on C and loses 2 stretch ones, halves C's covered soft boxes (80 -> 48, with the bridges resting on soft tops where the old rung could not), and is flat on B; the platform refit says hard2 crossings are not a platform lever.

What the measurement settles beyond the forms: the spots the bridge scan found are mostly overhangs (one contact, the centre of mass inside that one patch), so the lever is an overhang generator, not a bridge one, and its yield on the sample suites is one item on a handful of boards with the same soft-cover cost. The sliding generator, the plateau exemption and the late rung are kept in the code as flags (default off) for the record; nothing ships.
