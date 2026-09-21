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

## Known limits

* Task B policy time is the closest to its limit (5.2 s of 10 on this
  machine); `policy_budget_seconds` in `submission/agent.py` is the knob.
* The Task A gain measured on the bench is +0.8 fill points in physics over
  the constructive order (analytic +2.5); the difference is the analytic
  model's optimism about the settled board.
* Bench figures (48-scene suites, physics): Task C 27.85, Task A 36.4.
