# Diversity Cup 004 — 種馬成績表

Date: 2026-08-26. Run 32947834246 (episodes + standings both succeeded
cleanly). Its GitHub Actions run title mistakenly reads "Diversity Cup
003" — a leftover of the ledger-parsing bug fixed in `d681aaa` (a
nickname text in the `cup` column broke `next_cup_id()`'s regex on the
dispatch that drew this cup's course). The title is cosmetic only: the
course (primes 467/479/487/491/439/443) is genuinely fresh and never
reused, and the ledger row is correctly numbered 004. Dispatched via
`host-diversity-cup.yml`, which resolved the champion run, drew six
fresh never-used primes, preregistered ledger row 004, and dispatched
`diversity-cup.yml`. Field: champion プリフヒバリ (pi2-pref-w6, plain,
learning run 32890092906, same champion as Cup 003), ジ・アーモンド
(current-agent), and three mining studs, forking against the
champion's own ensemble. Six virgin cells, primes 439/443/467/479/487/
491, fork budget 12/episode.

Second cup run entirely under the 4-head dominance rule (Cup 003 was
the first).

## Research standings (what the cup is for)

| stud | novel board rate | disagreements | forks | strict pairs | pairs / M step-equiv |
|---|---|---|---|---|---|
| グリッドオー (rule-grid) | 0.89 | 39 | 39 | **18** | 33835 |
| カベヅタイ (rule-edge) | 0.85 | 34 | 34 | 15 | 37129 |
| テイジュウシン (rule-lowcog) | 0.81 | 28 | 28 | 14 | **48951** |
| ジ・アーモンド | 0.95 | 15 | 15 | 6 | 28846 |

- **Strict pairs: 53 this cup** (vs 56 in Cup 003) — essentially flat
  at the new post-fix rate; the three rule studs alone stayed roughly
  the same size (17->18, 16->15, 12->14) but **ジ・アーモンド's strict
  pairs nearly halved: 11 -> 6**, on fewer disagreements too (19 -> 15
  forks). Its raw disagreement volume with the champion is shrinking,
  not just its strict-win rate.
- Side corpus: **53 preference pairs** banked this cup — `side-corpus-pairs.jsonl`
  in the run artifact, not committed, not fed to training (same
  boundary as Cups 001-003).
- **ジ・アーモンド's genuine termination stayed at 0/6** — same as
  Cup 003, worse than Cup 002's 1/6. All six of its episodes ended
  `selected_action_failure` (5) or `max_steps` (1), never
  `no_retained_candidate` (the genuine-terminal condition every other
  horse hit in all 6 cells this cup, confirmed from each horse's own
  `episodes[0].genuine_termination` in the per-cell manifests, not
  guessed from the termination string — `no_retained_candidate` is
  itself a genuine terminal, unlike `selected_action_failure`/
  `max_steps`). Candidate-support misses: 135/164 steps (82%, in line
  with Cup 002's 80% and Cup 003's 84%) — three cups running with no
  sign of self-correction.
- ジ・アーモンド again set the cup's best terminal fill
  (`fill_score_proxy` 36.54, 22 placed, single-empty-noshelf cell,
  again non-genuine `selected_action_failure`) — the same pattern as
  Cups 002-003: its uncapped play occasionally reaches far higher raw
  fill than any of the other four horses, at the cost of never
  settling cleanly enough to be measured against them.

## Research averages (raw final_metrics, mean across 6 cells)

| horse | fill_score_proxy | placed_count | priority covered | center_of_mass_z | genuine term. |
|---|---|---|---|---|---|
| プリフヒバリ (champion) | 9.98 | 10.00 | 0.00 | 0.712 | 6/6 |
| ジ・アーモンド | 29.80 | 27.33 | 0.33 | 0.651 | **0/6** |
| グリッドオー | 9.46 | 10.17 | 0.00 | 0.800 | 6/6 |
| テイジュウシン | 8.65 | 8.67 | 0.00 | 0.704 | 6/6 |
| カベヅタイ | 8.81 | 10.00 | 0.17 | 0.832 | 6/6 |

As in Cups 002-003: ジ・アーモンド's fill/placed averages are inflated
by running far more steps before stopping (nobody else averages
anywhere near 27 placed at 6 cells), not by placing more efficiently
per step — descriptive, not a quality ranking. post_shake_* is omitted
here; ジ・アーモンド has zero genuine-termination samples this cup, so
no post-shake heads exist for it to compare.

## Race standings (spectator content)

W-L-D-∥ (challenger wins–member wins–equal–incomparable), first-named
first; U = unmeasured (non-genuine ジ・アーモンド episode):

| pairing | result |
|---|---|
| プリフヒバリ vs ジ・アーモンド | 0-0-0-0, U6 |
| プリフヒバリ vs グリッドオー | 0-1-1-4 |
| プリフヒバリ vs テイジュウシン | 1-1-0-4 |
| プリフヒバリ vs カベヅタイ | 0-1-1-4 |
| ジ・アーモンド vs グリッドオー | 0-0-0-0, U6 |
| ジ・アーモンド vs テイジュウシン | 0-0-0-0, U6 |
| ジ・アーモンド vs カベヅタイ | 0-0-0-0, U6 |
| グリッドオー vs テイジュウシン | 2-0-0-4 |
| グリッドオー vs カベヅタイ | 1-1-1-3 |
| テイジュウシン vs カベヅタイ | 0-1-1-4 |

ジ・アーモンド's races are entirely unmeasured this cup (6 of 6, same
as Cup 003) for the same reason as above: no genuine termination means
no shake test means no `post_shake_*` heads for
`league.episode_outcome()` to compare.

Among the champion and three rule studs (fully measured, 6 pairings x
6 cells = 36): 23/36 incomparable (64%, roughly Cup 003's 81% pulled
back toward Cup 002's rate — three cups is still not enough to call a
trend). Of 9 decisive results plus 4 equal, グリッドオー picked up 4
wins (2 vs テイジュウシン, 1 vs カベヅタイ, 1 as champion's opponent),
カベヅタイ 3, the champion and テイジュウシン 1 each. As always, race
wins decide nothing — no promotion or gating logic reads this table.

## Notes

This cup's episodes ran on the freshly-landed shared-prefix env
checkpoint infra (`scripts/env_checkpoint.py`, commit `804f3aa`) only
in the sense that the code was on the branch by run time — the flag is
`--shared-prefix-env`, off by default, and this cup's dispatch did not
opt in, so no result here should differ from a pre-`804f3aa` run of
the same course/seeds.
