# Where we stand (2026-09-24, from the data)

Best official build: **v18, 43.05** (`submit-v18.zip`, commit 3bdd115).
Nine official runs, six bench suites of 48 physics scenes per task,
and one analytic sweep are what this reads from.

## 1. What the platform scores, as fitted

| component | weight (7 runs fit to 0.001) | what moves it |
|---|---|---|
| fill | 0.286 | volume; barely moved in nine runs (34.05-36.29) |
| cog | 0.216 | items placed (+2 a point of fraction), height (-3 per 0.01 of centre-of-mass ratio) |
| stability | 0.213 | items placed (+2.3 a point), topples (-0.8 a topple a scene) |
| placement | 0.143 | priority cargo in its container, uncovered; more priority placed is *not* better (v14) |
| soft | 0.142 | soft cargo uncovered; roughly the soft count (v5 20.5 with 358 placed on the suite, v12 18.1 with 349) |

Every component but the fill is zero for an episode under a count
threshold.  Testing thresholds on the Task A suite distributions of
v5, v12 and v18: cog divided by the share of episodes at or over T is
flat only at T = 0.50 (55, 59, 58 for the three builds; 44/50/55 at
0.45, 89/66/64 at 0.55).  So the threshold is at or near **half the
items**, and a build is paid for every episode it lifts over it.

| official run | placed | total | what it changed |
|---|---|---|---|
| v5 | 0.503 | 35.09 | row planner |
| v12 | 0.540 | 38.21 | small cargo first |
| v14 | 0.543 | 37.38 | priority orders: placement and soft fell |
| v18 | 0.553 | **43.05** | the priority container's room |
| v19 | 0.556 | 40.44 | a fourth hard layer: height and topples cost 2.6 |

## 2. The three tasks on the bench (v18 agent, 48 scenes each, same seeds)

| | A (planned) | B (pool) | C (one at a time) |
|---|---|---|---|
| items a scene (of 61.5) | 38.0 | 31.5 | 27.2 |
| fraction placed | 0.616 | 0.526 | **0.445** |
| episodes at or over 0.50 | 94 % | 60 % | 23 % |
| episodes at or over 0.55 | 85 % | 35 % | 4 % |
| soft placed (of 18.2 a scene) | 7.3 (40 %) | 4.2 (23 %) | 8.0 (44 %) |
| hard unplaced a scene | 12.5 (5.6 of them the biggest class) | 15.9 | 24.1 |
| fill | 37 % | 35 % | 29 % |
| ends | declined 48 | declined 44, physics 4 | declined 44, physics 4 |

The official fraction (0.553) sits close to the mean of the three
(0.529).  Pooled, 59 % of episodes are at or over 0.50; the platform's
four components are averaged over all episodes, so about 40 % of them
contribute nothing but fill today, most of them Task C's.

## 3. Where the items are, in points of the fraction

| task | unplaced soft | unplaced hard | of which the biggest hard class |
|---|---|---|---|
| A | 17.8 pt | 20.4 pt | 9 pt (94 % of the 0.75 x 0.56 boxes are left out by choice: count first) |
| B | **22.8 pt** | 25.9 pt | 4 pt |
| C | 16.6 pt | 39.2 pt | 6 pt |

Two facts stand out:

* **Soft cargo is the largest single pool in A and B.**  The soft
  boxes are the smallest and lightest items, 30 % of the manifest, and
  60-77 % of them are never placed while a third to two thirds of the
  container is empty.  In A the planner keeps a headroom reserve for
  them and still places 40 %: the hard stack ends in a standing layer
  (the mid-height transport band forbids a flat third layer) whose top
  carries a third of a soft row, and a soft box may not sit above a
  priority box, which is where the planner puts the priority cargo.  In
  B the ladder defers soft items behind every hard item in the pool and
  places 23 %; two soft classes are at 1 % and 4 %.
* **Task C is cut by the stream, uniformly.**  Every class is placed at
  44 % because the episode ends at the first item with no legal pose,
  and that item is an ordinary box (a 0.65 x 0.45 eleven times of 48,
  the smallest hard box eight) with the floor 52 % covered: the
  ladder's terraces leave no rectangle its size.  A brute-force probe
  confirms zero legal poses at the decline.

## 4. What was tried on B and C, and what it gave (items a scene)

| change | C analytic | C physics | B | verdict |
|---|---|---|---|---|
| ladder flags: floor before growth + all last-resort poses | +1.67 [+0.7, +2.7] | +1.0 [-0.2, +2.2], topples 0.19 -> 0.38 | 0 | the only positive C lever; twice the topples |
| planner pose search online: lowest / walls / band / fixed rows | -15 / +0 / -5 / -5 (four scenes) | | | no |
| online layer policy (flat first, level bands, shelf gallery) | +0.67 (n.s.), centre of mass -0.016 | -1.4, nine physics failures, topples up | -0.9 | stopped |
| pool-best selection (B) | | | -3.65 | no |

And on A since v18: the reserve at half (+1.3 items on the bench,
-2.6 official), standing rows (+0.65, soft -54), the size order and the
layered layout search as variants (0), the soft cargo's own rows (0).

## 5. Timing

The slowest official policy call: 7.31 s of 8 at a 5 s budget (v12),
5.9 s at 4.5 s (v18, v19).  The bench (6 s budget) reaches 7.95 s on
A, 7.79 on B, 6.97 on C; the platform machine is 1.3-1.5 times slower
per call.  4.5 s stays.

## 6. What the data says to do next

1. **Soft cargo in Task B** is the cleanest target: 22.8 points of the
   fraction, in the task where the agent has a pool to choose from.
   The ladder never picks a soft item while a hard one fits; a rule
   that places a soft item when a level, uncovered top of its size
   exists (and before the hard stack covers it) would be measured on
   the B suite in an afternoon.  Every soft item placed is a count
   point and a soft-score point at once, and it adds no height the
   hard cargo would not add.
2. **Soft cargo in Task A**: 17.8 points.  The planner's soft rows
   need a flat top: either the hard stack ends on a flat layer under
   the transport band (a plan variant whose third layer is capped at
   0.7765 m and the soft rows go on it), or the priority cargo goes
   somewhere soft need not cross (the shelf, a corner column).  A
   variant costs nothing on the platform: the plan score chooses.
3. **Task C** stays at the ladder plus, if anything, its two flags
   (+1 item, twice the topples: about +0.3 on the total, within noise).
   A stronger C needs a policy the physics engine agrees with, and the
   five tried did not.
4. Nothing on height: v19 priced a fourth layer at -2.6.

Expected value, if the soft rate in A and B rose from 40 % / 23 % to
60 %: +3.6 and +6.7 items a scene, about +5 points of the fraction
over the three tasks, which the v12 -> v18 slope prices at 4-5 points
of total.
