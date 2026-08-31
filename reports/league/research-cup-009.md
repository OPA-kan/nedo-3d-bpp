# Research Cup 009 — 種馬成績表

Date: 2026-08-30. Run 33307098778 (episodes + standings both clean).
Hosted by `host-diversity-cup.yml` run 33307086613. **The first cup
under the Research Cup name** (renamed from Diversity Cup at this cup;
numbering, ledger, prime pool and every frozen rule continue unbroken).
Course: 000 607/613/617/619 · 001 499/503, six virgin cells.
Champion プリフヒバリ (pi2-pref-w6, learning run 32890092906,
unchanged since Cup 001).

**First cup with the rule-alpha candidate union.** rule-alpha alone ran
`--union-rule-alpha --rule-alpha-union-limit 4` with its own fork budget
of 40; the other five horses ran byte-identical commands to Cup 008, so
the corpus shift is attributable to one horse.

## Research standings

| stud | novel board rate | forks | strict pairs | strict rate | actor wins | champion wins | support misses |
|---|---|---|---|---|---|---|---|
| **rule-alpha** | 0.95 | 97 | **87** | **90%** | **67** | 20 | **0 / 126** |
| rule-lowcog | 0.76 | 38 | 24 | 63% | 12 | 12 | 0 / 58 |
| rule-edge | 0.81 | 31 | 18 | 58% | 7 | 11 | 0 / 53 |
| rule-grid | 0.83 | 32 | 16 | 50% | 10 | 6 | 0 / 65 |
| ジ・アーモンド | 0.95 | 20 | 11 | 55% | 4 | 7 | **143 / 174 = 82%** |

- **Side corpus: 156 pairs**, the largest yet and roughly double Cup
  008's 71. 87 of them (56%) are rule-alpha's.
- **The candidate-support mismatch is gone for rule-alpha: 89/89 = 100%
  misses in Cup 008, 0 of 126 boards here.** The 1-cell A/B reproduced
  across six unseen cells.
- rule-alpha's disagreements went 11 -> 97 and strict pairs 8 -> 87.
  Its fork budget of 40 was never binding (97 forks over 6 cells, mean
  16 per cell against a cap of 40), so all 97 disagreements were
  settled; strict rate 90%.
- rule-alpha took the cup's maximum terminal fill for a second straight
  cup: 34.698 (22 placed) on single-empty-shelf-permute-001-503.
- ジ・アーモンド's 82% miss rate is untouched, which is the expected
  result: the union is rule-alpha's family only. `C_other-experts`
  remains unbuilt.

## Shun Long distillation of this cup's memory

Run 33317423827, first attempt, clean. 156 pairs, 6 groups, `passes=1`.
Status stays `capability_only_not_league_evidence`; registry untouched.

| | before | after |
|---|---|---|
| leave-one-course-cell-out AUC | 0.6125 | **0.6130** |
| leave-one-course-cell-out log loss | 1.861 | **0.818** |
| same-corpus AUC | 0.6125 | 0.672 |
| held-out accuracy @0.5 | 0.378 | 0.596 |
| mean predicted probability | 0.154 | 0.523 |

**The largest corpus ever assembled produced no held-out ranking gain
at all** (+0.0005 AUC). Across the five distilled cups:

| cup | pairs | held-out AUC | delta |
|---|---|---|---|
| 003 | 56 | 0.624 -> 0.478 | -0.146 |
| 006 | 78 | 0.590 -> 0.566 | -0.024 |
| 007 | 83 | 0.484 -> 0.504 | +0.020 |
| 008 | 71 | 0.419 -> 0.630 | +0.211 |
| **009** | **156** | 0.613 -> 0.613 | **+0.001** |

The log-loss halving and the accuracy jump from 0.378 to 0.596 are
**bias correction, not ranking skill**: mean predicted probability moved
0.154 -> 0.523, and 100 of the 156 pairs are actor wins, so shifting the
prior alone buys that accuracy. Doubling the corpus did not help.

Two cautions on the corpus itself. 87 of 156 pairs come from one horse,
which won 67-20, so a model can satisfy much of it by learning "prefer
whatever looks like rule-alpha" or simply "bet on the actor". And the
label balance (100/56) is the most skewed of any cup.

## What this cup exposed

The distillation result is the fifth cup in a row with no held-out
ranking improvement, on the largest corpus yet, which says the
bottleneck is not corpus size. Investigating the teacher instead found
that across the 108 terminal rollouts inside this cup's mining forks on
`dual-empty-permute-000-613`, **zero ended by exhausting the item
stream**: 96.3% ended `no_retained_candidate`, which
`GENUINE_TERMINATIONS` counts as a finished board.

So every verdict in Cups 001-009 was computed by a continuation that
stopped after about nine or ten placements, on boards where rule-alpha
places up to 39. Full measurement and the fix in
`reports/candidate-support/rollout-ceiling-20260830.md`; the teacher is
widened from Cup 010, which is why Cup 010's standings are not
comparable to these.
