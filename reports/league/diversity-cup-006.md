# Diversity Cup 006 — 種馬成績表

Date: 2026-08-30. Run 33294741331 (episodes + standings both succeeded
cleanly). Dispatched via `host-diversity-cup.yml` (run 33294726696),
which resolved the champion run, drew six fresh never-used primes,
preregistered ledger row 006, and dispatched `diversity-cup.yml`.
Field: champion プリフヒバリ (pi2-pref-w6, plain, learning run
32890092906, same champion since Cup 001), ジ・アーモンド
(current-agent), the new exact stateful **rule-alpha** actor (first
Cup appearance), and three mining studs, forking against the
champion's own ensemble. Six virgin cells, primes 523/541/547/557
(000) and 461/463 (001), fork budget 12/episode.

Third cup run entirely under the 4-head dominance rule.

## Research standings (what the cup is for)

| stud | novel board rate | disagreements | forks | strict pairs | pairs / M step-equiv |
|---|---|---|---|---|---|
| テイジュウシン (rule-lowcog) | 0.82 | 36 | 36 | **23** | **58974** |
| カベヅタイ (rule-edge) | 0.87 | 37 | 37 | 17 | 42289 |
| rule-alpha | 0.94 | 17 | 17 | 17 | 41872 |
| グリッドオー (rule-grid) | 0.83 | 32 | 32 | 15 | 43103 |
| ジ・アーモンド | 0.96 | 17 | 17 | 7 | 38889 |

- **Side corpus: 79 preference pairs banked this cup** — the largest
  cup yet (vs 53/56/75 in Cups 003-005). `side-corpus-pairs.jsonl` in
  the run artifact, not committed, not fed to training (same boundary
  as every prior cup).
- **rule-alpha's debut: 0/6 genuine termination**, matching
  ジ・アーモンド's now-familiar pattern. Its terminations were
  `rule_alpha_declined` (5/6) and one `selected_action_failure` — a
  new termination reason not seen from any other horse, worth
  tracking separately from ジ・アーモンド's failure mode rather than
  lumping them together. candidate_support_misses: 105/105 boards
  (100%) — every one of its steps missed candidate support, markedly
  worse than ジ・アーモンド's 142/173 (82%) this cup.
- **ジ・アーモンド's genuine termination stayed at 0/6** for a fifth
  straight cup (all six episodes `selected_action_failure` this time,
  no `max_steps` outlier). Strict pairs ticked up slightly (6 -> 7)
  but stayed far below Cups 003/005's 11 and its own share of the
  cup's total pairs keeps shrinking (7/79 = 9%, vs 6/53 = 11% in Cup
  004) as the rule studs and rule-alpha now supply most of the yield.
- Maximum terminal fill this cup: **ジ・アーモンド, 41.86
  (fill_score_proxy), 26 placed**, single-empty-noshelf cell, again a
  non-genuine `selected_action_failure` episode — same pattern as
  every prior cup (uncapped play reaches higher raw fill than any
  other horse, at the cost of never settling cleanly). rule-alpha's
  own best (29.80, 19 placed) is the second-highest in the field,
  ahead of every rule stud and the champion.

## Research averages (raw final_metrics, mean across 6 cells)

| horse | fill_score_proxy | placed_count | priority covered | center_of_mass_z | genuine term. |
|---|---|---|---|---|---|
| プリフヒバリ (champion) | 9.71 | 9.67 | 0.00 | 0.768 | 6/6 |
| ジ・アーモンド | 31.04 | 28.67 | 0.33 | 0.683 | **0/6** |
| rule-alpha | 20.66 | 18.17 | 0.00 | 0.518 | **0/6** |
| グリッドオー | 9.22 | 9.67 | 0.00 | 0.887 | 6/6 |
| テイジュウシン | 10.03 | 10.17 | 0.00 | 0.724 | 6/6 |
| カベヅタイ | 9.49 | 10.00 | 0.00 | 0.852 | 6/6 |

genuine_termination is read directly from each horse's own
`episodes[0].genuine_termination` in the per-cell manifests, not
guessed from the termination string (`no_retained_candidate` is
itself a genuine terminal, unlike `selected_action_failure`,
`max_steps`, or the new `rule_alpha_declined`). As in every prior cup:
ジ・アーモンド's and rule-alpha's fill/placed averages are inflated by
running more steps before stopping, not by placing more efficiently —
descriptive, not a quality ranking. post_shake_* is omitted; neither
non-genuine horse has any genuine-termination sample this cup to
compute it from.

## Race standings (spectator content)

W-L-D-∥ (challenger wins–member wins–equal–incomparable), first-named
first; U = unmeasured (non-genuine current-agent/rule-alpha episode):

| pairing | result |
|---|---|
| プリフヒバリ vs ジ・アーモンド | 0-0-0-0, U6 |
| プリフヒバリ vs rule-alpha | 0-0-0-0, U6 |
| プリフヒバリ vs グリッドオー | 0-0-2-4 |
| プリフヒバリ vs テイジュウシン | 0-0-0-6 |
| プリフヒバリ vs カベヅタイ | 0-2-1-3 |
| ジ・アーモンド vs rule-alpha | 0-0-0-0, U6 |
| ジ・アーモンド vs グリッドオー | 0-0-0-0, U6 |
| ジ・アーモンド vs テイジュウシン | 0-0-0-0, U6 |
| ジ・アーモンド vs カベヅタイ | 0-0-0-0, U6 |
| rule-alpha vs グリッドオー | 0-0-0-0, U6 |
| rule-alpha vs テイジュウシン | 0-0-0-0, U6 |
| rule-alpha vs カベヅタイ | 0-0-0-0, U6 |
| グリッドオー vs テイジュウシン | 0-0-0-6 |
| グリッドオー vs カベヅタイ | 0-0-1-5 |
| テイジュウシン vs カベヅタイ | 0-0-0-6 |

Both ジ・アーモンド's and rule-alpha's races are entirely unmeasured
this cup (6 of 6 each) — no genuine termination means no shake test
means no `post_shake_*` heads for `league.episode_outcome()` to
compare.

Among the champion and three rule studs (fully measured, 6 pairings x
6 cells = 36): 30/36 incomparable (83%, back up near Cup 003's 81%
after Cup 004's 64%). Only 2 decisive results this cup (both カベヅタイ
over the champion), plus 4 equal; every other measured pairing came
back incomparable, including all 6 グリッドオー-vs-テイジュウシン and
all 6 テイジュウシン-vs-カベヅタイ cells. As always, race wins decide
nothing — no promotion or gating logic reads this table.

## Notes

Champion, course, and dominance rule are unchanged from Cups 003-005 —
still pi2-pref-w6/プリフヒバリ (learning run 32890092906), still the
4-head rule. `reports/league/season/state.json` shows season stage
"collecting" (wave 8, round 4) with no collection/learning/match run
id recorded and no matching workflow run in progress — pre-existing
season state, not touched here, not currently blocking Cup hosting.
