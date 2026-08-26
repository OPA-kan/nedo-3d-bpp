# Diversity Cup 003 「アーモンドビレッジ」 — 種馬成績表

Date: 2026-08-26. Run 32935678296 (episodes + standings both succeeded
cleanly — no crash, no local reconstruction needed). Dispatched via the
one-click `host-diversity-cup.yml` host, which resolved the champion
run, drew six fresh never-used primes, preregistered ledger row 003,
and dispatched `diversity-cup.yml` itself. Field: champion プリフヒバリ
(pi2-pref-w6, plain), ジ・アーモンド (current-agent), and three mining
studs, forking against the champion's own ensemble (learning run
32890092906). Six virgin cells, primes 449-463, fork budget
12/episode.

**This is the first cup scored entirely under the 4-head dominance
rule** (surface_total_variation excluded, fix `1087667`) — Cup 001
and Cup 002 were both mined under the old 5-head rule despite what an
earlier version of the Cup 002 writeup said (episodes there ran two
hours before the fix landed; see the correction in
`diversity-cup-002.md`).

## Research standings (what the cup is for)

| stud | novel board rate | disagreements | forks | strict pairs | pairs / M step-equiv |
|---|---|---|---|---|---|
| グリッドオー (rule-grid) | 0.79 | 38 | 38 | **17** | **39171** |
| カベヅタイ (rule-edge) | 0.80 | 33 | 33 | 16 | 44444 |
| テイジュウシン (rule-lowcog) | 0.82 | 32 | 32 | 12 | 37736 |
| ジ・アーモンド | 0.96 | 19 | 19 | 11 | 36424 |

- **Strict pairs jumped from 17 (Cup 002) to 56** on the same 6-cell
  format against the same champion. This is the fix showing up in
  practice: removing an unvalidated, noisy proxy axis from strict
  dominance let genuinely fill/soft/priority-clear wins register as
  strict instead of being knocked down to "incomparable" by a
  surface-flatness wobble. Per-stud: グリッドオー 7->17, カベヅタイ
  7->16, テイジュウシン 3->12 — every stud roughly doubled or more.
- **ジ・アーモンド went from 0/19 to 11/19 strict forks** — the
  clearest single before/after data point. Its forks were always
  disagreeing with the champion at similar volume (19 both cups); what
  changed is how many of those disagreements register as decisive
  once surface noise stops vetoing them.
- Side corpus: **56 preference pairs** banked this cup alone (vs 17
  and 15 the two previous cups combined) — `side-corpus-pairs.jsonl`
  in the run artifact, not committed, not fed to training (same
  boundary as Cups 001-002).
- **ジ・アーモンド's termination rate got worse, not better**: 0 of 6
  cells reached genuine termination this cup (all `max_steps` or
  `selected_action_failure`), versus 1 of 6 last cup. Candidate-support
  misses: 152/181 steps (84%, vs 132/164 = 80% in Cup 002). Two cups
  is not enough to call this a trend rather than course-to-course
  noise, but nothing here suggests it's improving on its own.
- ジ・アーモンド again set the cup's best terminal fill
  (`fill_score_proxy` 38.64, 25 placed, single-empty-noshelf cell,
  again a non-genuine `selected_action_failure` episode) — the
  pattern from Cup 002 repeats: its uncapped, unscreened play
  occasionally reaches far higher raw fill than anything the other
  four horses produce, at the cost of not settling cleanly.

## Research averages (raw final_metrics, mean across 6 cells)

| horse | fill_score_proxy | placed_count | priority covered | center_of_mass_z | genuine term. |
|---|---|---|---|---|---|
| プリフヒバリ (champion) | 8.43 | 8.50 | 0.17 | 0.697 | 6/6 |
| ジ・アーモンド | 31.33 | 30.33 | 0.83 | 0.686 | **0/6** |
| グリッドオー | 10.23 | 10.50 | 0.00 | 0.768 | 6/6 |
| テイジュウシン | 9.27 | 9.33 | 0.00 | 0.727 | 6/6 |
| カベヅタイ | 8.64 | 9.33 | 0.00 | 0.668 | 6/6 |

As in Cup 002: ジ・アーモンド's fill/placed averages are inflated by
running far more steps before stopping (nobody else averages anywhere
near 30 placed at 6 cells), not by placing more efficiently per step —
treat these as descriptive, not a quality ranking. post_shake_* is
omitted here; it has zero genuine-termination samples for
ジ・アーモンド this cup (down from n=1 last cup).

## Race standings (spectator content)

W-L-D-∥ (challenger wins–member wins–equal–incomparable), first-named
first; U = unmeasured (non-genuine ジ・アーモンド episode):

| pairing | result |
|---|---|
| プリフヒバリ vs ジ・アーモンド | 0-0-0-0, U6 |
| プリフヒバリ vs グリッドオー | 0-2-0-4 |
| プリフヒバリ vs テイジュウシン | 0-1-0-5 |
| プリフヒバリ vs カベヅタイ | 0-1-0-5 |
| ジ・アーモンド vs グリッドオー | 0-0-0-0, U6 |
| ジ・アーモンド vs テイジュウシン | 0-0-0-0, U6 |
| ジ・アーモンド vs カベヅタイ | 0-0-0-0, U6 |
| グリッドオー vs テイジュウシン | 0-0-0-6 |
| グリッドオー vs カベヅタイ | 1-0-1-4 |
| テイジュウシン vs カベヅタイ | 0-1-0-5 |

ジ・アーモンド's races are entirely unmeasured this cup (6 of 6 —
worse than Cup 002's 5/6), for the same reason as the research
standings above: no genuine termination means no shake test means no
`post_shake_*` heads for `league.episode_outcome()` to compare.

Among the champion and three rule studs (fully measured, 6 pairings x
6 cells = 36), races are even more incomparable than Cup 002: 29/36
(81%, vs 25/36 in Cup 002). Of 6 decisive results plus 1 equal, the
champion lost all 4 of its decisive races (0 wins); グリッドオー
picked up 3 (2 vs champion, 1 vs カベヅタイ), カベヅタイ 2,
テイジュウシン 1. As always, race wins decide nothing — no promotion
or gating logic reads this table.

## Calibration of the planning numbers

56 strict pairs from one 6-cell cup blows past the runbook's 40-90
milestone for "1-3 cups" in a single cup — but that milestone was
calibrated on the old 5-head rule's 15-17 pairs/cup, so it needs
re-anchoring now that the rule has changed. At this new rate (~45
pairs/cup from the three rule studs alone, ~56 with ジ・アーモンド),
the ~130-pair threshold that trained the first promoted policy is
reachable in 2-3 more cups rather than ~9.
