# Official evaluation results (as reported by the competition platform)

| build | fill | cog | stability | placement | soft | placed fraction | optimize s | policy s |
|---|---|---|---|---|---|---|---|---|
| trunk best (`trueenvelope`, from the trunk's HANDOFF) | 34.25 | 40.68 | 53.24 | 16.95 | 21.30 | 0.505 | | |
| v1 (33fce01: stack option, dry-run order, last resort) | 35.63 | 36.30 | 45.87 | 15.1 | 8.9 | 0.504 | 139.2 | 7.48 |
| v4 (7606e9f: any-container last resort, no-cover veto, priority first) | 36.29 | 41.38 | 50.12 | 19.4 | 10.4 | 0.515 | 138.6 | 7.21 |
| v5 (c47d35e: Task A row planner, hybrid with the dry-run) | 34.60 | 40.92 | 46.05 | 25.5 | 20.45 | 0.503 | 139.1 | 6.43 |
| v7 (78d478f: no standing boxes, three layouts, replay tolerance, conservative transport) | 34.52 | 32.32 | 37.60 | 16.0 | 16.35 | 0.488 | 140.4 | 6.46 |
| v8 (6d50bda: v7 with the layouts run one after the other against the whole budget) | 34.52 | 32.32 | 37.60 | 16.0 | 16.35 | 0.488 | 139.8 | 6.47 |
| v9 (e56c13f: v5's planner settings plus the replay tolerance and the conservative transport model) | 34.09 | 37.25 | 41.87 | 21.4 | 20.6 | 0.493 | 139.9 | 6.42 |
| v11 (4220db3: v5 with the priority cargo mixed into the size order) | 34.49 | 36.37 | 41.84 | 22.2 | 17.55 | 0.4996 | 139.9 | 6.53 |
| v12 (3e84dbb: count first -- small cargo first, rows with the most boxes, count-weighted plan score) | 34.05 | 48.08 | 54.46 | 27.5 | 18.05 | 0.540 | 139.9 | 7.31 |
| v14 (588645a: v12 with the three priority orders planned in sequence, policy budget 4.5 s) | 34.06 | 47.14 | 54.30 | 25.6 | 15.8 | 0.5427 | 140.0 | 6.71 |
| v18 (3bdd115: v15 plus the priority container's room -- priority rows deep first, normal cargo in its spare rows, the cover veto through a shelf, the soft reserve per container) | 34.82 | 54.83 | 62.69 | 35.6 | 19.85 | 0.5526 | 139.3 | 5.92 |

| v19 (b8d99c1: v18 with the soft headroom reserve sized for half the soft volume) | 34.82 | 50.32 | 58.50 | 30.05 | 20.2 | 0.5558 | 139.7 | 5.88 |
| v24 (7f2edae: v18 plus v23's soft cargo as structure and soft first when free, the cover veto's tolerance fixed, the stack option's soft support share online) | 31.78 | 40.59 | 46.43 | 24.05 | 37.9 | 0.5447 | 139.0 | 7.03 |
| v25 (e1ff972: v18's loads with the soft headroom reserve at 0.9 of the soft volume; the cover veto's tolerance fix in) | 35.10 | 50.59 | 58.47 | 29.3 | 20.6 | 0.5585 | 139.0 | 5.58 |

v25's total was 40.53, 2.52 below v18 and within 0.09 of v19 -- the
reserve moved the other way (0.9 against v19's 0.5) and landed on the
same components: fill +0.28, soft +0.75, the fraction placed +0.6
points (the bench had Task A -0.85 items), cog -4.2, stability -4.2,
placement -6.3.  Two builds that differ from v18 by one setting each,
in opposite directions, score the same 2.5 points under it: the height
story that explained v19 does not explain v25 (its load is lower), and
the reserve is not what v18's 43.05 rests on.  What v19 and v25 share
against v18 is placement -6, and what v25 alone carries is the veto's
tolerance fix, on every task -- measured on v23's loads only (Task C
-1.1 items), never on v18's.  v18 with the current code on all three
suites is the next measurement.

Measured (`reports/bench/v18fix-core-{a,b,c}`, the v18 arm on the
current code against the stored v18 runs): the fix changes 3 to 8
scenes of 48 on each suite and the means by nothing -- items A +0.29
[-0.02, +0.69], B -0.19 [-0.42, -0.04], C +0.25 [-0.04, +0.77]; the
centre of mass within 0.002; priority and soft cargo within 0.2 a
scene; the covered priority cargo 0.08 -> 0 a scene on B.  So v25's
2.5 points under v18 are the reserve's (0.75 -> 0.9), which the bench
prices at -0.85 items and -0.013 of the centre of mass on Task A and
the platform paid as cog -4.2, stability -4.2, placement -6.3 with the
fraction placed *up* 0.6 points; and v19's 2.6 points under v18 were
the reserve's the other way (0.5), with the fraction up 0.3 points.
Three builds one setting apart, the middle one 2.5 points above both
neighbours, the bench unable to order them: at this size of change the
platform's score is not a function the bench resolves, and v18's
43.05 is best read as a favourable realisation of a family that
scores 40.5-43 -- to be beaten by a change the bench can see whole
(several items a scene on B and C at the same height), not by tuning.

v24's total was 36.58, 6.47 below v18 (v23 was not run on the
platform, so this is v23's soft cargo and v24's fixes together): soft
+18.05 (the covered soft cargo gone and the soft galleries), but fill
-3.04 (the first fill under 34 of any build), cog -14.2, stability
-16.3, placement -11.6, on 0.8 points fewer of items placed (0.5447)
with the slowest policy call at 7.03 s against v18's 5.92 (limit 8).
The physics suites had v23 +2.65 / +4.92 / +4.65 items a scene over
v18 and v24 within an item of v23: the platform saw fewer items and
less volume, not more.  A time-out is not the reason: the official
runner reports a timed-out call at the limit itself (its `poll` returns
at the limit and that elapsed time is what `time_results` keeps), so a
slowest call of 7.03 s means no call reached 8 s.  What the bench and
the platform agree on is the structure of the load: the centre of mass
+0.02 / +0.04 / +0.03 (Task B's two-container layout +0.045), which
v19 priced at about 3 cog and 3 stability points per 0.01, and the
priority cargo on Task B halved (c1 2.9 -> 1.8, c1s 2.7 -> 1.3, c2 5.7
-> 3.0 a scene), which is the placement score.  Soft cargo is smaller
than hard cargo, so the soft galleries that lift the soft score are
volume the hard cargo no longer gets: fill -3 on the same count.  The
platform's prices, per component weight: soft +18 x 0.142 = +2.6
against cog -14 x 0.216, stability -16 x 0.21, placement -11.6 x 0.143
and fill -3 x 0.286 = -9.1.  v23's direction (more soft cargo, higher)
is a loss at those prices whatever the count does.

v19's total was 40.44, 2.61 below v18, on 0.3 points more of items
placed (0.5558 against 0.5526): fill and soft held (0.00, +0.35), cog
-4.5, stability -4.2, placement -5.55.  The bench had it +1.33 items a
scene with the centre of mass 0.015 higher and topples 21 against 11:
the fourth hard layer the smaller reserve allows sits on standing boxes
at 0.93 m, and the platform's cog and stability scores paid for that
height and those topples at once, with too little count to cover it
(v12's 15 topples were carried by 3.7 points of items placed; v19's
0.3 points carried nothing).  So topples and height do count, at
roughly this rate: -0.9 cog and -0.8 stability points per topple a
scene on 48 scenes, or -3 cog points per 0.01 of centre-of-mass ratio.
Reverted: v20 is v18's reserve again, and the count has to come from
below, not from a higher stack.

v18's total was 43.05, 4.85 above v12 and the best so far, on 1.25
points more of items placed (0.5526 against 0.540).  Every component
rose: fill +0.77, cog +6.75, stability +8.23, placement +8.1, soft
+1.8; by weight cog 1.45, stability 1.75, placement 1.16, soft 0.26,
fill 0.22.  The placement score's jump is the priority cargo staying in
its container (the deep-first rows leave it room, so the last resort
sends less of it to a normal one) and the count crossing the threshold
on more episodes; the bench had predicted the count (+2.2 items a
scene, the priority-container scenes 40.8 -> 49.0) and nothing else.
The slowest policy call took 5.92 s at the 4.5 s budget.

Seven totals fit the weights to 0.001: fill 0.286, cog 0.216,
stability 0.213, placement 0.143, soft 0.142 -- 2 : 1.5 : 1.5 : 1 : 1.

v14's total was 37.38, 0.83 below v12, with *more* items placed
(0.5427 against 0.540): the first run where the four components did
not follow the count.  The fill and the stability held (0.00, -0.16),
the cog lost 0.94, and the two penalty scores lost together --
placement -1.9, soft -2.25 -- which is exactly what the bench could
not see: it had the three orders placing 0.67 more priority items a
scene with no covered priority or soft cargo by its AABB test, and the
platform's "contact from above" test found more of both covered.  So
placing more priority cargo is not the aim; placing it where nothing
of another attribute can touch it from above is, and the mixed and
last orders (priority in the size order, or after the soft cargo) put
it where that happens.  The policy budget at 4.5 s brought the slowest
call to 6.71 s (7.31 at 5 s) and cost nothing the count shows; it
stays.  The next build is v12's plan with the 4.5 s budget (v15).

Six totals fit the weights to 0.001: fill 0.287, cog 0.219, stability
0.210, placement 0.143, soft 0.141 -- which is 2 : 1.5 : 1.5 : 1 : 1
(2/7, 3/14, 3/14, 1/7, 1/7) within the rounding of the reported
components.  v14's loss by component: cog -0.21, placement -0.27, soft
-0.32, stability -0.03.

v12's total was 38.21, the best so far (v5 35.09), and it confirms the
count threshold: the fraction placed rose from 0.503 to 0.540 and the
three components that follow it rose with it -- cog 40.9 -> 48.1,
stability 46.1 -> 54.5, placement 25.5 -> 27.5 -- by almost exactly the
slope the five earlier runs gave (about 2 cog and 2.3 stability points
a percent of items placed); the fill (-0.55) and the soft score (-2.4)
paid for it, since the small hard cargo first leaves less room for the
soft cargo on top.  The bench's 15 topples on 48 scenes (v5: none) did
not show in the platform's stability score, so on the platform the
count of items in an episode outweighs what the shake proxy measures.
The slowest policy call took 7.31 s of the 8 s limit (v5 6.43 s, same
5 s budget): the pool tried smallest first runs the ladder to its
deadline more often, and a call over the limit is answered with a
random action by the platform, so the next build lowers the budget.

Five totals now pin the weights: the least-squares weighting summing to
one that reproduces all five exactly is fill 0.287, cog 0.222,
stability 0.207, placement 0.143, soft 0.140 -- the fill three parts in
ten, the centre of gravity and the shake test two each, the placement
and soft scores one and a half each (the nearest round weighting,
0.3/0.2/0.2/0.15/0.15, misses v12 by 0.65 because the reported
components are rounded).  With these weights one percent of items
placed is worth about 0.9 points of total through cog and stability
alone, and a fill point 0.29.

v11's total was 32.29.  Every change from v5 has now lost the same four
components together, and by how much tracks one number: the fraction of
items placed.  v5 0.503 -> cog 40.9, stability 46.1; v11 0.4996 -> 36.4,
41.8; v9 0.493 -> 37.2, 41.9; v7 0.488 -> 32.3, 37.6; and v4 0.515 ->
41.4, 50.1.  The README says every component but the fill is zero for an
episode that places fewer than "a certain number" of items, and the
platform reports the components as averages over episodes.  Our episodes
place about half the items, so a threshold near there would zero the
four components on roughly half of them, make their averages swing with
tiny changes in the count (about 4.6 stability points per percent of
items placed, from these five runs), and put the values *conditional on
crossing it* at about twice what we see -- cog around 80, stability
around 90 -- which with these weights is a total near 60, the top of the
leaderboard.  So the count of items placed per episode, not the volume,
is what the score turns on, and the next builds place the small cargo
first (``count_first``).

v9's total was 32.69: the two "safety fixes" alone cost 2.4 points
against v5 (cog -3.7, stability -4.2, placement -4.1, fill -0.5, soft
+0.15), and v7's other two changes another 3.2.  On the bench's physics
suite v5 and v9 are indistinguishable on every proxy (mass-weighted
centre of mass 0.364 / 0.365, shake shift 0.0240 / 0.0237, no covered
priority or soft cargo in either), so the bench does not measure what
the platform's cog, stability and placement scores measure.  The
platform is deterministic (v5 resubmitted and v8 against v7 gave
identical components), so each official run is one clean measurement.

Three totals fit the weights better: on a 0.025 grid, the weightings
within 0.15 of all three put the fill at 0.275-0.325, cog and stability
together at 0.40-0.45, placement at 0.10-0.175 and soft at 0.075-0.20;
(0.30, 0.35, 0.10, 0.125, 0.125) fits within 0.05 in total.  So the
centre of gravity and the shake test together weigh half again as much
as the fill.

v7's total was 29.47 against v5's 35.09, while the bench's 48-scene
physics suite had v7 ahead of v5 on every count.  The difference is the
budget: v7 gave each of its three layouts a third of the 140 s, and on
the evaluation machine (about five times slower than this sandbox) a
third was not enough to finish a plan, so every plan was cut before its
soft rows and its priority cargo -- which is exactly what the official
soft (-4) and placement (-9.5) scores show, and the ladder's
improvisation over a half plan is what the cog and stability drops
show -- so ran the reasoning; v8, which runs the layouts one after the
other against the whole budget, then scored *identically* to v7 in every
component (total 29.47 again), so the budget split was not the cause:
the plans were complete in both and the platform's four non-fill
components fell on the v7 packing itself, which the bench's proxies
(topples, shake energy, centre-of-mass height, cargo placed) do not
see.  The v5 build stays the best official result.

Two totals (v5 35.09, v7 29.47) constrain the platform's weights: on a
0.05 grid, 23 weightings summing to one reproduce both within 0.2.
None gives the fill more than 0.4, most give cog and stability together
0.3-0.5 and soft and placement together 0.2-0.35; (0.30, 0.15, 0.25,
0.15, 0.15) for fill, cog, stability, placement, soft fits within 0.17.
So the fill is one part in three or four, and the four other parts --
which the bench can only proxy -- carry the rest; a third total would
pin them.

v5 against v4: soft +10.0 and placement +6.1 (the two components the
planner was built for; the bench's counts of soft and priority cargo
placed moved the same way), fill -1.7, stability -4.1, cog -0.5.  The
platform's total for v5 was 35.09.  Optimization used the whole budget
(139 s): on that machine the ladder's dry-run never finishes, so the
planner's plan is the one in use on every Task A scene.

Both of our runs end with the status "Stopped in the middle. Did not
satisfy {is_valid, is_placed_safe, is_included}": that is the surrender
action (a placement far above the container) the wrapper answers with
instead of declining, and it is not scored any lower than a decline.
