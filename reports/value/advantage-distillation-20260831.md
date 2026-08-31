# Distilling with the PCT learning signal: the method transfers, the verdict does not

Date: 2026-08-31. Follows
`reports/value/pct-reference-reading-20260831.md`.

The reading note argued that the published RL 3D-BPP work cannot be
reproduced here because their environment is analytic and ours settles
every placement in PyBullet. This is the part that *can* be taken: the
**learning signal**, applied to episodes already on disk. No new physics
steps were run to build or train anything below.

## What changed

Architecture, features and artifact format are the incumbent's: the same
set transformer over the same `geometry` candidate tokens, saved as the
same ensemble. Only the loss differs.

| | incumbent | this |
|---|---|---|
| label | strict 4-head dominance between two candidates | the return the action actually led to |
| eligible rows | forks with two genuine terminals and a strict verdict | every decision with ≥2 safe candidates |
| rows from Cup 4/6/7/8 | 156 pairs (Cup 009) | **1166 decisions** |
| terminal required | yes | **no** |

The return telescopes, because `fill_score_proxy` is the same quantity
as PCT's `box_ratio`, paid per item:

    G_t = final_fill - fill_before(t)

so an episode that ended `no_retained_candidate` labels its prefix
states exactly as well as one that exhausted the stream. The tail
problem that blocked Cups 009 and 010 does not arise: there is nothing
to bootstrap.

The advantage subtracts a per-`(cell, step)` mean over the horses that
ran that cell — the standard time-dependent baseline, computed
empirically. Within a cell the stream is identical, so step *t* means
the same items have arrived. The fitted `V_theta` was deliberately NOT
used: it trained on these same states, and would put a model inside the
label.

Weights are `clip(exp(A/beta), 0, 20)` with `beta` the corpus advantage
standard deviation (7.363 fill points). The exponential form is what
makes it sound offline — a negative advantage shrinks that action's
weight toward zero instead of pushing probability onto some other action
whose return was never observed. With `w == 1` it degenerates to plain
behaviour cloning, which is the ablation below.

## Head to head, six cells, `permute-000-607` (held out of training)

Same stream, same everything, only the policy head swapped.
`champ-argmax` is the incumbent's own weights re-deployed as a plain
argmax, with its incumbent floor removed — the control that separates
"what it learned" from "how conservatively it acts".

| cell | champ | champ-argmax | advantage |
|---|---|---|---|
| dual-empty | 7.67 / 12 | 11.00 / 15 | **13.11 / 19** |
| single-empty-shelf | **13.51 / 10** | 13.51 / 10 | 6.80 / 6 |
| dual-preloaded-dedicated | **10.74 / 15** | 10.74 / 15 | 9.48 / 14 |
| dual-shelf-mixed | 8.19 / 13 | 8.19 / 13 | **13.95 / 19** |
| single-empty-noshelf | **10.87 / 9** | 9.76 / 8 | 10.87 / 9 |
| single-preloaded | 8.89 / 7 | 8.89 / 7 | **9.57 / 8** |
| **mean fill** | 9.980 | 10.349 | **10.631** |

Three wins, two losses, one identical trajectory. Paired over cells:

| comparison | mean difference | sd | t |
|---|---|---|---|
| advantage − champ | **+0.652** | 4.632 | **0.34** |
| advantage − champ-argmax | +0.282 | 4.134 | 0.17 |

**Not significant, and not close.** +6.5% mean fill is the headline
number and it should not be believed: the per-cell spread of the paired
difference is ±4.6 fill points, seven times the effect.

The `champ-argmax` control also earns its keep. On `dual-empty` the
incumbent floor cost the champion 3.3 fill points on its own — keeping
provider rank-0 unless clearly beaten is a property of the *preference*
objective, not of what it learned — while on three cells the floor never
bound at all and champion and argmax are bit-identical. More than half
of the advantage model's apparent margin over the shipped champion is
that deployment difference, not the training signal.

## The measurement finding, which outlasts the result

To detect a +0.65 fill-point effect at 80% power with a paired sd of
4.63 needs about **396 cells**. The Cup format is six.

This is not a claim about strict-pair counts, which are counts over many
forks and have their own resolution. It is specifically about **mean
fill over a six-cell course**, and it says that comparison cannot
resolve differences of the size any of today's changes produce. A cup
whose standings differ by a fill point is reporting noise.

## Retracted

An earlier framing in this session read an offline metric —
"shared-board pairs": decisions from an identical board where two horses
chose differently, scored by which action's realised return was higher —
as a model comparison, and reported behaviour cloning at 0.321,
advantage weighting at 0.371 and the shipped champion at 0.421.

**That metric is confounded and those numbers do not mean what was
said.** `G_t` is "this action *plus this horse's continuation*", and the
continuation dominates: `current-agent` wins 41 of the 41 pairs it
appears in, and a predictor that sees no board at all and only asks
"which horse is stronger on average" scores **0.643** on the same 140
pairs. A candidate-geometry model cannot see the horse, so it cannot
score well; the sub-chance results measure the confound. The claim that
"imitation learns the worse move" is withdrawn.

Only the *difference* between the three survives, all three carrying the
identical confound, and it is small.

## What stands

* The method transfers mechanically. 7.5x the training rows, no
  dominance rule, no terminal requirement, **zero new simulator steps**.
* Trained on that corpus, the resulting policy packs in the same range
  as the head nine cups of distillation produced. It is not better; it
  is also not worse, and it was free.
* The instrument, not the method, is now the binding constraint. Any
  next comparison of this size needs either far more cells or a
  lower-variance statistic than mean fill.

## Reproduction

    python scripts/build_advantage_policy_dataset.py \
      --episodes-root <cup4> --episodes-root <cup6> \
      --episodes-root <cup7> --episodes-root <cup8> \
      --output <dataset.json>

    python scripts/train_advantage_policy.py \
      --dataset <dataset.json> --report <report.json> \
      --model-dir <awr-model> --incumbent-model-dir reports/cup/model
    # add --uniform-weights for the behaviour-cloning ablation

    python scripts/run_terminal_rollout_policy.py \
      --config <cfg>/<scenario>.json --case m-<scenario> \
      --environment-seed 42 --attempt-budget 128 --top-k 3 \
      --rollout-top-k 3 --rollout-max-steps 40 --max-steps 40 \
      --policy learned --model-dir <awr-model|reports/cup/model> \
      --output-dir <out>
