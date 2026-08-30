# Diversity Cup 007 — 種馬成績表

Date: 2026-08-30. Run 33297401046 (episodes + standings both succeeded
cleanly). Dispatched via `host-diversity-cup.yml` (run 33297384852),
which resolved the champion run, drew six fresh never-used primes,
preregistered ledger row 007, and dispatched `diversity-cup.yml`.
Field: champion プリフヒバリ (pi2-pref-w6, plain, learning run
32890092906, unchanged since Cup 001), ジ・アーモンド (current-agent),
rule-alpha, and three mining studs, forking against the champion's own
ensemble. Six virgin cells, primes 563/569/571/577 (000) and 467/479
(001), fork budget 12/episode.

**Version boundary:** this cup was dispatched from `3b95cfc`, so it
still raced **rule-alpha@7908b09** — the same old actor as Cup 006.
The `803fd6f` vendor landed in `f54abbc`, after dispatch. Cup 008 is
the first cup on the newer actor.

First cup collected entirely under the one-horse-race fix (`ce6cb2b`,
an ancestor of `3b95cfc` — verified). **Zero one-sided verdicts** this
cup, and the analyzer, the dataset builder and the pairs jsonl all
independently agree at 83.

## Research standings (what the cup is for)

| stud | novel board rate | disagreements | forks | strict pairs | strict rate | pairs / M step-equiv |
|---|---|---|---|---|---|---|
| カベヅタイ (rule-edge) | 0.85 | 40 | 40 | **23** | 58% | 47917 |
| グリッドオー (rule-grid) | 0.87 | 37 | 37 | 21 | 57% | 39474 |
| rule-alpha | 0.95 | 22 | 22 | 18 | **82%** | **78261** |
| テイジュウシン (rule-lowcog) | 0.78 | 31 | 31 | 18 | 58% | 47368 |
| ジ・アーモンド | 0.93 | 14 | 14 | 3 | 21% | 12605 |

- **Side corpus: 83 preference pairs**, the largest cup yet
  (53/56/75/78 in Cups 004/003/005/006). `side-corpus-pairs.jsonl` in
  the run artifact, not committed, not fed to training — same boundary
  as every prior cup.
- **rule-alpha is now the most efficient miner in the field by a wide
  margin**: 18 strict pairs from only 22 forks (82% strict rate, vs
  57-58% for the three rule studs) at 78261 pairs per million
  step-equivalents, roughly 1.6x the next best. It also *wins* most of
  what it mines — 12 actor wins to 6 champion wins, the only horse
  with a winning record against the champion this cup. In Cup 006 it
  was 6 actor / 11 champion, so the direction flipped. Note this is
  still the **old** 7908b09 actor.
- **ジ・アーモンド collapsed as a miner**: 3 strict pairs from 14
  forks (21%), down from 7/17 in Cup 006 and 11/19 in Cup 003. Its
  disagreement volume keeps shrinking (19 → 17 → 14 forks) and its
  strict rate with it. It now contributes 3 of the cup's 83 pairs
  (3.6%). Six straight cups at 0/6 genuine termination.
- Maximum terminal fill: **ジ・アーモンド, 36.069 (fill_score_proxy),
  23 placed**, single-empty-noshelf cell, again a non-genuine
  `selected_action_failure`. rule-alpha's best (27.054, 16 placed) is
  again second, ahead of every rule stud and the champion.

## Research averages (raw final_metrics, mean across 6 cells)

| horse | fill_score_proxy | placed_count | priority covered | center_of_mass_z | genuine term. |
|---|---|---|---|---|---|
| プリフヒバリ (champion) | 10.39 | 11.17 | 0.33 | 0.686 | 6/6 |
| ジ・アーモンド | 28.19 | 26.50 | 0.67 | 0.673 | **0/6** |
| rule-alpha | 23.55 | 21.67 | 0.00 | **0.561** | **0/6** |
| グリッドオー | 10.51 | 11.33 | 0.17 | 0.698 | 6/6 |
| テイジュウシン | 10.44 | 10.67 | 0.00 | 0.647 | 6/6 |
| カベヅタイ | 10.46 | 11.17 | 0.00 | 0.691 | 6/6 |

genuine_termination is read from each horse's own
`episodes[0].genuine_termination`, not inferred from the termination
string. Terminations: champion and all three rule studs
`no_retained_candidate` x6 (all genuine); ジ・アーモンド
`selected_action_failure` x4 + `max_steps` x2; rule-alpha
`rule_alpha_declined` x5 + `selected_action_failure` x1.

As in every prior cup, the two non-genuine horses' fill/placed
averages are inflated by running more steps before stopping — treat as
descriptive, not a quality ranking. Worth noting separately:
rule-alpha carries the **lowest centre of mass in the field** (0.561
vs 0.647-0.698 for everyone else) while placing roughly twice as many
items as the rule studs, which is the one average here that is not
just a step-count artefact. post_shake_* is omitted; neither
non-genuine horse has a genuine-termination sample this cup.

## Race standings (spectator content)

W-L-D-∥ (challenger wins–member wins–equal–incomparable), first-named
first; U = unmeasured (non-genuine current-agent/rule-alpha episode):

| pairing | result |
|---|---|
| プリフヒバリ vs ジ・アーモンド | 0-0-0-0, U6 |
| プリフヒバリ vs rule-alpha | 0-0-0-0, U6 |
| プリフヒバリ vs グリッドオー | 0-0-0-6 |
| プリフヒバリ vs テイジュウシン | 0-0-1-5 |
| プリフヒバリ vs カベヅタイ | 1-0-1-4 |
| ジ・アーモンド vs rule-alpha | 0-0-0-0, U6 |
| ジ・アーモンド vs グリッドオー | 0-0-0-0, U6 |
| ジ・アーモンド vs テイジュウシン | 0-0-0-0, U6 |
| ジ・アーモンド vs カベヅタイ | 0-0-0-0, U6 |
| rule-alpha vs グリッドオー | 0-0-0-0, U6 |
| rule-alpha vs テイジュウシン | 0-0-0-0, U6 |
| rule-alpha vs カベヅタイ | 0-0-0-0, U6 |
| グリッドオー vs テイジュウシン | 0-1-0-5 |
| グリッドオー vs カベヅタイ | 0-1-0-5 |
| テイジュウシン vs カベヅタイ | 1-0-1-4 |

Both ジ・アーモンド and rule-alpha are entirely unmeasured (6 of 6
each) — no genuine termination means no shake test means no
`post_shake_*` heads for `league.episode_outcome()` to compare. That
is now the standing situation for both, and it is the one thing that
keeps the cup's two strongest fill performers out of every race table.

Among the champion and three rule studs (fully measured, 6 pairings x
6 cells = 36): 29/36 incomparable (81%), 3 equal, 4 decisive —
テイジュウシン 2, プリフヒバリ 1, カベヅタイ 1. As always, race wins
decide nothing; no promotion or gating logic reads this table.

## Shun Long distillation of this cup's memory

Run 33299265660 (on `071e9b9`), first attempt, clean. 83 pairs, 6
course-cell groups, `passes=1`, base model 32890092906, 0 one-sided
verdicts skipped. Label balance 45 actor wins / 38 champion wins — the
most actor-favourable corpus so far. Status stays
`capability_only_not_league_evidence`: no match, no promotion, the
registry is untouched, so プリフヒバリ remains champion.

| | before | after |
|---|---|---|
| leave-one-course-cell-out AUC | 0.484 | **0.504** |
| leave-one-course-cell-out log loss | 1.958 | **0.887** |
| same-corpus AUC | 0.484 | 0.696 |

**This is the first cup whose distillation does not degrade held-out
ranking.** Cup 003 went 0.624 → 0.478 (below chance) on 56 pairs and
Cup 006 went 0.590 → 0.566 on 78; here 0.484 → 0.504 — a small
improvement rather than a loss, and the first time the after-value
lands above chance. Held-out log loss more than halves (1.958 →
0.887), continuing Cup 006's calibration gain.

Read it carefully though: the *before* AUC is itself the lowest of the
three (0.484 — the frozen champion is worse than chance at ranking
this cup's pairs before any memory is applied), so the after-value of
0.504 is still only chance-level ranking. The honest summary is that
the memory now stops hurting and fixes calibration, not that it ranks
well. Three cups is also three points: 56 → 78 → 83 pairs with
held-out AUC deltas of −0.146, −0.024, +0.020 is consistent with
"corpus size cures the overfit" but does not establish it.

## Notes

Champion, dominance rule and course format unchanged. The registry is
untouched (Cup 006's distillation stayed
`capability_only_not_league_evidence`), so プリフヒバリ remains
champion for Cup 008. `reports/league/season/state.json` still shows
season stage "collecting" (wave 8, round 4) with no run id recorded
and no season workflow in flight — not touched here, not blocking
cup hosting.
