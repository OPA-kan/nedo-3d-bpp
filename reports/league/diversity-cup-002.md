# Diversity Cup 002 — 種馬成績表

Date: 2026-08-26. Episodes run 32925104549 (episodes succeeded; the
`standings` job in that run crashed — see "Standings recovery" below).
Preregistration: `reports/self-play-packing/diversity-cup-design.md`
(Cup 002+ amendment: exact current-agent anchor) + ledger row 002.
Field: champion プリフヒバリ (pi2-pref-w6, plain), ジ・アーモンド
(ジ系列, the shipped `agent/agent.py::Agent.policy` run as
`current-agent` — named after this cup, its first outing), and three
mining studs, all forking against the champion's own ensemble
(learning run 32890092906). Six virgin cells, primes 401-443, fork
budget 12/episode.

**Correction (2026-08-26, same day):** this cup's episodes were
auto-dispatched at 03:04:57Z on commit `88fc535`, which still carried
the *original 5-head* `DOMINANCE_HEADS` (surface_total_variation
included). The surface-exclusion fix (`1087667`) landed at 05:27:29Z,
about two hours after these episodes ran — it could only affect the
*standings reconstruction* below (which uses the unrelated, always
surface-free `league.py` `LEAGUE_HEADS` for race tables), not the
strict-pairs mining that happens live inside each episode via
`vector_search_root`. So despite what an earlier version of this file
said, **Cup 002's 17 strict pairs were mined under the OLD 5-head
rule**, same as Cup 001. Cup 003 is the first cup run entirely under
the 4-head rule; see `reports/league/diversity-cup-003.md` for the
yield comparison this makes possible (17 -> 56 pairs, same 6-cell
format, same champion).

## Standings recovery

`scripts/analyze_diversity_cup.py` crashed in the original run:
`league.episode_outcome()` requires every `LEAGUE_HEADS` metric,
including the post-shake heads, which only exist for a genuine
termination. `current-agent` always executes its own action —
including a physically rejected one — so it can legitimately end
non-genuine, and did: 5 of its 6 episodes ended `max_steps` or
`selected_action_failure`, never reaching the shake test. The episode
jobs themselves all succeeded (the six cells' rollout artifacts are
complete and deterministic under seed 42); only the final scoring
step failed. `pairwise_tables()` now catches that `ValueError` and
records the pairing as `unmeasured` for that cell instead of failing
the whole report (fix landed in this same push). Standings below were
recomputed locally from run 32925104549's own uploaded episode
artifacts — no re-run of the field was needed or performed.

## Research standings (what the cup is for)

| stud | novel board rate | disagreements | forks | strict pairs | pairs / M step-equiv |
|---|---|---|---|---|---|
| グリッドオー (rule-grid) | 0.84 | 34 | 34 | **7** | **16129** |
| カベヅタイ (rule-edge) | 0.82 | 37 | 37 | **7** | 14644 |
| テイジュウシン (rule-lowcog) | 0.85 | 27 | 27 | 3 | 10638 |
| ジ・アーモンド (current-agent) | 0.95 | 19 | 19 | 0 | 0 |

- **State diversity holds again**: 82-95% novel boards across all four
  actors, ジ・アーモンド highest of all (0.95) — the shipped
  hand-coded agent visits states even further from the champion's
  distribution than the rule studs do.
- **ジ・アーモンド mined nothing decisive** (0/19 forks strict): every
  disagreement against the champion ensemble ended tied or
  incomparable at genuine terminal. It still contributes state
  diversity, just not preference-pair yield, this cup.
- Side corpus: **17 preference pairs** banked (7 grid + 7 edge + 3
  lowcog; `side-corpus-pairs.jsonl` in the run artifact — not
  committed, not fed to training, same boundary as Cup 001).
- **ジ・アーモンド's own robustness under this harness is the notable
  result**: it reached genuine termination in only 1 of 6 cells (the
  other 5 hit the 40-step cap or a physically rejected action first),
  and missed the physically-screened safe-candidate support set on
  132 of its 164 recorded steps (80%). This is diagnostic of the
  shipped agent under a harness that never substitutes its action for
  a safe one — not a claim about the competition score, and not a
  claim the rule studs or champion share (their support-miss counts
  are 0).
- ジ・アーモンド still set the cup's single best terminal fill
  (`fill_score_proxy` 35.21, 22 placed, single-empty-noshelf cell) —
  the one cell it did reach genuine termination in.

## Race standings (spectator content)

W-L-D-∥ (challenger wins–member wins–equal–incomparable), first-named
first; U = cells where the pairing was unmeasured (a non-genuine
ジ・アーモンド episode with no post-shake heads):

| pairing | result |
|---|---|
| プリフヒバリ vs ジ・アーモンド | 0-0-0-1, U5 |
| プリフヒバリ vs グリッドオー | 0-1-0-5 |
| プリフヒバリ vs テイジュウシン | 1-1-0-4 |
| プリフヒバリ vs カベヅタイ | 0-1-0-5 |
| ジ・アーモンド vs グリッドオー | 0-0-0-1, U5 |
| ジ・アーモンド vs テイジュウシン | 0-0-0-1, U5 |
| ジ・アーモンド vs カベヅタイ | 0-0-0-1, U5 |
| グリッドオー vs テイジュウシン | 0-2-0-4 |
| グリッドオー vs カベヅタイ | 1-2-0-3 |
| テイジュウシン vs カベヅタイ | 2-0-0-4 |

ジ・アーモンド's races are mostly unmeasured (5 of 6 cells each), not
losses — the harness has no result to report there, and that absence
is itself the finding above, not hidden inside a 0-0-0-6 line.
Among the champion and the three rule studs (all fully measured,
6 pairings × 6 cells), races stay mostly incomparable (25 of 36,
69%). Of the 11 decisive results, the champion won only 1 (against
テイジュウシン) and lost 10 — the rule studs collectively out-raced
プリフヒバリ this cup (wins: テイジュウシン 5, カベヅタイ 3,
グリッドオー 2, プリフヒバリ 1). Race wins were never the cup's
objective (see Cup 001), so this is descriptive, not a challenge
signal — no promotion or gating logic reads this table.

## Calibration of the planning numbers

17 strict pairs from 6 cells (vs 15 for Cup 001), still tracking the
runbook's 40-90/cup estimate at the low end when ジ・アーモンド (which
mined 0) is included. Cup 001's cadence estimate stands: 12-cell
courses roughly double the take if hosting cadence becomes the
constraint.
