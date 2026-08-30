# Diversity Cup hosting runbook (for the Codex session)

The cup is a teacher-mining event, fully outside season 1. Hosting one
is a **dispatch plus a ledger row — never a code change**. Design and
frozen rules: `reports/self-play-packing/diversity-cup-design.md`.
Scoring: `scripts/analyze_diversity_cup.py` (runs inside the workflow).

## One-click hosting (preferred for a human operator)

Open GitHub Actions → **Host Diversity Cup (one click)** → **Run
workflow**. Both inputs may stay blank: the workflow resolves the current
champion's learning run from season state, draws the next unused six
source-specific streams, appends and pushes the ledger preregistration,
then dispatches the Cup. Optional inputs only override the model run or
assert the expected next Cup number. The job refuses to proceed while
another Cup is queued/running.

This workflow is only a host. The physics event remains
`diversity-cup.yml`, and all manual rules below remain the recovery/audit
contract. Cup 006+ runs the six-horse field including the exact stateful
current agent and exact stateful rule-alpha actor. The aggregate report
includes maximum terminal fill and exact-actor candidate-support misses.

## Per-cup procedure

The following is the transparent manual equivalent of the one-click host
and the recovery path if its dispatch step fails after preregistration.

1. **Pick the champion model.** The studs mine against the CURRENT
   champion's ensemble. Find the learning run id of the round that
   promoted the current champion: `reports/league/season/state.json` →
   `history[*]` where `promoted=true` and `champion_after` equals the
   current champion → that entry's `runs.learning` (for pi2-pref-w6
   this is 32890092906). The artifact name is `rollout-policy-model`.
2. **Draw a fresh course.** Six cells, one per scenario family
   (dual-preloaded-dedicated, dual-empty, single-empty-noshelf,
   dual-shelf-mixed, single-empty-shelf, single-preloaded), each on a
   prime from the 401-599 pool that the ledger shows as unused for that
   source (000 or 001). Alternate sources roughly as cup 001 did.
   Cell naming: `<scenario>-permute-<source>-<prime>`.
3. **Append the ledger row FIRST** (`reports/league/cup-ledger.md`) —
   cup id, date, model run, streams. Commit and push. This is the
   preregistration; a cup without a prior ledger row does not count.
4. **Dispatch** `diversity-cup.yml` on `work/terminal-rollout-oracle`:
   - `model_run_id`: from step 1
   - `cup_id`: next number ("002", "003", ...)
   - `mine_fork_budget`: `12` (do not tune this per cup; changing it
     is a design change and needs a design-record amendment)
   - `cells`: JSON array of the six
     `{"cell":...,"scenario":...,"stream":...}` rows from step 2.
     Empty re-runs the Cup 001 course — never do that; courses are
     single-use.
5. **After the run**: download `diversity-cup-result-<run>` →
   `cup-report.json` + `side-corpus-pairs.jsonl`. Fill the ledger
   row's run id, `side_corpus_pairs`, and total novel-board rate.
   Optionally write `reports/league/diversity-cup-<id>.md` with the
   stud standings (research metrics first, race tables second). Keep
   the pairs jsonl attached to the run artifact — do not commit the
   raw pairs into the repo.
6. **Failure handling**: a failed cell job → re-dispatch the SAME
   inputs once (deterministic; the course is not burned until a run
   succeeds). Note the retry in the ledger.

## Hard boundaries (do not cross)

- Never touch `reports/league/season/*`, `registry.json`, the
  hard-state/learning matrices, or the frozen eval variants.
- Never feed `side-corpus-pairs.jsonl` into the season learner or any
  training run automatically. Mixing Cup pairs is a separate experiment.
  The first such experiment is explicitly preregistered in
  `reports/self-play-packing/shun-long-cup-memory-distillation.md` and may
  run only through `cup-preference-distillation.yml`; it emits a standalone
  capability artifact and cannot dispatch a match or alter season state.
- Course primes are single-use per source. When the pool runs dry,
  extend `STREAM_VARIANTS` in `scripts/build_scenario_matrix.py` (that
  IS a code change — coordinate first).
- One cup at a time; check Actions for a running Diversity Cup before
  dispatching.

## How much data until it matters (planning guidance)

Anchors from measured history: the whole wave-4 teacher corpus (100
cells) yielded 1803 preference pairs of which only **129 were
decisive positives**, and that was enough to train the first promoted
preference policy (pair AUC 0.745). Every cup pair is decisive by
construction and comes from states the champion line does not visit —
per-pair value should be at least comparable.

Measured yield (Cup 001 actuals, `diversity-cup-001.md`): ~5.2
disagreements per stud episode, 94/94 disagreements forked (the budget
of 12 never bound), strict-dominance rate 16% → **15 strict pairs per
6-cell cup**, novelty 0.81-0.84. Milestones at the 6-cell format:

| cups (same champion) | ~decisive pairs | what it buys |
|---|---|---|
| 1-3 | 15-45 | calibration probe: how wrong is the champion off-distribution; not enough to move training |
| ~9 | ~130 | matches the decisive-pair count that trained the first promoted policy — enough to preregister a mixed-corpus challenger (cup pairs as a 10-20% auxiliary slice) and expect a measurable effect |
| ~18 | ~270 | the clean A/B: two challengers on the same wave, identical except with/without the cup slice, one extra title look (preregister it) |

If cadence matters, the lever is a LARGER COURSE (the `cells` input
takes any number of cells; 12 cells ≈ double the take, halving the
cup count above), NOT a bigger fork budget — the harvest is
disagreement-limited. Course-size changes need a design-record
amendment first. The ledger's per-cup actuals always override these
planning numbers.

**Stopping rule (novelty saturation)**: if total `novel_board_rate`
drops below ~0.30 for two consecutive cups against the same champion,
pause hosting until the next generation promotes — the studs have
shown that champion everything they know.

**Cadence**: 1-2 cups per champion generation is the useful default;
more is fine while novelty stays high and CI is idle, but season runs
have priority on runners.
