# Design record: Research Cup 001 (リサーチカップ)

Named the Diversity Cup for Cups 001-008; renamed at Cup 009 (see the
Cup 009+ amendment below). The event, the numbering, the prime pool
and every frozen rule are continuous across the rename.

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

## Cup 009+ amendment: Research Cup rename, and rule-alpha's candidate union

Date: 2026-08-30. Three changes, all confined to Cup 009 onward.

### 1. The event is renamed Diversity Cup -> Research Cup

Numbering continues (Cup 009 is the ninth cup, not a new series), and so
do the ledger, the single-use prime pool, the champion lineage and every
frozen rule. A numbering reset was rejected outright: the prime pool's
single-use-per-source guarantee is tracked by cup id in
`reports/league/cup-ledger.md`, and restarting the count would put that
guarantee at risk for a cosmetic gain.

**What is deliberately NOT renamed**, and why. Workflow filenames
(`diversity-cup.yml`, `host-diversity-cup.yml`), script filenames
(`host_diversity_cup.py`, `analyze_diversity_cup.py`), the cross-workflow
`cup-cell-*` artifact contract, and the report filenames for Cups
001-008. A `workflow_dispatch` targets a workflow by filename and GitHub
keys run history to that path, so renaming those files would orphan the
run history of Cups 001-008 -- the run ids the ledger records as
evidence -- and break `cup-preference-distillation.yml`'s consumer
contract, for no research benefit. Human-facing names (workflow display
names, run titles, document titles, step summaries) are renamed, as is
the aggregate artifact going forward: Cup 009+ uploads
`research-cup-result-<run>` where Cups 001-008 uploaded
`diversity-cup-result-<run>`.

### 2. rule-alpha races with its Layer 1 proposal family unioned in

Cup 008 measured rule-alpha's executed action absent from the candidate
provider's set on 89 of 89 boards, and the current agent's on 78%
(`reports/league/diversity-cup-008.md`). Mining papered over this by
unioning the exact actor command into the fork's roots, so a preference
label was written for a move that at inference was not in the choice set
at all -- a defect upstream of any ranker.

From Cup 009 the rule-alpha episode runs `--union-rule-alpha
--rule-alpha-union-limit 4`, adding rule-alpha's own Layer 1 placement
for each visible pool item to the candidate set. Measured on
dual-empty-permute-000-607 seed 42
(`reports/candidate-support/rule-alpha-union-20260830.md`): support hits
0/31 -> 31/31, and running the same episode with
`add_exact_agent_candidate` turned OFF gave a bit-identical result, so
the mining-time injection is now a provable no-op.

**The exact-agent candidate is nevertheless kept on.** Having proved it
is a no-op when the union works, leaving it in costs nothing and insures
the cup against an unmeasured board where the union might miss; the
per-step `candidate_support_hit` field still records whether the
provider supplied the action, so the measurement is not weakened.

### 3. rule-alpha alone gets its own fork budget

`mine_fork_budget` stays 12 for the other five horses -- the runbook
fixes it and this amendment does not move it. rule-alpha gets a separate
`rule_alpha_fork_budget`, default 40, because the union moved its
bottleneck: on the measured cell it raised disagreements from 3 to 25,
of which budget 12 could fork only 12. At 40 all 25 fork and strict
pairs go 3 -> 23 at a 92% strict rate, against 10 at budget 12.

**Only rule-alpha changes.** The champion, the current agent and the
three rule studs run byte-identical commands to Cup 008, so every
cross-cup comparison except rule-alpha's stays exact and the corpus
shift is attributable to one horse.

### What this does not claim

The union is a baseline that makes teacher actions executable. Both
sides of a rule-alpha fork are still drawn from rule-alpha's own
generator -- the alternatives now come from its discard pile rather than
from nowhere -- so a richer preference signal is expected, but no action
outside rule-alpha's generator has been produced. Cost is real and
recorded: 756 fork step-equivalents against the baseline's 132, well
inside the 180-minute cell timeout (Cup 008's longest cell ran 26
minutes). Course isolation, four-head dominance, the genuine-terminal
teacher contract and the no-auto-training boundary are unchanged.

## Cup 010+ amendment: the teacher's rollout continuation is widened

Date: 2026-08-30. **This one changes the teacher, so Cup 010 standings
are NOT comparable to Cups 001-009 for any horse.** That is a real cost
and it is paid deliberately; the reason follows.

### What was wrong

`_terminal_rollout` values a board by continuing with frozen rank-0 over
the generic provider. Across the 108 terminal rollouts inside Cup 009's
mining forks on one cell, **zero** ended by exhausting the item stream;
96.3% ended `no_retained_candidate` and 3.7% `no_safe_retained_candidate`.
Both are listed in `GENUINE_TERMINATIONS`, so "the generator ran out of
proposals" has been recorded as "the board is full" in every cup so far.

The teacher was therefore never a Monte Carlo return to a terminal. It
was an n-step estimate with the bootstrap term pinned to zero,

    V(s_t) ~= sum_{k<n} r_{t+k} + gamma^n * V(s_{t+n}),  V(s_{t+n}) := 0

at n ~ 9-11. Measured against rule-alpha's own continuation from the
same boards, that zero understates remaining capacity by 2-4x
(`reports/candidate-support/rollout-ceiling-20260830.md`).

### The change

From Cup 010 the rollout continuation runs
`--union-rollout-continuation`: the rule-alpha proposal family is unioned
into the provider the continuation selects from, at
`--rule-alpha-union-limit 4`. Measured over six cells the continuation
goes from 9.2 steps / 9.62 fill to 17.7 / 20.50, against rule-alpha's own
21.0 / 23.97 -- 40% of the reference ceiling to 85%.

### Why this reverses a decision made eight hours earlier

The Cup 009 amendment deliberately left this provider alone, arguing
that the teacher's lookahead must not be given rule-alpha's flavour or
the pipeline becomes imitation one level up. The argument stands on its
own terms and the measurement overrides it on two counts.

The price of the narrow teacher was a 60% underestimate of board
capacity behind every dominance verdict in nine cups. And the composite
is not imitation: on `dual-shelf-mixed` rank-0 choosing from the union
reaches 25.68 fill where rank-0 alone reaches 7.45 and rule-alpha alone
reaches 8.32. Proposals from rule-alpha, selection by the generic
ranker, a result neither reaches by itself.

### What it costs, stated plainly

Cup 010's numbers stand alone. Strict-pair counts, novel-board rates and
race tables from Cups 001-009 were produced by a teacher that stopped
looking after nine moves; Cup 010's are produced by one that looks for
about eighteen. Cross-cup trend lines through Cup 009 into 010 are not
valid and must not be drawn. The per-cup reports keep their own numbers;
the ledger row for 010 records the teacher change.

Everything else is unchanged: course isolation, single-use primes, the
four-head dominance rule, the genuine-terminal requirement, the
no-auto-training boundary, and `mine_fork_budget` at 12 for the studs
with rule-alpha's own budget separate.

### What it does not fix

The widened continuation still ends early -- `selected_action_failure`
on 3 of 6 cells, because a wider candidate set contains physically
riskier actions and greedy rank-0 takes them. rule-alpha, the reference,
is itself non-genuine on 4 of 6 cells. The reference is a higher
ceiling, not the true one, and the bootstrap term is still zero.

### A consequence for two null results

Stage 0 (mechanical perturbation, 40/40 `incomparable`) and the
archetype-ladder swap probe both returned "no effect" through the narrow
teacher on 2026-08-30. A perturbation that pays off at step 25 cannot be
seen by a rollout that stops at step 9. Those nulls are **not settled**
and are to be re-run against the widened continuation before being read
as evidence that the hand-coded rules are locally optimal.

## Cup 010+ amendment WITHDRAWN, and what replaced it was too

Date: 2026-08-31. The amendment above -- widening the teacher's rollout
continuation with the rule-alpha union from Cup 010 -- **is withdrawn.
Cup 011 returns to Cup 009's teacher.**

**Why: it does not fit in a cell.** Cup 010 (run 33358944688) lost three
of six cells to the 180-minute job timeout and its standings job was
skipped. `dual-preloaded-dedicated` took **146 minutes** where the same
family took 43 in Cup 009. The estimate that cleared this change looked
only at the continuation growing from ~9 to ~18 steps; it missed that
the unioned candidate set (2.71 -> 12.65 candidates per state) also
multiplies the cost of every step *inside* that continuation. The two
compound.

**The cheaper replacement was measured and also not adopted.** Instead
of extending the continuation, book its tail with a fitted V_theta:

    V(s_t) ~= measured prefix delta + V_theta(s_{t+n})

The model is real -- it ranks boards better than the ten-step rollout it
would replace, Spearman +0.586 / +0.594 / +0.658 against +0.365 /
+0.477 / +0.399 on leave-one-cell-out folds. But against a
higher-ceiling judge its verdicts agree 14/21 where the incumbent agrees
13/21, and the reason is a scale mismatch: the bootstrap term averages
**17.371 fill points** added to each side of a comparison whose measured
gap averages **0.729**. A model validated on ranking *different* boards
does not thereby earn the right to rank two boards *one move apart*.
Full measurement: `reports/value/bootstrap-not-adopted-20260831.md`.

**What stands from this line of work.** The candidate union on the
*inference* side -- Cup 009's change, rule-alpha's own candidates in the
actor's root set -- is unaffected and stays. So does the finding that
provoked all of this: across 108 terminal rollouts in Cup 009, zero
reached `stream_exhausted` and 96.3% stopped at `no_retained_candidate`,
so the teacher books a 2-4x underestimate as a finished board. That
defect is real and is **still open**. Two attempts to close it have now
failed on cost and on resolution respectively, and both are recorded so
a third does not repeat them.

**Cup 010's course is burnt.** 000: 631/641/643/647 and 001: 509/521 are
spent -- three cells did run -- and must not be redrawn.
