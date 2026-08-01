# Stride x endgame rollout saturation

## The question

The rollout enforce ablation (`docs/VISIBLE_POOL_ROLLOUT.md`, Actions run
`30716558143`) left one number unexplained: rollout non-degeneracy was
138/240 (57.5%) at steps 0-9 and 2/166 (1.2%) from step 10 onward. Late in an
episode the rollout almost never distinguishes the actions under comparison.

Two mechanisms produce that, and they demand opposite responses.

* **Saturation.** The container really is full. No future placement exists,
  every Top-K action has the same consequence, and the tie is correct. There
  is nothing to fix inside the rollout; a late-episode value signal has to
  come from somewhere else entirely.
* **Coverage hole.** Future placements do exist, but the per-step anchor
  budget is spent on the dense infeasible prefix of the anchor scan and never
  reaches them. Every branch returns `placed_count = 0`, the keys tie, and
  the tie is an artefact of the measurement rather than a property of the
  state.

Until this is settled, tuning the enforce band or the rollout weights is
guesswork: a coverage hole would make the late band uninformative no matter
what the weights are.

## Why stride is the discriminating instrument

The rollout caps each future step by an anchor-attempt count, not by wall
time (`bounded_rollout_decision`). Attempts are consumed in scan order, so a
budget of 64 buys the *first* 64 anchors, not 64 anchors spread over the
grid. If the feasible remainder of a nearly-full container lives late in that
order, no budget under the deadline will reach it.

`stride`/`stride_offset` systematically subsample the deduped anchor
sequence: only every stride-th anchor is validated. A skipped anchor yields
nothing and consumes no round slot, so **the attempt budget is unchanged and
the reach is multiplied**. That makes it the one knob that separates "did not
look" from "looked and there was nothing there" without also changing cost.

The parameter existed before this experiment but was unreachable on the
shipped path: it was implemented only in `iter_cartesian_attempts`, while
`ANCHOR_GENERATOR_MODE` defaults to `support_plane`, and neither
`iter_attempts` nor `iter_prioritized_candidates` forwarded it. Both plane
generators now implement it and all four layers forward it, defaulting to
stride 1.

## Design

`scripts/measure_rollout_saturation.py` evaluates three arm families on the
same reconstructed Top-K, per saved snapshot:

| family | stride | attempts/step | role |
| --- | ---: | ---: | --- |
| `baseline` | 1 | 64 | the shipped shadow setting; the control |
| `stride-S` | S | 64 | same cost, wider reach |
| `budget-N` | 1 | N | reach oracle at N/64 times the cost |

`budget-512` is the upper bound on what any amount of looking finds under
this proxy. Whatever it cannot find is evidence for real saturation. What
`stride-S` recovers of what `budget-N` recovers is the part that is available
for free.

Reported per arm and per band (`step < 10` vs `step >= 10`):

* **non-degenerate** - the Top-K rollout keys are not all equal. This is the
  quantity the enforce run reported.
* **any future placement** - some branch reached `placed_count > 0`. This is
  deliberately tracked apart from non-degeneracy: a key can split on the
  accumulated release-risk terms alone while every branch still places
  nothing. That is discrimination without reach, and it is a weaker result.
* **recovered baseline ties** - of the snapshots where `baseline` was
  degenerate, how many this arm splits.
* **attempts used** and **elapsed ms** - the two cost currencies. They do not
  move together: stride holds attempts fixed but not wall clock, because
  advancing the anchor iterators past skipped positions still costs time.

Each stride is measured at every valid phase (`stride-4`, `stride-4+1`,
`stride-4+2`, `stride-4+3`) so a lucky phase is visible as spread rather than
reported as the effect.

## Method boundaries

Read these before quoting any number from the report.

* The immediate Top-K is reconstructed by consuming
  `iter_prioritized_candidates` under a **fixed attempt budget** and feeding
  it through the production `VisiblePoolRolloutCollector`. That makes the
  rows deterministic and reproducible, but it is **not** a replay of any
  particular deadline-limited live search. The arms are comparable to each
  other; the absolute rates are not the same quantity as the live shadow
  rates from run `30716558143`.
* Stride is applied to the rollout's **future** transitions only. The
  immediate candidate set under comparison is never resampled, so stride
  cannot change which actions are being evaluated - only how widely their
  consequences are searched.
* These are static-proxy rollouts on saved states, not PyBullet
  counterfactuals. A future release transition still terminates the branch
  with `release_transition_uncertain`.
* Non-degeneracy is a property of the measurement, not a score. An arm that
  discriminates more is not thereby a better policy. Nothing here is
  adoption evidence for enforce; a live ordering change still needs its own
  repeated ablation.
* The saved snapshot pool is late-heavy (steps 8-16). Its "early" band is
  steps 8-9 only, so it is not a control for the full 0-9 band the enforce
  run reported.

## Offline command

```bash
python3 scripts/measure_rollout_saturation.py \
  --output-dir reports/rollout-saturation/<run> \
  --stride 2 --stride 4 --stride 8 \
  --stride-offset 0 --stride-offset 1 --stride-offset 2 --stride-offset 3 \
  --budget 256 --budget 512 --jobs 4
```

Snapshots default to `reports/replay-dataset/*/step-*-state.json`. Sharding
across processes with `--jobs` cannot change a result, only the wall clock:
every snapshot is measured independently from a file on disk and the rows are
re-sorted before the summary.

## Result

Local Linux run, 48 committed snapshots, `reports/rollout-saturation/local-20260801`.
Late band = 37 snapshots at step >= 10. Phases `+1..+3` are in the report;
the table shows phase 0.

| arm | non-degenerate | any future placement | recovered baseline ties | mean ms | max ms |
| --- | ---: | ---: | ---: | ---: | ---: |
| `baseline` | 8/37 (21.6%) | 8/37 (21.6%) | - | 92.6 | 185.3 |
| `stride-2` | 9/37 (24.3%) | 9/37 (24.3%) | 1/29 | 93.5 | - |
| `stride-4` | 16/37 (43.2%) | 15/37 (40.5%) | 8/29 | 108.8 | 244.1 |
| `stride-8` | 33/37 (89.2%) | 28/37 (75.7%) | 25/29 | 267.3 | 654.1 |
| `budget-256` | 36/37 (97.3%) | 12/37 (32.4%) | 28/29 | 1395.8 | 4015.5 |
| `budget-512` | 36/37 (97.3%) | 12/37 (32.4%) | 28/29 | 2352.0 | 6184.6 |

**The late endgame is not saturated.** Only 4 of 37 late snapshots have no
arm that reaches a future placement, and only 1 of 37 has no arm that
discriminates at all. On the other 33 there is something for the rollout to
see; the shipped setting sees it on 8.

**It is a scan-order hole, not a budget shortfall.** This is the load-bearing
comparison, and it is the one that was not predicted:

* `stride-8` reaches a future placement on 28/37 late snapshots.
* `budget-512`, spending about 8.4x the attempts, reaches one on 12/37.
* 17 late snapshots are reached by `stride-8` and not by `budget-512`; only
  1 goes the other way.

Multiplying the attempt budget mostly buys more of the same dense infeasible
prefix. Spreading the same budget over the grid buys the feasible remainder.
`budget-N` still scores high on *non-degeneracy* because the extra attempts
eventually reach release candidates whose accumulated `P_rot`/`P_slide` break
the tie - discrimination with no reach. That is exactly why the two metrics
are reported separately: read on non-degeneracy alone, the budget arms look
like the better instrument, and they are not.

**Cost.** The per-step attempt cap is identical across `baseline` and the
stride arms. Total consumed attempts still rise (205.8 -> 257.7 mean at
stride 8) because branches that find a placement survive into the next
rollout step instead of terminating early - that is the signal being paid
for, not overhead. Wall clock does rise, because advancing the anchor
iterators past skipped positions is not free: `stride-4` costs +17% mean over
baseline (108.8 vs 92.6 ms), `stride-8` about 2.9x (267.3 ms, 654.1 max).
Against the enforce run's live shadow cost of 111.1 ms/step mean and 617.6 ms
max, `stride-4` is affordable at roughly the measured cost and `stride-8` is
not obviously so.

**Early band.** Steps 8-9 (11 snapshots) show baseline non-degeneracy 2/11
(18.2%), statistically indistinguishable from the late band's 21.6%. This
run therefore does **not** reproduce the live 57.5% / 1.2% split, and must
not be quoted as doing so: the snapshot pool starts at step 8, so its "early"
band is already late, and the Top-K is reconstructed rather than replayed.
The comparison that carries weight here is across arms within a band.

## What this does and does not license

Established:

* The step >= 10 rollout silence measured in run `30716558143` is
  substantially a coverage artefact of the anchor scan order, not a property
  of a full container.
* Stride recovers most of it at the same attempt budget and a modest wall
  clock cost, and recovers strictly more *reach* than raising the budget
  does.

Not established:

* That a strided rollout is a better live ordering. Non-degeneracy is not a
  score. The enforce rejection stands until a repeated same-run ablation says
  otherwise, and the b000-k15 first divergence is still undiagnosed.
* That the same hole exists in the live *policy* search. This measures the
  rollout's own bounded future search. The policy search is deadline-limited
  rather than attempt-limited and was not measured here.
* Any physical claim. A branch that "places" an item places it through the
  static proxy, with no PyBullet settle.

The next evidence worth having is the b000-k15 first-divergence
counterfactual re-run with `VISIBLE_POOL_ROLLOUT_STRIDE=4`, since the enforce
loss there was deterministic and repeatable, and this result says the value
it was enforcing on was measured through a hole.
