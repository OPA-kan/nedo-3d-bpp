# Diversity Cup 008 — 種馬成績表

Date: 2026-08-30. Run 33299902464 (episodes + standings both clean).
Hosted by `host-diversity-cup.yml` run 33299885236, the first cup on
the extended 401-799 prime pool (`58a164b`) — source 000 had been
exhausted at the old 401-599 window. Course: 000 587/593/599/601 ·
001 487/491, six virgin cells, fork budget 12/episode. Champion
プリフヒバリ (pi2-pref-w6, learning run 32890092906, unchanged since
Cup 001).

**First cup on rule-alpha@803fd6f** — the vendored actor carrying the
veto-fallback, wedge-reservation, floor-scoring and floor-map fixes
(`f54abbc`). Cups 006-007 raced 7908b09.

## Research standings

| stud | novel board rate | forks | strict pairs | strict rate | actor wins | champion wins |
|---|---|---|---|---|---|---|
| カベヅタイ (rule-edge) | 0.86 | 42 | **22** | 52% | 8 | 14 |
| テイジュウシン (rule-lowcog) | 0.79 | 41 | 17 | 41% | 7 | 10 |
| グリッドオー (rule-grid) | 0.88 | 40 | 16 | 40% | 3 | 13 |
| **rule-alpha** | 0.93 | 11 | 8 | **73%** | **7** | 1 |
| ジ・アーモンド | 0.96 | 22 | 8 | 36% | 3 | 5 |

- **Side corpus: 71 pairs** (83 in Cup 007). Verified independently by
  the dataset builder: 71 rows, 6 groups, 0 one-sided verdicts, label
  balance 28 actor / 43 champion.
- **rule-alpha took the cup's maximum terminal fill for the first
  time: 39.917 (23 placed)**, on single-empty-noshelf-000-599, beating
  ジ・アーモンド's 32.575 in the same cell. Every previous cup's
  maximum belonged to ジ・アーモンド. Not an all-time record —
  Cup 006's 41.857 still stands — but the first time the hand-coded
  actor has topped the field.
- rule-alpha keeps the best strict rate by a wide margin (73% vs
  40-52%) and a 7-1 record against the champion, on the fewest forks
  in the field (11). Its fork count halved from Cup 007's 22, which is
  most of why the cup total fell 83 → 71.
- ジ・アーモンド: 0/6 genuine termination for a seventh straight cup,
  strict rate down to 36%.

## Research averages (raw final_metrics, mean across 6 cells)

| horse | fill_score_proxy | placed_count | center_of_mass_z | genuine term. |
|---|---|---|---|---|
| プリフヒバリ (champion) | 9.91 | 9.67 | 0.732 | 6/6 |
| ジ・アーモンド | 27.91 | 26.17 | 0.693 | **0/6** |
| rule-alpha | 21.27 | 15.17 | **0.632** | **0/6** |
| グリッドオー | 11.07 | 11.50 | 0.663 | 6/6 |
| テイジュウシン | 9.51 | 9.67 | 0.682 | 6/6 |
| カベヅタイ | 10.23 | 10.50 | 0.669 | 6/6 |

genuine_termination read from each horse's own
`episodes[0].genuine_termination`. Terminations: champion, グリッドオー
and テイジュウシン `no_retained_candidate` x6; カベヅタイ x5 plus one
`no_safe_retained_candidate` (also genuine); ジ・アーモンド
`selected_action_failure` x5 + `max_steps` x1; rule-alpha
`selected_action_failure` x3 + `rule_alpha_declined` x3 — the
declines are now only half its endings, where in Cup 006 they were
5 of 6.

## Race standings

W-L-D-∥, first-named first; U = unmeasured (non-genuine episode):

| pairing | result |
|---|---|
| プリフヒバリ vs ジ・アーモンド | 0-0-0-0, U6 |
| プリフヒバリ vs rule-alpha | 0-0-0-0, U6 |
| プリフヒバリ vs グリッドオー | 0-0-0-6 |
| プリフヒバリ vs テイジュウシン | 0-1-0-5 |
| プリフヒバリ vs カベヅタイ | 0-0-0-6 |
| ジ・アーモンド vs rule-alpha | 0-0-0-0, U6 |
| ジ・アーモンド vs グリッドオー | 0-0-0-0, U6 |
| ジ・アーモンド vs テイジュウシン | 0-0-0-0, U6 |
| ジ・アーモンド vs カベヅタイ | 0-0-0-0, U6 |
| rule-alpha vs グリッドオー | 0-0-0-0, U6 |
| rule-alpha vs テイジュウシン | 0-0-0-0, U6 |
| rule-alpha vs カベヅタイ | 0-0-0-0, U6 |
| グリッドオー vs テイジュウシン | 0-0-0-6 |
| グリッドオー vs カベヅタイ | 1-0-1-4 |
| テイジュウシン vs カベヅタイ | 0-0-0-6 |

Among the four measured horses: 33/36 incomparable (92%, the highest
yet), 1 equal, 2 decisive. The dominance rule is now almost silent on
this field. Both non-genuine horses are unmeasured 6/6 as usual.

## Shun Long distillation of this cup's memory

Run 33302670965, first attempt, clean. 71 pairs, 6 groups, `passes=1`,
0 one-sided verdicts, label balance 28 actor / 43 champion. Status
stays `capability_only_not_league_evidence`; registry untouched.

| | before | after |
|---|---|---|
| leave-one-course-cell-out AUC | 0.419 | **0.630** |
| leave-one-course-cell-out log loss | 1.879 | **0.922** |
| same-corpus AUC | 0.419 | 0.723 |

**The largest held-out gain of any cup, and the first after-value
clearly above chance.** Across the four distilled cups:

| cup | pairs | held-out AUC | delta |
|---|---|---|---|
| 003 | 56 | 0.624 -> 0.478 | -0.146 |
| 006 | 78 | 0.590 -> 0.566 | -0.024 |
| 007 | 83 | 0.484 -> 0.504 | +0.020 |
| **008** | **71** | **0.419 -> 0.630** | **+0.211** |

Corpus size does not explain it -- 71 is *fewer* pairs than Cup 007's
83. The variable that changed is the corpus's composition: Cup 008 is
the first on rule-alpha@803fd6f, whose 8 pairs came at a 73% strict
rate with a 7-1 record against the champion.

Two cautions before this is read as a trend. The before-AUC is itself
the lowest of the four (0.419), so the champion started with the most
headroom on this corpus; before/after deltas across cups compare
different corpora and are not strictly commensurable. And it is one
cup. What is fair to say is that the best absolute held-out value so
far (0.630) came from the corpus with the strongest miner in it, not
from the largest corpus.

## The finding this cup exposed: candidate-support mismatch

The number worth keeping from Cup 008 is not a standing. It is
`candidate_support_misses`, which counts steps where the horse's own
executed action was **absent from the candidate provider's set**:

| horse | support misses / boards |
|---|---|
| **rule-alpha** | **89 / 89 = 100%** |
| ジ・アーモンド | 122 / 157 = 78% |
| グリッドオー | 0 / 64 |
| テイジュウシン | 0 / 53 |
| カベヅタイ | 0 / 58 |

The three rule studs re-rank the same generic candidate set, so they
never miss — and correspondingly never produce a move the generator
could not have proposed. The two horses that *do* produce novel play
are exactly the two playing outside that set, rule-alpha entirely so.

During mining this is invisible, because `add_exact_agent_candidate`
unions the exact actor action in so the fork can score it. At
inference the learned ranker chooses only among the provider's
candidates. So the pipeline currently teaches a preference over an
action the student cannot select:

    teacher plays outside the candidate set
      -> mining adds it as an exact candidate
      -> label says "this move wins"
      -> at inference the move is not in the choice set

Stated carefully: `support_hit=False` means the *exact* action is
absent, and does not by itself prove no near-equivalent neighbour was
available. But at 89/89 the train/inference mismatch is large however
it is read, and it sits **upstream of the ranker** — even a perfect
preference head cannot execute an action outside its own choice set.
This is a more likely explanation for the flat distillation results
(held-out AUC ≈ chance across Cups 003/006/007) than teacher quality.

Recorded as the reason Cup 009 is deliberately **not** hosted next:
the candidate set is being fixed first.

### A hypothesis that did not hold, recorded so it is not retried

Before this, the suspected bottleneck was rollout blindness. The
`candidate_stride` knob exists in `build_candidate_provider` and was
never threaded into `run_terminal_rollout_policy`, and
`reports/rollout-saturation/local-20260801` measured stride 1
discriminating on only 20.8% of snapshots against stride 8's 91.7%.
Threading it through and running a controlled A/B on
dual-empty-permute-000-607, seed 42, rule-alpha mining, changing only
the stride:

| | stride 1 | stride 8 |
|---|---|---|
| steps / placed / fill | 31 / 31 / 25.459 | 31 / 31 / 25.459 |
| disagreements / forks | 3 / 3 | 3 / 3 |
| strict pairs | 3 | **2** |
| fork step-equivalents | 132 | 132 |

Bit-identical episode; strict pairs went *down* by one. The 2026-08-01
measurement was of the `rollout_enforce` shadow — a different
mechanism on a different codebase — and does not transfer to Cup
mining. The flag is kept (default 1, behaviour unchanged) but it is
not the answer, and n=1 cell here besides.
