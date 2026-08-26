# Design record: Diversity Cup 001 (ダイバーシティカップ)

Date: 2026-08-26. Direction set by the project owner; this file
preregisters the event before it runs. Companion to
`two-timescale-learning-and-diverse-actors.md`, which froze the rule
studs and reserved them for "season 2 or a separately preregistered
side corpus" — this is that side corpus.

## What the Cup is (and is not)

Not a win-maximizing round robin. The Cup is a **teacher-mining
event**: deliberately different-minded actors visit states the
champion line never reaches, and at those states we harvest exactly
the teacher the preference objective wants —

    at the SAME state s, was action A or action B better?

A plain round robin barely produces that signal: once trajectories
diverge, the boards differ and terminal comparisons stop being
same-state evidence. So the Cup's engine is the **counterfactual
mining fork**:

    rule stud visits state s
      ├ the stud's own choice a_rule   (always executed)
      └ the champion's choice a_nn    (from the frozen ensemble)
              ↓ when they disagree
      paired fork: both actions physically played to genuine terminal
              ↓
      strict 5-head dominance verdict → one preference pair saved

Frozen rules of the fork:

- **The stud always executes its own action.** Mining never alters the
  stud's trajectory — the whole point is its untouched state
  distribution (lattice-spacious, bottom-dense, perimeter-hugging
  boards). Forks are counterfactual observations only.
- Pairs are labeled by the SAME strict multi-head dominance rule as
  everything else; ties and censored terminals produce no pair.
- The champion's choice is the frozen generation-2 ensemble's argmax
  over the same physically screened safe candidates (incumbent raised
  to the switch threshold, exactly the production execution rule).
- Fork budget per episode is fixed up front (default 12) and every
  budget exhaustion is logged — no silent truncation of the harvest.

## Preregistered event card

- **Field (4 horses)**: プリフヒバリ `pi2-pref-w6` (champion, runs
  plain — the novelty baseline), グリッドオー `rule-grid`,
  テイジュウシン `rule-lowcog`, カベヅタイ `rule-edge` (each mining
  against the champion ensemble).
- **Course (6 fresh cells, seed 42)** — streams disjoint from BOTH the
  frozen eval variants and every preregistered season-1 wave prime
  (199-379); primes 401+ are virgin territory:
  - dual-preloaded-dedicated-permute-000-401
  - dual-empty-permute-000-419
  - single-empty-noshelf-permute-000-431
  - dual-shelf-mixed-permute-001-409
  - single-empty-shelf-permute-001-421
  - single-preloaded-permute-000-433
- **Model**: the current champion's own ensemble artifact — learning
  run 32890092906 (the run that trained プリフヒバリ); the run id
  passed at dispatch is recorded in every manifest.

## Scoring: research standings first, race standings second

Primary (what the Cup is FOR — per stud and total):

1. novel board fingerprint rate (fingerprints unseen in the champion's
   runs of the same streams);
2. action disagreement count (states where stud and champion differ);
3. strict dominance pairs harvested (the side corpus itself);
4. pair yield per physics cost (pairs per million physical step
   equivalents spent on forks);
5. coverage of soft/priority/stability events in mined terminals;
6. terminal vectors (fill, placed, violations) — reported, not ranked.

Secondary (the 競馬 part): all six pairwise W-L-D-∥ tables from the
same terminal results under `paired_relation` — pure spectator
content. **A stud that loses every race can still win the Cup as a
stud**: テイジュウシン going 0-for-fill while yielding the most usable
pairs from bottom-dense boards is a good outcome, and the report will
say so explicitly.

## Contracts

- **Season 1 untouched**: cup cells never enter the hard-state or
  learning matrices; waves 5-14 and the frozen eval set are unmodified.
  The cup workflow is dispatch-only and writes nothing to the season
  ledger, registry, or spectator live state.
- **Side corpus**: mined pairs live in the cup episode manifests and
  the analysis artifact. Feeding them into a future generation's
  training corpus is a SEPARATE preregistered step (expected: season 2
  design), not something this event does implicitly.
- Read-only spectating unchanged: cup standings are content and
  diagnostics; no manual tuning of anything from them beyond the
  preregistered side-corpus path above.
- Repeats, honestly counted: cups may be hosted periodically (the
  Codex session hosts them; procedure in
  `reports/league/cup-hosting-runbook.md`) under a rolling
  preregistration — each cup's course must be fresh never-reused
  primes from the 401-599 pool, appended to
  `reports/league/cup-ledger.md` BEFORE dispatch, with the same
  protocol and fork budget. Novelty saturation (total novel-board
  rate < ~0.30 two cups running) pauses hosting until the next
  generation promotes.
