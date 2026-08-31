# A learned board value beats the teacher's own rollout, with no terminal

Date: 2026-08-31. Branch `work/terminal-rollout-oracle`.
Follows `reports/candidate-support/rollout-ceiling-20260830.md`.

## The mistake this corrects

The rollout-ceiling report established that the teacher stops when the
candidate generator runs dry -- 96.3% of Cup 009's terminal rollouts
ended `no_retained_candidate`, none exhausted the item stream -- and
then books the tail as zero. The obvious reading, and the one taken at
first, was that the fix is to make rollouts run further until they reach
a real terminal.

That reading was wrong, and treating it as a gate would have been a
serious defect: it would make learning wait on something that is
expensive, possibly unreachable (containers need not hold every item),
and **not required**.

The early stop is not the defect. An n-step estimate is valid at any n:

    V(s_t) ~= sum_{k<n} gamma^k r_{t+k} + gamma^n * V_theta(s_{t+n})

The defect is only that `V_theta(s_{t+n})` is pinned to 0, which is 2-4x
wrong. Bootstrapping fixes that directly and needs no terminal at all --
which is what a value function is *for*: the true value is unknown, so
it is approximated from experience under a local consistency condition
rather than from a global oracle label.

## Labels are free, and no episode reached a terminal

One episode labels every prefix state by telescoping, with r_t = the
volume of the item placed at t and gamma = 1:

    V(s_t) = sum of the volume placed from t onward

Collected over 24 course cells and two behaviour policies (rule-alpha
and rank-0 over the unioned provider), 48 trajectories, **988 labelled
states**. How they ended:

| termination | trajectories |
|---|---|
| `selected_action_failure` | 18 |
| `no_retained_candidate` | 16 |
| `rule_alpha_declined` | 14 |
| **`stream_exhausted`** | **0** |

**Not one trajectory packed the stream out, and every state still got a
label.** That is the point stated as a measurement.

## Result

A two-hidden-layer MLP on ten free geometric features, scored by
Spearman **within a step index** on **leave-one-cell-out** folds:

| step | boards | **learned V** | incumbent rollout | best single feature |
|---|---|---|---|---|
| 4 | 45 | **+0.586** | +0.365 | `mean_height` +0.489 |
| 8 | 44 | **+0.594** | +0.477 | `flat_cells` +0.472 |
| 12 | 39 | **+0.658** | +0.399 | `visible_pool_volume` +0.542 |

The learned value beats the teacher's ten-step physical rollout at every
step index, by +0.221 / +0.117 / +0.259 -- **at one network forward pass
against roughly ten physics steps.**

It also beats the best single feature at every step, so "the model won"
is not hiding "one raw feature would have won too". Every feature's own
score is in the artifact for that reason.

Three deliberate choices in the scoring. Ranking, not calibration: a
predictor wrong by a constant factor but correctly ordered is worth the
same inside a search. Within a step index: later boards trivially hold
less, so a pooled correlation would mostly measure episode progress and
`placed_count` would win it while saying nothing. And leave-one-CELL-out
rather than random: states inside one episode are near-duplicates, so a
random split would score memorisation.

## What this model is not

**The target is V^behaviour, not V\*.** It is the volume these two
policies go on to place, not the volume the board could hold. Regressing
on it approximates the behaviour policies and is bounded by them -- the
same trap this branch has been circling all along, one level over.

It is accepted here for one reason, stated plainly: the value it
replaces is the constant **0**, and V^behaviour beats 0 by two to four
times. It is a better bootstrap, not a good value function.

Escaping the bound needs a max -- over policies, or over candidate
continuations from the same prefix. `collect_value_targets.py` records
the behaviour policy on every row so several can be pooled and a
per-state max taken later; that is a change to the data, not to the
model.

## Caveats

- 39-45 boards per step index. A Spearman gap of +0.117 is not
  significant at that n; +0.259 is larger but on one seed.
- Ten hand-built features. The `depth_map` is (2, 64, 64) in every
  snapshot and a small CNN over it is untried.
- Both behaviour policies share a generator, so the state distribution
  is narrower than the board space.

## Reproduction

    python scripts/collect_value_targets.py \
      --config-dir <cells> --cases <names> \
      --policies rule-alpha rank0-union --output targets.json

    python scripts/train_board_value.py \
      --targets targets.json --steps 4 8 12 \
      --output report.json --model-dir reports/value/board-value-v1

The incumbent baseline comes from `scripts/probe_value_rankability.py`
on the same cells and the same ground truth.
