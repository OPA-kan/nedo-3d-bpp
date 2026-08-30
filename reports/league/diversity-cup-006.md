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
| rule-alpha | 0.94 | 17 | 17 | 16 | 39409 |
| グリッドオー (rule-grid) | 0.83 | 32 | 32 | 15 | 43103 |
| ジ・アーモンド | 0.96 | 17 | 17 | 7 | 38889 |

- **Side corpus: 78 preference pairs banked this cup** — the largest
  cup yet (vs 53/56/75 in Cups 003-005). `side-corpus-pairs.jsonl` in
  the run artifact, not committed, not fed to training (same boundary
  as every prior cup).
- **Corrected from 79 to 78** (rule-alpha 17 -> 16) after the
  distillation run failed on this Cup's artifact. One rule-alpha fork
  in the dual-preloaded-dedicated-000-523 cell was recorded as a
  strict pair but was not one: the actor's own action turned out
  physically unsafe inside the fork, so it left
  `build_resurrection_audit`'s comparison set entirely (that set is
  built from *safe* root candidates, so an unsafe side is dropped
  rather than censored). The champion was then alone on a
  one-candidate terminal frontier with `terminal_truth_complete` still
  True, and the miner read a "winner" off a one-horse race. Fixed at
  the source in `run_terminal_rollout_policy.pair_fork_winner`, which
  now requires both pair ids to be terminal-eligible; the analyzer and
  the dataset builder apply the same rule so legacy artifacts report
  and import consistently. Prior cups: **003 and 005 are proven clean**
  (their distillations succeeded under the old builder, which aborted
  on exactly this condition), **004 rechecked directly against its
  artifact** (0 one-sided of 53 verdicts); 001-002 were never distilled
  and are not rechecked here, so their recorded pair counts should be
  treated as upper bounds. The same defect also let the online adapter
  (シュンヒバリ) switch its executed action to, and take a preference
  update from, such a one-horse race; that path is fixed by the same
  helper.
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

## Shun Long distillation of this cup's memory

Run 33297218065 (on `ce6cb2b`, after the one-horse-race fix; the first
attempt 33296515759 aborted on the defect this cup exposed). 78 pairs,
6 course-cell groups, `passes=1`, base model 32890092906. Status stays
`capability_only_not_league_evidence` — no match, no promotion, and
the registry is untouched, so the next cup keeps the current champion.

| | before | after |
|---|---|---|
| leave-one-course-cell-out AUC | 0.590 | **0.566** |
| leave-one-course-cell-out log loss | 1.716 | **0.960** |
| same-corpus AUC | 0.590 | 0.644 |

Same shape as Cup 003's distillation but noticeably less overfit: the
held-out ranking still degrades (0.590 -> 0.566) while the in-corpus
fit improves, so the memory is still not earning out-of-distribution
ranking power. What is new is calibration — held-out log loss nearly
halves (1.716 -> 0.960), where Cup 003's held-out AUC had collapsed
below chance (0.624 -> 0.478) on 56 pairs. On 78 pairs the same
procedure is directionally better on both counts. Treat this as
"bigger corpus hurts less", not as evidence the memory helps.

## rule-alpha version boundary (read before reusing these numbers)

This cup ran **rule-alpha@7908b09**, the state vendored into the Cup
trunk by `f8464ff`. Later defect fixes were made after this cup was
collected; they live on the branch
**`claude/rule-alpha-layer-1-ch78oi`** (an orphan line that shares no
history with this branch — empty merge-base, and it carries no
`reports/league` or `scripts/`, so it is vendored file-by-file, never
merged). At the time of this cup they were not yet vendored here:

- `7908b09` terrace: `level_residual` unreachable below an early
  return, `plateau_gain` always 0 under its clamp — two of the key's
  three terms were never read. (This one **is** in the cup.)
- `2567bcb` two vetoes without a fallback were emptying the survivor
  list and ending episodes outright (at the stop, 10/10 and 17/17
  candidates died there).
- `c974c28` the wedge's material reservation was reordering the whole
  stream, pulling the four largest boxes past position 13.
- `803fd6f` the floor height map was blind across the whole container
  above 0.785 m, so free-rectangle search invented room inside solids.

So rule-alpha's debut figures here (0/6 genuine termination,
`rule_alpha_declined` in 5 of 6 cells, 105/105 candidate-support
misses, 16 strict pairs) characterise **7908b09 only**, and three of
the four known episode-ending defects were still live in it — the
`rule_alpha_declined` terminations in particular are the expected
signature of the `2567bcb` veto defect. Do not read them as the
current actor's ceiling.

Those fixes have since been vendored into this branch, so **Cup 008
onward races the newer actor**; Cup 007 was already dispatched from
`3b95cfc` and still ran 7908b09. Measured on the cup's own case 000 /
seed 42, before and after the vendor: 16 placed / fill 24.316 ->
**21 placed / fill 33.420**. What did *not* change is the ending —
both versions still finish `rule_alpha_declined` with
`genuine_termination` false, so rule-alpha stays unmeasured in race
tables. Its cup value remains mining (16 strict pairs from 17 forks
here), which does not depend on its own episode terminating.

## Notes

Champion, course, and dominance rule are unchanged from Cups 003-005 —
still pi2-pref-w6/プリフヒバリ (learning run 32890092906), still the
4-head rule. `reports/league/season/state.json` shows season stage
"collecting" (wave 8, round 4) with no collection/learning/match run
id recorded and no matching workflow run in progress — pre-existing
season state, not touched here, not currently blocking Cup hosting.
