# Diversity Cup 005 — 種馬成績表

Date: 2026-08-30. Run 33291140628 completed successfully. The
one-click host preregistered six fresh cells (000: 499/503/509/521,
001: 449/457) before dispatch. Field: frozen champion プリフヒバリ
(`pi2-pref-w6`, learning run 32890092906), ジ・アーモンド, and the
three rule miners. Fork budget: 12 per episode. This Cup used the
current 4-head terminal dominance contract; surface variation is not a
verdict head.

## Research standings

| miner | novel board rate | disagreements | forks | strict pairs | actor/champion wins | pairs / M step-equiv |
|---|---:|---:|---:|---:|---:|---:|
| ジ・アーモンド | 0.959 | 28 | 28 | 20 | 12 / 8 | 46,729 |
| グリッドオー | 0.852 | 37 | 36 | 16 | 12 / 4 | 37,037 |
| テイジュウシン | 0.833 | 43 | 43 | **21** | 13 / 8 | 41,176 |
| カベヅタイ | 0.828 | 36 | 36 | 18 | 7 / 11 | **46,875** |

- Total: **144 disagreements, 143 physical forks, 75 strict pairs**
  from 1,754 fork physical-step-equivalents (**42,759 pairs/M**).
- Side corpus: **75** genuine-terminal preference pairs, retained in
  the run artifact and not fed directly to the season learner.
- Weighted novelty was 315/351 = **0.897**; the per-miner range was
  **0.83-0.96**, well above the 0.30 saturation stop.
- Event coverage across mining forks: soft-violation change **3**,
  priority-covered change **10**, priority-misroute change **0**.
  Post-shake stability was measurable for all 24 champion/rule-horse
  terminal outcomes; ジ・アーモンド remained unmeasured at 0/6 genuine
  terminations.

## Maximum terminal fill

- Overall: **38.8154308885**, ジ・アーモンド,
  `single-empty-noshelf-permute-000-509`, **25 placed**.
- Champion: **14.6756556565**, プリフヒバリ,
  `single-preloaded-permute-000-521`, 9 placed.
- Best rule stud: **15.0780788305**, グリッドオー,
  `dual-preloaded-dedicated-permute-000-499`, 22 placed.

The overall maximum is descriptive, not a clean race win:
ジ・アーモンド ended that episode with `selected_action_failure`, so it
did not receive terminal shake heads. It nevertheless supplied **20
strict physical teacher pairs**, the second-largest take in the field.

## Race table

W-L-D-I is written from the first-named horse's perspective; U means
unmeasured because ジ・アーモンド did not reach a genuine terminal.

| pairing | W-L-D-I / U |
|---|---:|
| プリフヒバリ vs ジ・アーモンド | 0-0-0-0 / U6 |
| プリフヒバリ vs グリッドオー | 0-0-0-6 |
| プリフヒバリ vs テイジュウシン | 0-1-0-5 |
| プリフヒバリ vs カベヅタイ | 1-0-0-5 |
| グリッドオー vs テイジュウシン | 0-0-0-6 |
| グリッドオー vs カベヅタイ | 0-0-1-5 |
| テイジュウシン vs カベヅタイ | 0-0-0-6 |

## Label-quality audit

All **75/75** stored winners reproduce under the current four heads:
fill gain (higher), soft violations (lower), priority covered (lower),
and priority misrouted (lower). Surface-only decisions: **0**. Pairs
whose largest oriented dominance margin was at most `1e-6`: **0**.
The smallest non-zero strict head margin was **0.0058968296** and the
median largest margin was **0.6588509639**. Every pair improved fill;
six also improved priority-covered count and one improved soft count.
No numerical-noise blocker was found. Same-fork rerun reproducibility
was not re-executed in this landing step; the persisted genuine-terminal
truth and winner IDs were audited without additional physics.
