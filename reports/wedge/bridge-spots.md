# Bridges: a box resting on two tops with a dip between them

The question (raised as "a ragged floor still takes a box when two of its
columns stand at one height: n / n-15 / n"): does the packer use poses that
rest on two separate tops at one level and span the lower ground between
them, and how much is left on the board that only such a pose reaches?

Scripts and outputs are in `reports/wedge/bridge-spots/`: `bridge_scan.py`
(the two-point-support spot scan on the declining boards), `bridge_check.py`
(the agent's own validator on the poses the scan found; `bridge_check.json`),
`bridge_probe.py` / `bridge_probe2.py` (where the production bridge rung's
candidates die), `cf_probe_b.py` (the replay that re-asks a declining call
with larger budgets and records the pose placed; `cf3/`).

## Summary

1. **The pose exists in the packer and is dead in practice.** The ladder has a
   `plateau-merge` rung (Layer 2 "bridge") whose anchors span the gap between
   two hard tops grouped within 6 cm, and the stability criterion is the
   centre of mass inside the convex hull of the contact patches, so a bridge
   needs no contact share at all. In the v50 records it placed 1 of 1851 items
   on core C, 2 of 1900 on core B, 25 of 4516 on hard2 C and 31 of 4578 on
   hard2 B. The anchor generator offers one point per pair of tops (the gap's
   middle, the shared interval's middle) with no slide along the gap: over six
   core C scenes, 1191 anchors, 7 legal (805 overlap a neighbour, 185 settle
   outside the container, 153 hit a shelf, 34 fail the centre of mass).
2. **Bridge spots are real on the declining boards.** A scan of every
   declining board in the v50 records (two-point support at one level within
   1 cm, the centre of mass straddled by 4 cm or more on both axes, headroom,
   the sweep from the door clear) finds a reachable spot for a visible item
   that the level-patch check (full support) misses on 7 of 48 core C
   declines, 10 of 47 core B, 16 of 89 hard2 C (8 of its 49 misses) and 21 of
   91 hard2 B (14 of 43 misses). **The agent's own validator accepts at least
   one of those poses on 5 / 1 / 9 / 13 of them**, and on 4 / 1 / 7 / 10 the
   contact share is 0.5 or more, so even the grid rescue's support filter
   passes them.
3. **The shape is not the n / n-15 / n picture.** Dips of 20 cm or less occur
   once in 275 boards. The bridges that exist span the slot between two
   columns 0.5-1.3 m tall (median dip 0.94 m) with 0.2-0.6 of the footprint
   in contact (median 0.44) and 0.03 m^2 of bare floor under the slot
   (15 % of them over the production veto of 0.06 m^2).
4. **The rescue can find them, given seconds C does not have.** On c-c1-s0003
   (margin 0, next item 0.75 x 0.56 x 0.27) the replay re-asked the declining
   call: 4.5 s declines (grid rescue 1 try), 6.5 s declines (5 tries), 8.0 s
   places by the grid rescue after 7.8 s the exact pose the scan found
   (bottom 0.86 m, standing 0.56 tall, contact share 0.48, dip 0.82 m, among
   10 grid poses), and the shadow world accepts it. 7.8 s is over Task C's
   platform limit (8 s at the platform's 1.5x machine factor), so the pose is
   unreachable by time on C. On c-c2p-s0001 only 30 s found anything (the
   count pass at 17.8 s); c-hard2-s0016 placed at 6.5 s by the count pass.
5. **Price.** The platform's streams are sample-like, every platform episode
   already counts, and the refit prices one more hard box per episode at
   about 0.6 of a soft box's volume in fill: 5 of 48 core C and 1 of 47 core
   B declining boards gaining one item is about 0.1 items an episode, about
   +0.02 to +0.05 total points. On hard2 the near misses (-1 to -3) with a
   bridge-only spot are 2 of 12 on C and 2 of 8 on B. The lever is real and
   cheap to build (slide the bridge anchors along the gap at 2 cm, validate
   each; or give the grid rescue its window before the ladder's 2 s and the
   stack option's 1.2 s in a declining call), but it is one item on about a
   tenth of the sample-like episodes, not a crossing lever.

## 1. The scan (`bridge_scan.py`)

Every board that ends on a decline in `gate0-core`, `gate0-core-b`,
`gate0-hard2` and `gate0-hard2-b`, rebuilt from the settled poses as in the
miss taxonomy. For each visible item (the next item on C, the pool on B),
each of the six orientations and each level z of the board (a packed top):

- **free**: every cell under the footprint (plus 3 cm) has its local ceiling
  at z + h + 3 cm or more, no packed box intrudes into [z, z + h + 3 cm), and
  the chamfer limit is respected;
- **full** (the taxonomy's level patch): every cell rests on a top within
  2 cm of z, gaps of one 2 cm cell closed;
- **bridge**: not full, and the cells resting within 1 cm of z (a rigid box
  touches only the higher of two tops; contact tolerance 6 mm plus drift)
  straddle the window's centre by 2 cells (4 cm) or more on both sides along
  x and along y, a proxy for the agent's own criterion (the centre of mass
  3 cm inside the convex hull of the contacts);
- **reach**: the sweep from the door at the transport height is clear of
  packed boxes (the taxonomy's travel path);
- **floor veto**: the bare floor under the window is 0.06 m^2 or less
  (`bridge_max_sealed_floor`);
- **shallow**: every cell under the window is within 20 cm of z.

| record | declines | full spot | bridge-only spot | ...floor veto passed | ...shallow | misses: full / bridge-only / shallow (of n) | near misses -1..-3: full / bridge-only (of n) |
|---|---:|---:|---:|---:|---:|---|---|
| gate0-core | 48 | 1 | 7 | 6 | 0 | - | - |
| gate0-core-b | 47 | 5 | 10 | 9 | 0 | - | - |
| gate0-hard2 | 89 | 7 | 16 | 14 | 0 | 6 / 8 / 0 (49) | 1 / 2 (12) |
| gate0-hard2-b | 91 | 4 | 21 | 19 | 1 | 4 / 14 / 1 (43) | 0 / 2 (8) |

Dip (z minus the lowest surface under the window) over the bridge-only
boards: deciles 0.50 / 0.94 / 1.34 m. Contact share of the example windows:
median 0.44, minimum 0.04. Bare floor under them: median 0.028 m^2, 15 % over
0.06 m^2.

## 2. The agent's verdict on those poses (`bridge_check.py`)

Up to six bridge windows per level and orientation were put through
`layer1.validate` (the analytic mirror of the official validator with the
convex-hull stability, the v50 C config) and through the grid rescue's own
contact-share reading (the share of the 5 cm skyline window resting at the
bottom within the contact tolerance, compared with 0.5, or 0.25 under the
count threshold).

| record | bridge-only boards | a pose the validator accepts | ...with contact share >= 0.5 | ...>= 0.25 |
|---|---:|---:|---:|---:|
| gate0-core | 7 | 5 | 4 | 4 |
| gate0-core-b | 10 | 1 | 1 | 1 |
| gate0-hard2 | 16 | 9 | 7 | 8 |
| gate0-hard2-b | 21 | 13 | 10 | 11 |

Refusals over all poses: overlaps-packed-item 914, transport-hits-packed-item
640 (the validator's sweep is stricter than the scan's), centre-of-mass-
outside-support 123, overlaps-small_shelf 98, no-support 74. Accepted margins
run 0.03-0.28 m inside the hull.

The boards that gain a pose on core C: c-c1-s0003 (margin 0; 6 poses, 3 with
share >= 0.5), c-c2-s0011 (+11), c-c2p-s0001 (+4; 53 legal of 60), c-c2p-s0002
(+2), c-c2p-s0004 (+12; share 0.24, under the rescue's filter). On core B:
b-c1s-s0011 (+2; 188 legal of 290).

## 3. Why the rung is dead (`bridge_probe.py`, `bridge_probe2.py`)

Six core C scenes under the ladder-only analytic arm (v50 C form without the
shadow and rescue stages), every Layer 2 call wrapped:

| | count |
|---|---:|
| Layer 2 calls | 459 |
| hard tops seen / level groups / groups with a pair | 3666 / 2169 / 1005 |
| bridge anchors offered | 1191 (324 more groups over the ceiling) |
| anchors the validator accepts | 7 (all true bridges, both tops in contact) |
| refused: overlaps a packed item | 805 |
| refused: settled pose outside the container | 185 |
| refused: overlaps a shelf | 153 |
| refused: centre of mass outside the support | 34 |
| terrace candidates generated at the same calls | 465 |
| bridge candidates vetoed later | 7 (no-plateau-to-build-on 6, bridge-would-seal-floor 1) |
| bridge candidates surviving | 0 |

`bridge_anchors` emits one centre per pair of tops and axis: the gap's middle
along the spanning axis and the middle of the two tops' shared interval on
the other. A footprint wider than the shared interval runs into the
neighbours; a footprint longer than the two tops' extent runs past them. The
spots the scan finds are reached by sliding the box along the gap and by
spanning more than two members (a slot between two columns of several boxes
each); neither is generated. The per-orientation candidate cap (220) is not
the cause (terraces fill 465 over 459 calls).

## 4. The replay (`cf_probe_b.py`, mode observe)

| scene | decline (margin) | 4.5 s | 6.5 s | 8.0 s | 30 s |
|---|---|---|---|---|---|
| c-c1-s0003 | step 21 (0) | declines, grid rescue 1 try | declines, 5 tries | **grid-rescue-cover at 7.8 s: bottom 0.86 m, 0.27 x 0.75 x 0.56 standing, contact share 0.48, dip 0.82 m, "support 0.36 among 10"** | the same |
| c-c2p-s0001 | step 47 (+4) | declines | declines | declines | count pass at 17.8 s |
| c-c2p-s0002 | step 49 (+2, replay placed 49 against the record's 44) | declines (count 5 tries) | declines (7) | declines (8) | count pass at 12.8 s |
| c-hard2-s0016 | step 21 (+3) | declines (count 11 tries, grid 2) | count pass at 6.8 s | the same | the same |
| c-hard2-s0027 | step 26 (-3) | declines (no pose in the room scan of this replay's board) | - | - | declines |
| c-hard2-s0069 | step 37 (-2) | the same | - | - | declines |

The pose placed on c-c1-s0003 is the scan's bridge (z 0.85, 0.27 x 0.75
footprint, contact 0.45, dip 0.81). Its rescue reading "support 0.36" passes
the count threshold's 0.25 (the episode is at its threshold) and would fail
the 0.5 the rescue applies over it. The time it needs sits past Task C's
platform limit. hard2 replays do not reproduce the recorded course (s0069
placed 37 against the record's 27), so their room scans speak of other
boards.

## 5. What would make it reachable

- **A bridge generator that slides.** For each pair (or run) of tops within
  the level tolerance, anchors every 2 cm along the gap and across the shared
  interval, validated as Layer 2 candidates are (0.1 ms a pose). It would put
  the scan's poses into the ladder at ladder cost, well before the decline,
  and the `bridge-would-seal-floor` veto keeps the lids off usable floor.
  Measurable on the analytic bench in minutes and on the sample suites in an
  hour; judge by items placed and by soft boxes left uncovered, since the
  sample suites keep their crossings either way.
- **The rescue's window before the ladder's.** In a declining call the ladder
  (about 2 s) and the stack option (about 1.2 s) find nothing (the Task B
  time-budget deep-dive); the grid rescue's validator scan is cheap and its
  shadow checks are what need the seconds. Giving it the first window in the
  low phase targets the same poses without a new generator, on B and C
  alike.
- **The rescue's 0.5 contact filter** is the old support-ratio rule
  (`min_support_ratio`, "not an official rule") living on; the validator's
  convex hull already decides stability. Dropping it to the count threshold's
  0.25 for the non-count path admits the 0.3-0.5 bridges (c-c2p-s0004's
  only legal poses are at 0.24).

Expected size: one item on about a tenth of the sample-like declining boards
(fill, and soft where the item is soft), no platform crossing (k is 19 of
19), one or two hard2 near misses. Worth building only as a cheap addition
to a soft-surface lever, not on its own.
