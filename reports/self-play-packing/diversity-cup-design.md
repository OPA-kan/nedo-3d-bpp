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
  primes from the 401-799 pool, appended to
  `reports/league/cup-ledger.md` BEFORE dispatch, with the same
  protocol and fork budget. Novelty saturation (total novel-board
  rate < ~0.30 two cups running) pauses hosting until the next
  generation promotes.

## Cup 002+ amendment: exact current-agent anchor

Date: 2026-08-26. Cup 001 remains the four-horse event reported above.
Starting with Cup 002, the field adds `current-agent`: one stateful
instance of the shipped `agent/agent.py::Agent.policy`, initialized once
and advanced exactly once per live step. This is not the older `legacy`
Cup mode (rank-0 over the Cup provider). Its own generator, rescue,
fallback and guard stack choose the action.

The exact action is unioned into the bounded Cup root support before
physical measurement. A support hit/miss is recorded; a miss is not
silently replaced by the nearest provider candidate. The actor always
executes its own action, including a physically rejected action, so race
outcomes remain faithful. When physically comparable, the same terminal
fork used for the rule studs compares it with the frozen champion action.
Environment dominance, not imitation of the hand-coded agent, decides the
teacher.

Cup 002+ therefore has five horses: frozen learned champion,
`current-agent`, `rule-grid`, `rule-lowcog` and `rule-edge`. Reports must
include current-agent support misses and maximum terminal fill with horse,
cell and placed count. This changes the actor field, not the fork budget,
course isolation, dominance rule or no-auto-training boundary.

## Cup 006+ amendment: exact rule-alpha actor

Date: 2026-08-30. Starting with Cup 006, the field adds `rule-alpha`
from source commit `7908b09`. It uses the same exact-action contract as
`current-agent`: one stateful policy instance per episode, no private
stream reorder, and its command is unioned into the bounded root support
before PyBullet validation and paired terminal mining. The standalone
rule-alpha official-task runner is not used, so its reconstructed stream
settings cannot affect the Cup course.

Cup 006+ therefore has six horses: the frozen learned champion, the two
exact stateful actors `current-agent` and `rule-alpha`, and the three
compact rule studs. This amendment changes only actor coverage. Course
isolation, fixed fork budget, four-head dominance, genuine-terminal
teacher contract and the no-auto-training boundary remain unchanged.

## Cup 002+ amendment: surface_total_variation drops out of the fork dominance rule

Date: 2026-08-26 (second amendment, made after Cup 002 was preregistered
above but before it dispatched — the ledger row was still `pending` —
so this does reach Cup 002, superseding "not... dominance rule" in the
amendment above for this one axis).

`surface_total_variation_delta` is removed from the strict 5-head
dominance rule everywhere it decided a fork/pair verdict:
`DOMINANCE_HEADS` in `run_vector_mcts.py`,
`build_terminal_rollout_trigger_dataset.py` and
`train_delta_y_head.py`, and `OBJECTIVE_METRICS` in
`aggregate_terminal_rollout_policy.py`. The rule is now 4-head:
fill_gain, soft_violation_gain, priority_covered_gain,
priority_misrouted_gain.

Reason: `surface_total_variation` is a heightmap-adjacency proxy
(`docs/theory/ABC_IMPLEMENTATION_SPEC.md` section 9), not one of the
official-aligned heads — `scripts/league.py`'s `LEAGUE_HEADS` never
included it, and `MULTI_HEAD_SPECS` already tags it
`"minimize_proxy"` rather than `"minimize"`, which
`audit_paired_physical_contract.py`'s `PARETO_OBJECTIVES` already uses
to exclude it from the audited confidence-Pareto frontier. The 5-head
copies used for the Cup fork verdict, preference-distillation
`beats_incumbent` labels and the online adapter's fork gate were the
only places still giving it equal veto power in strict dominance, so
an unvalidated axis could tie-break or invalidate an otherwise clean
fill/soft/priority win. This amendment brings those copies in line
with the pattern the rest of the codebase already uses.

Not affected: it remains a reported/regressed diagnostic wherever it
already was (`COMPONENT_HEADS` in `train_delta_y_head.py`, the
`CANDIDATE_HEADS` model input features in `train_rollout_trigger.py`,
`REPORT_METRICS` in `aggregate_terminal_rollout_policy.py`); only its
role in *deciding* a strict-dominance winner is removed. League
promotion (`league.py`), the season registry and Cup 001's already-run
result are unaffected — Cup 001's strict-pair count and novel-board
rate were produced under the old 5-head rule and are not directly
comparable to Cup 002 onward. Full unit suite green after the change
(`python -m unittest discover -s tests`, 1554 tests, the one failure
being the pre-existing Python-3.12 gate in
`audit_deadline_rollout.py`, unrelated to this change).

## Cup 008+ amendment: side-corpus pool extended to 401-799

The side-corpus stream pool originally ran 401-599: 31 primes per
source, disjoint from the frozen eval variants and every season-1 wave
prime. `host_diversity_cup.COURSE_PATTERN` draws a fixed six-cell
course as four cells from source 000 and two from 001, so source 000
depletes at twice the rate of 001. After Cup 007 that caught up:
source 000 held three primes (587, 593, 599) against a four-cell
requirement, `allocate_course` raised

    Diversity Cup stream pool exhausted for source 000: need 4, have 3

and Cup 008 could not be hosted. This is the case the runbook's hard
boundaries anticipate ("when the pool runs dry, extend
`STREAM_VARIANTS` — that IS a code change, coordinate first").

**Coordinated decision: extend the pool rather than rebalance the
course.** Primes 601-799 are appended for both sources (30 more each,
61 per source total). Rebalancing `COURSE_PATTERN` to 3+3 was the
considered alternative and was rejected because it would permanently
change which scenario family runs on which source, breaking
comparability with Cups 001-007 for the sake of one cup's worth of
headroom. Extending the pool leaves the course composition — and so
every cross-cup comparison — exactly as preregistered.

Disjointness is preserved and was verified rather than assumed: every
prime referenced anywhere in the repository was scanned, and the
maximum was 599; `eval_variants_forbidden` in
`reports/league/season/waves.json` tops out at 197 and the season-1
wave primes at 379. Nothing in 601-799 collides.

The window is encoded in **two** places, and a prime present in only
one is silently never drawn: the pool block in
`build_scenario_matrix.STREAM_VARIANTS`, and the draw window in
`host_diversity_cup`, which previously inlined `401 <= p <= 599` and
is now the named constant `CUP_PRIME_RANGE`. Both moved together here.

Unchanged: the six-cell course size, the 12 forks/episode budget, the
one-cup-at-a-time rule, single-use-per-source primes, and the novelty
stopping rule. Nothing about scoring, dominance or promotion is
touched.
