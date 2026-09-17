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

## Known limits

* Task B policy time is the closest to its limit (5.2 s of 10 on this
  machine); `policy_budget_seconds` in `submission/agent.py` is the knob.
* The Task A gain measured on the bench is +0.8 fill points in physics over
  the constructive order (analytic +2.5); the difference is the analytic
  model's optimism about the settled board.
* Bench figures (48-scene suites, physics): Task C 27.85, Task A 36.4.
