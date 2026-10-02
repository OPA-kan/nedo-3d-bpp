# Submission: rule-alpha with the stack option

The submission is the directory `dist/submit` (zipped as `dist/submit.zip`),
built from the tree by

```
python3 scripts/build_rule_alpha_submission.py
```

It contains `agent.py` (`submission/agent.py`: the `Agent` class the official
loader imports), `rule_alpha/` (the ladder, its analytic model, the Task A
offline phase; `agent/agent.py` travels as `rule_alpha/_production_agent.py`
for the geometry helpers it reuses), `wedge_rl/` (the stack option and its
policy in numpy) and `weights/stack/policy.npz`.  Numpy only; no torch, no
network; import takes 0.15 s.

Settings (`submission/agent.py`): the `ladder-stable` configuration the
benchmarks were run with, `offline_dry_run` (Task A: the agent dry-runs
itself over the constructive order within 140 s and defers what it declines
to the tail), `last_resort_relax` (one attempt with the margins relaxed to
the validator's own before giving up) and `policy_budget_seconds=6` (the
ladder stops asking further items of a Task B pool once the budget is
spent).  A decline is never `None` -- the official app reads the action's
keys first -- but a placement far above the container, which fails the
inclusion check and ends the episode.

## Check on the official simulator

```
cp -r dist/submit simulator/agents/submit
cd simulator && python -m scripts.run_test --module-path agents/submit/ \
    --config-path ../reports/submission/abc_config.json --result-dir results --verbose True
```

`reports/submission/abc_config.json` is the sample config's task 000 (Task A:
41 items, optimize, one visible) and 001 (Task B: 42 items, ten visible),
plus 002 = 001 with one visible item and no optimize (Task C).  Result
(`reports/submission/official-sample-abc.json`, this sandbox's 4 cores):

| task | fill score | placed | optimize | policy max |
|---|---|---|---|---|
| 000 (A) | 32.1 | 25 / 41 | 28.4 s (limit 180) | 1.26 s (limit 8) |
| 001 (B) | 28.7 | 23 / 42 | - | 5.17 s (limit 10) |
| 002 (C) | 23.1 | 23 / 42 | - | 1.52 s (limit 8) |

For comparison the repository's baseline `agent/agent.py` placed 7 of 41 on
task 000 (fill 14.0, `docs/COMPETITION_BASELINE.md`).

Second build (7e750fa; the any-container last resort and strict budget
accounting, `official-sample-abc-v2.json`): the same scores on these
single-container sample tasks (the new stage only acts when a priority
container exists), policy max 2.1 s (A), 5.3 s (B), 2.3 s (C), optimize
39 s.  On the bench's 48-scene physics suites this build is +1.9 (Task C)
and +2.0 (Task A) fill points over the first build and ahead of the live
trunk agent on both (`reports/wedge/findings.md`).

Third and fourth builds (v3: `no_cover_other_attribute`; v4: v3 plus
`priority_cargo_first`, commit 7606e9f): sample scores unchanged (the
sample tasks have one container and their coverage was already clean),
policy max 2.7 s (A), 5.4 s (B), 3.0 s (C), optimize 51 s.  On the bench
v3 clears soft/priority coverage and halves the Task C shake proxies for
-0.7 fill (n.s.); v4 places three more priority boxes a scene on the
priority-container layout and cuts its shake energy by a third for -0.3
fill on the Task A suite (n.s.).  See `reports/wedge/findings.md`.

Fifth build (v5, `official-sample-abc-v5.json`): Task A is packed offline
by the row planner (`rule_alpha/planner.py`) against the ladder's
dry-run, the better plan by fill + soft + priority shares replayed online
(`offline_planner`, `plan_score_weights`, `priority_is_structure`;
findings section "Task A: the row planner").  Sample scores A 29.2
(24 of 41; v4 32.1 / 25), B 28.7, C 23.1; optimize 30 s, policy max
4.4 s.  On the 48-scene Task A suite in physics the hybrid is level on
fill with v4 (37.8 against 38.0, n.s.), places 358 of 874 soft items
against 77 and 178 of 314 priority items against 130, lowers the centre
of mass, never topples in the shake (v4: 0.46 topples a scene) and ends
no episode on a physics failure (v4: 3).

Sixth and seventh builds (v6: no standing boxes, three ranked row
layouts; v7, commit 78d478f: v6 plus the tolerant plan replay and the
conservative transport model, findings section "v6 and v7").  v7 on the
48-scene Task A physics suite: fill 39.3 (v5 37.8), soft items placed
49 % (41 %), priority 79 % (57 %), one physics failure in 48 episodes.
Sample tasks: A 24.6 with 20 of 41 (the plan score takes the 4-of-4
priority plan over the ladder's 25-item one on that manifest), B 28.7,
C 23.1; optimize 54 s, policy max 4.5 s.

Eighth build (v8, commit 6d50bda): v7 with the planner's layouts run one
after the other against the whole budget, a cut plan used only when none
finished.  The official v7 result (total 29.47 against v5's 35.09) came
from the budget split: on the evaluation machine a third of the budget
did not finish a plan, so the soft rows and the priority cargo -- the
end of every plan -- were never planned.  Sample tasks unchanged from
v7 (A 24.6, B 28.7, C 23.1), optimize 40 s, policy max 4.5 s.  On this
machine v8 plans exactly as v7, so the v7 physics suite figures stand.

v8 then scored identically to v7 on the platform, so the packing itself,
not the budget, was the cause; the probes that followed are single
changes against v5 (`reports/submission/official-results.md` has every
official result): v9 (commit e56c13f) v5's planner settings plus the two
safety fixes -- 2.4 points below v5, so they are off again; v11 (commit
4220db3) the priority cargo mixed into the size order -- 2.8 below.
Every loss since v5 fell on the four non-fill components together and
in the order of the fraction of items placed, which the README zeroes
for an episode that places too few items.

Twelfth build (v12, commit 3e84dbb): `count_first` -- the small cargo
first, rows with the most boxes, the plan judged by its count share.
Task A physics suite against v5: +2.7 items a scene, fill -2.1, topples
0.31 a scene (v5 none).  Sample tasks: A 32.1 with 25 of 41, B 23.1
with 25 of 42, C 23.1.

Thirteenth build (v13, commit 006b59d): v12 with
`plan_standing_max_bottom` = 0.6 m -- the rows stand a box up only
where its bottom is at or below 0.6 m, since v12's topples were the
standing boxes on the fourth level (bottom 0.86 m).  Physics suite
against v12: topples 0.125 a scene (from 0.31), items -0.7 a scene,
fill -0.2 (n.s.); against v5 still +2.1 items.  Sample tasks identical
to v12 (no standing pose above the cap on those manifests).  Not
adopted after v12's official result (38.21, cog +7.2 and stability
+8.4 with those topples in): the count is what the platform pays for.

Fourteenth build (v14): v12 with the three priority orders planned one
after the other (`plan_variants` after-hard,mixed,last; the best
complete plan by the plan score) and the policy budget at 4.5 s (the
platform's slowest call reached 7.31 s of 8 at 5 s).  Physics suite
against v12: priority items +0.67 a scene [+0.21, +1.23], soft +0.3
(n.s.), count and fill unchanged, planner 27 s longer on the Actions
runners.  Two other probes did not move the count (the soft cargo
smallest first; a pure count plan score, which lost 26 soft and 26
priority items on the suite).

Fifteenth build (v15): v12's plan with the 4.5 s policy budget alone
(the v14 official result, 37.38 with more items placed, put the loss on
the platform's placement and soft penalties, which neither the bench's
AABB test nor a pybullet contact probe reproduces).  Sample tasks
identical to v12.

Eighteenth build (v18): v15 plus the priority container's room --
its priority rows built up one row at a time, the leftover normal hard
cargo into its spare rows, the cover veto letting a pair a shelf
separates through, and the soft headroom reserve per container
(findings section "The priority container's room").  Physics suite
against v12: items +2.2 a scene [+1.2, +3.4], fill +1.5, the
priority-container scenes 49.0 against 40.8 items; other layouts
unchanged.  Two probes between them did not move the count: v16 (the
size order as a variant) and v17 (the spare rows alone).

v18 scored 43.05 on the platform (v12 38.21): every component up,
placement +8.1.

Nineteenth build (v19): v18 with the soft headroom reserve sized for
half the soft volume (`soft_headroom_volume_share` 0.5, from 0.75).
Physics suite against v18: items +1.3 a scene [+0.5, +2.3], fill +1.2,
the soft count unchanged, priority +11 over the suite, topples 21
against 11; the two-container scenes 53.0 -> 57.9 items.  Two other
probes: no reserve at all halves the soft count (not adopted); the
row-depth search scored over a row's layers, as a planner variant, is
in the code but off (count +0.08, n.s.).

v19 scored 40.44 on the platform (cog -4.5, stability -4.2, placement
-5.55 against v18): a fourth hard layer on standing boxes.  Three
probes after it were not adopted: v20 (standing rows over the flat
layers: soft -54 on the suite), v21 (ladder flags: C +1.0 n.s., topples
doubled), v22 (an online layer policy for B/C: physics -1.4).

Twenty-third build (v23): v18 with soft cargo carrying load in the
analytic support model (`soft_is_structure`) and, in the online tasks,
a soft item going to the shelf gallery, onto soft cargo or onto a top
no hard box could use before the hard cargo is tried
(`soft_first_when_free`).  Physics suites against v18: Task A +2.65
items a scene, B +4.92, C +4.65; costs: soft cargo covered 0.08 / 0.10
/ 0.29 a scene, Task C topples 9 -> 29 (findings section "Soft cargo:
the one-layer gallery").

Twenty-fourth build (v24): v23 with the cover veto counting a packed
item as under the box when its bottom is below the box's bottom (the
old test skipped a soft box whose settled top sat a fraction of a
millimetre above the stack option's rounded support top, and the box
landed on it: every covered soft item on the Task C probes), and, in
the online tasks, the stack option's soft poses off the floor needing
80 % of their footprint in contact (`stack_soft_min_support`; the
offline phase turns it off, where it cost 1.5 items a scene for no
topple).  Physics suites against v23: covered soft cargo 0 / 0 / 0.02 a
scene, Task C topples 0.60 -> 0.21, items A -0.4 (n.s.), B +0.3 (n.s.),
C -1.0 [-2.0, -0.1] (findings section "v23's costs: the veto's micron,
and the soft pile").

v24 scored 36.58 on the platform (v18 43.05): soft +18, but the load
0.02-0.045 higher, Task B's priority cargo halved and hard volume
displaced by soft (fill -3), which the platform priced at three times
the soft gain.  v23's direction is off again.

Twenty-fifth build (v25): v18's loads (the cover veto's tolerance fix
kept; it changes nothing on them) with the soft headroom reserve sized
for 0.9 of the soft volume (0.75 in v18): v19's move to 0.5 cost 2.61
points on the platform for +1.33 items and +0.015 of the centre of
mass, and this reverses it at about the same size.  Physics suite
against v18 (Task A, the only task the reserve touches): items -0.85
[-1.71, -0.06], the centre of mass -0.013 [-0.021, -0.005], topples
0.23 -> 0.19 (n.s.), episodes above the count threshold 45 -> 44 of 48,
the soft count kept (analytic +0.04).

Twenty-sixth build (v26): v18 with the shadow check (`shadow_check`;
`rule_alpha/shadow.py`).  Every chosen pose is tried, before it is
committed, in a private pybullet world the agent builds from the
observation with the simulator's own container meshes, shelves and
item dynamics, running the official placement test itself (the
transport sweep at 0.01 m within 0.015 m of the packed items and
shelves, then the warp and 300 settle steps with the 0.3 m / 45 deg
limits); on two physics scenes the verdicts matched the official
validator on 155/155 transport and 142/142 settle probes and the
settled poses agreed within 0.4 mm.  A pose the test would reject, or
one that lands over 0.10 m / 15 deg away, is replaced by the next
survivor of the decision that passes, or the decision goes on to its
next item and stage; a milder slide keeps the pose unless a survivor
passes.  0.2-0.5 s a check inside the 4.5 s budget, the last resort
leaving room for it; without pybullet the agent is v18.  Physics
suites against v18: items A +0.44 (6 scenes up, 0 down), B +0.85, C
+0.56; soft B +0.52 (16 up, 0 down); priority B +0.17; settle ends 4
-> 1 on B and on C; slowest call shorter on every suite (findings
section "The shadow world").  Official sample: A 32.11 / 25 placed
(v18 the same), B 25.99 / 25 (v18 23.06 / 25), C 23.14 / 23 (the
same); policy max 1.13 / 3.73 / 0.85 s (v18 1.46 / 4.22 / 1.70),
optimize 28 s (`official-sample-abc-v26.json`).

Twenty-seventh build (v27): v26 with the physics resort
(`physics_resort`).  Before a decline, every pose the geometry allows
on the floor or on a packed top in any container -- the stack option's
candidate generator with the tower rule, the extra transport clearance,
the support shares and the headroom reserve off, a 4 cm anchor lattice
across every support, the cover rule kept -- is tried lowest and best
supported first in the shadow world until one stands; a decline ends
the episode, a pose the physics accepts does not.  With a Task B pool
the resort may run 1.5 s past the 4.5 s budget (the limit is 10 s).
Physics suites against v26: items A +0.65 (16 scenes up, none down), B
+1.00 (19 up, none down), C +0.96 (19 up, none down); soft B +0.98, C
+0.44; episodes over half the items B 30 -> 34, C 11 -> 17 of 48;
topples unchanged; CoM +0.002-0.006 (findings section "The physics
resort").  Official sample: A 32.11 / 25 placed (v26 the same), B
27.28 / 25 (v26 25.99 / 25), C 23.14 / 23 (the same); policy max 0.93 /
4.06 / 0.93 s, optimize 31 s (`official-sample-abc-v27.json`).

Twenty-eighth build (v28): v27 with two time changes.  With a Task B
pool the stages before the physics resort keep their deadlines and the
resort uses its 1.5 s past the budget alone (the reserve had cut a
soft-edge decision at 3.7 s on b-c2p-s0011 and the seven items after
it); and the shadow's settle stops once the box has rested 20 steps
(the pose within 0.8 mm of the full 300 steps on 168 probes, 0.10-0.15
s a check instead of 0.25-0.3).  Physics suites against v26: items A
+0.65 (16 up, 0 down; identical to v27), B +1.23 (26 up, 0 down; v27
+1.00), C +0.96 (identical to v27); soft B +1.15; priority B +0.17;
episodes over half the items B 30 -> 34, C 11 -> 17.  Official sample:
A 32.11 / 25, B 27.28 / 25, C 23.14 / 23 (v27 the same); policy max
0.99 / 4.89 / 0.87 s (the B call past the 4.5 s budget is the resort's
window, under the 10 s limit), optimize 25 s
(`official-sample-abc-v28.json`).  After v27's official run (its
slowest call 6.56 s: a candidate generation started just before the
resort's deadline) a generation starts only when the slowest so far
and a check fit before the deadline, and the Task B window past the
budget is 2.5 s (at 1.5 s the guard cost 0.7 items a scene on B).
Physics B at the 4.5 s budget against v26: items +1.38 (28 scenes up,
none down), soft +1.25, priority +0.17, slowest call 6.84 s (limit
10 s); C against v27: identical, slowest call 4.0 s.  Official sample
unchanged, policy max 1.42 / 4.60 / 1.27 s.

Twenty-ninth build (v29): v28 with the pocket guard (`pocket_guard`;
`rule_alpha/pocket.py`).  On the v28 end states, 52 of the 87 small
boxes on the floor of the Task C suite -- every one of them soft --
stood where the biggest hard box left unplaced would otherwise have
had a floor pose.  After the ladder decides a floor pose for a soft
item, the guard generates every pose the geometry allows (the stack
option's candidates, flat, half supported) and takes the one after
which the load keeps the most level, reachable slots for the big hard
classes still expected (soft tops counted as dead ground for hard
cargo), when it beats the ladder's pose by a quarter of a slot.  The
classes and their weights: a Dirichlet prior over the sample stream's
hard classes updated with every item seen, and the chance each still
arrives in the items expected to remain; on Task A the manifest's
counts, and the guard stays off under a plan.  0.75 s a guarded
decision.  Physics suites against v28 at the 4.5 s budget: items C
+1.15 a scene (20 up, 7 down; episodes over half the items 17 -> 22),
B +0.17 (34 -> 38), A +0.10 (6 up, 2 down; the plan-off form makes it
v28's); C's topples 0.17 -> 0.38 (the extra items stack higher).  A
shadow shake that vetoes high or standing poses which topple under a
0.3 g tilt is built and measured (C +0.15 more, B -0.40, topples 0.06
on both) and left off here as a separate probe.  Official sample: A
32.11 / 25, B 27.28 / 25, C 23.14 / 23 (the same as v28); policy max
and optimize in `official-sample-abc-v29.json`.

Thirtieth build (v30): v29 with the count mode (`count_mode`;
`rule_alpha/config.py`, the second pass of `_physics_resort`).  The
platform scores every component but the fill as zero for an episode
under a count threshold the fit puts near half the items, so the item
that crosses it is worth about 56 points to its episode where any other
is worth 0.3.  The v29 boards that end one to three items short (C 11
of 48 episodes, B 9, A 3) still hold hundreds of poses the analytic
validate and the shadow physics accept, every one of them on priority
or soft cargo: the cover rule alone declines them.  While the containers
hold fewer than ceil(items / 2) items (41 a container expected, the
manifest's count on Task A), the physics resort runs once more with
both cover vetoes off and soft tops as structure, lowest and
best-supported pose first, the shadow judging; above the threshold the
strict rules are back and the next decline ends the episode as before.
Physics suites against v29 at the 4.5 s budget: items C +1.83 a scene
(23 up, 2 down; episodes over half the items 22 -> 39), B +0.33 (38 ->
45), A -0.15 (two-container run-to-run spread; 45 -> 47); priority
boxes covered 0 -> 20 on C's 48 scenes and 0 -> 4 on B's, soft 0 -> 8
on C; topples C 18 -> 18, B 11 -> 7; slowest call C 4.3 s, B 6.9 s (the
resort's cap, as v29).  Official sample: A 32.11 / 25, B 27.28 / 25, C
23.14 / 23 (the same as v29: the sample episodes are already over the
threshold, so the mode never engages); policy max B 4.66 s, optimize
20 s (`official-sample-abc-v30.json`).

Thirty-first build (v31): v30's count mode as one resort pass.  The
v30 boards still under the threshold were out of time, not out of
poses (c-c2-s0004 had 20 of 20 shadow-ok poses in both containers and
the count pass never started; b-c1-s0004 had poses for every pool
item), and where time was left the lowest poses all tipped while the
whole-top ones behind them stood (c-c1-s0003), or the sweep was blocked
by boxes the resort had set by the door.  Now the resort generates the
covering poses in the same pass under the threshold (one generation per
item size and container), tries the poses that cover nothing first,
whole-top poses before partial ones, drops a pose group (cover class,
level, support share) after three settle failures in a row, takes the
pool's smallest item first, stops a settle once the box has fallen or
tipped past the validator's limits, and may run
`count_mode_extra_seconds` (1.0 s on A and C, 3.0 s on B) past the
budget while under the threshold.  A sweep-only prefilter was tried and
dropped (it never skipped a pose and spent the window: C 42 -> 36
episodes over the threshold).  Physics suites against v30 at the 4.5 s
budget (`count4-core`, `count4-core-b`): items C +0.40 a scene (8 up, 3
down; episodes over half the items 39 -> 43), B +0.44 (11 up, 2 down;
45 -> 48 of 48), A +0.23 (6 up, 1 down; 47 of 48; `count4-core-a`);
priority boxes covered C 20 -> 22, B 4 -> 6, soft C 8 -> 5; topples C 18 -> 19, B 7 -> 16 (the extra items stack higher);
slowest call C 4.9 s, B 6.8 s.  Ordering the resort's poses by the
deeper floor they wall off from the sweep (`resort_shade_step`) was
level on the suite (`shade2-core`) and stays off.  Official sample: A
32.11 / 25, B 27.28 / 25, C 23.14 / 23 (as v30); policy max B 4.61 s,
optimize 21 s (`official-sample-abc-v31.json`).  Official result 52.45
(v29 44.93): fill +1.6, cog +10.3, stability +12.5, placement +7.1,
soft +8.05, the fraction placed 0.5848 -> 0.6104 -- the count
threshold's signature, every non-fill component up together.

Thirty-second build (v32): v31 with the threshold taken as strictly
more than half (`count_mode_strict`: 42 of 82, 21 of 41 either way;
the two-container suites ended at exactly half often, C 6 and B 2 of
48, and whether that counts is unknown), the resort's support floor at
a quarter under the threshold (`count_mode_min_support`; the shadow's
settle judges the rest), and the planner's `first` order variant on
Task A (the priority cargo before everything on every layout, planned
alongside `after-hard`; `rule_alpha/planner.py`).  Physics suites at
4.5 s against v31: C placed +0.06 a scene, episodes strictly over half
37 -> 41 of 48 (at or over: 43 -> 43), priority covered 22 -> 22, soft
5 -> 11 (`strictms-core`); B +0.08, strictly over half 46 -> 48
(`strict-core-b`); A -1.5 items and -1.8 fill, priority placed 0.66 ->
0.78 a share, loads 0.010 lower, 48 of 48 over the threshold either
way (`strictfirst-core-a`; at the fitted prices about +0.9 on the
total).  Official sample: A 32.11 / 25, B 27.28 / 25, C 23.14 / 23 (as
v31); policy max B 4.50 s, optimize 20 s
(`official-sample-abc-v32.json`).

Thirty-third build (v33): v32 with the sweep-shade veto on Task C
(`shade_veto_area` = 0.15 m^2, `resort_shade_step` = 0.1;
`wedge_rl.stack.shade_area`).  The seven C episodes still at or under
the count threshold after v32 all had standing poses for the next box
that the simulator's transport sweep could not reach, behind stacks
the ladder had built at the door; the shadow gate now vetoes a pose
that walls off more than 0.15 m^2 of lower floor with headroom behind
it (the decision's other survivors first, the next stage otherwise,
the pose itself before a decline), and the resort orders its poses by
the same measure.  Off under a Task A manifest (it broke the plan
replay) and with a Task B pool (it cost four crossings).  Two gate
faults fixed on the way: an alternative built from the ladder's
survivors after the pocket guard had moved the placement to the other
container (an inclusion failure on b-c2p-s0005), and a settled-pose
inclusion veto that refused planned poses the platform accepts
(telemetry now).  Physics suites at 4.5 s (`v33-core`, `v33-core-b`,
`v33-core-a`) against the v32 form: C placed +2.0 a scene (27 up, 4
down), every episode over the threshold (43 -> 48 of 48), fill +1.8,
priority boxes covered 22 -> 12, topples 21 -> 9, CoM +0.012, slowest
call 5.3 s; B level (48 of 48 over, -0.17 items); A as v32's form (its
run-to-run spread comes from the optimize race between the dry-run and
the planner on the shelf layouts: a-c1s-s0006 and s0007 end at 19 of
41 when the dry-run's plan wins, 24 and 23 under the planner's).
Official sample: A 33.46 / 28, B 27.28 / 25, C 26.44 / 25 (v32: 32.11
/ 25, 27.28 / 25, 23.14 / 23); policy max B 4.87 s, optimize 25 s
(`official-sample-abc-v33.json`).

## Known limits

* Task B policy time is the closest to its limit (5.2 s of 10 on this
  machine); `policy_budget_seconds` in `submission/agent.py` is the knob.
* The Task A gain measured on the bench is +0.8 fill points in physics over
  the constructive order (analytic +2.5); the difference is the analytic
  model's optimism about the settled board.
* Bench figures (48-scene suites, physics): Task C 27.85, Task A 36.4.
