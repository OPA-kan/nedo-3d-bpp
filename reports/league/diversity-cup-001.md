# Diversity Cup 001 — 種馬成績表

Date: 2026-08-26. Run 32920552027 (12.5 min wall). Preregistration:
`reports/self-play-packing/research-cup-design.md` + ledger row 001.
Field: champion プリフヒバリ (pi2-pref-w6, plain) vs three mining studs
against the champion's own ensemble (learning run 32890092906). Six
virgin cells, primes 401-433, fork budget 12/episode.

## Research standings (what the cup is for)

| stud | novel board rate | disagreements | forks | strict pairs | pairs / M step-equiv |
|---|---|---|---|---|---|
| カベヅタイ (rule-edge) | 0.81 | 32 | 32 | **6** | **18519** |
| テイジュウシン (rule-lowcog) | 0.84 | 33 | 33 | **6** | 16129 |
| グリッドオー (rule-grid) | 0.81 | 29 | 29 | 3 | 9554 |

- **The studs live where the champion doesn't**: 81-84% of every
  stud-visited board fingerprint was unseen in the champion's runs of
  the same streams. The state-diversity premise holds.
- **Every disagreement was forked** (94/94): the budget of 12 per
  episode never bound — the harvest is disagreement-limited, not
  budget-limited, so raising the budget buys nothing at 6 cells.
- **Strict-dominance rate on forks: 16%** (15/94). The other 84% ended
  in terminal trade-offs — informative in itself: on stud-distribution
  boards, the champion's move and the stud's move usually lead to
  incomparable ends rather than clean wins.
- Side corpus: **15 preference pairs** banked
  (`side-corpus-pairs.jsonl` in the run artifact; not committed, not
  fed to training — that step needs its own preregistration).
- 種馬としての序列: カベヅタイとテイジュウシンが同数の6ペアで並び、
  収率(物理コスト当たり)ではカベヅタイが最良。グリッドオーは
  最少だが、格子盤面の被覆は他の2頭が作れない — 3頭とも残す。

## Race standings (spectator content)

All six pairings over the six cells (W-L-D-∥, first-named first):

| pairing | result |
|---|---|
| プリフヒバリ vs グリッドオー | 0-0-1-5 |
| プリフヒバリ vs テイジュウシン | 0-0-0-6 |
| プリフヒバリ vs カベヅタイ | 0-0-0-6 |
| グリッドオー vs テイジュウシン | 0-0-0-6 |
| グリッドオー vs カベヅタイ | 0-0-0-6 |
| テイジュウシン vs カベヅタイ | 0-0-0-6 |

Nobody beat anybody: 35 of 36 comparisons are incomparable. That is
the design speaking, not a bug — different inductive biases trade
heads (fill vs violations vs stability) instead of dominating, which
is exactly why race wins were never the cup's objective. **No stud
lost its stud value by losing races — none even lost a race.**

## Calibration of the planning numbers

The runbook estimated 40-90 strict pairs per cup; the actual is 15.
The gap is the strict rate (16% observed vs 20-40% assumed) and
disagreement volume (~5.2 per stud episode). Updated milestones at the
6-cell format: **~3 cups ≈ 45 pairs (probe), ~9 cups ≈ 130 pairs**
(the measured decisive-pair count that trained the first promoted
policy). If cadence matters, the lever is more cells per cup (the
course is a dispatch input), not a bigger fork budget — a 12-cell
course should roughly double the take; amend the design record before
changing course size.
