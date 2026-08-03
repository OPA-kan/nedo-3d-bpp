# Handoff for the next model

Updated: 2026-08-02 JST (branch `claude/stride-endgame-saturation-test-gqssix` closed)

## Start here

Repository: https://github.com/OPA-kan/nedo-3d-bpp

- **Live trunk is `experiment/anchor-recall-oracle`, not `main`.** `main` is
  frozen at `d3986a9` and is ~39 commits behind. Reading `main` will give you
  an `agent/agent.py` that is 2,629 lines out of date.
- The counterfactual replay work from `claude/release-counterfactual-replay`
  has been fast-forwarded into the live trunk. No SHA is pinned here on
  purpose — generated report commits move the branch. Confirm branch state
  with `git fetch --all --prune` and `git log --oneline --decorate -10`.
- Run `git fetch --all --prune` before judging what exists.

```powershell
python scripts/context.py list
python scripts/context.py show handoff
python scripts/context.py evidence --topic risk   # measured facts, machine-readable
python scripts/context.py symbol PlacementCore.choose  # one symbol, not the module
```

Measured facts now live in `context/evidence.json` with explicit
active/superseded/historical status; the prose below points at it rather
than being the source of truth. When you need one function from
`agent/agent.py` (4,400 lines), pull it with `symbol` instead of reading
the file.

Do not load the whole repository. Select a profile and add `--full` only when
source-level detail is needed. New here: the `replay-dataset` profile.

## Where Task A and Task B go next

**This section was audited on 2026-08-02 and three of its claims were
wrong. Corrected below; the ledger entry
`task-a-offline-objective-misdiagnosed` records what was claimed and what
verification showed.**

### Task B is search-allocation limited

`ANCHOR_FIRST_PASS_ATTEMPTS` 64 -> 256 gave +25% placed at unchanged
total attempts per step: redistribution, not more work.

**The first thing to look at.** `ANCHOR_DEEP_PASS_ATTEMPTS` is also 256.
`attempts_per_unit` starts at the first-pass constant (`agent.py:4129`)
and is replaced by the deep constant on later rounds (`agent.py:4260`),
so with both at 256 every round is now uniform and the two-phase
structure is gone. Either raise the deep pass or admit the structure has
collapsed.

The endgame is still where the remaining loss is -- the fallback probe
found legal moves available at 2 of 3 terminal states -- and
state-dependent depth is the likely shape. But do NOT justify that with
a change in cause of death. Counted over all 30 episodes of
`reports/first-pass-depth`, EVERY arm ends `is_placed_safe False` 10 out
of 10; only the terminal fallback rate moves, and non-monotonically
(base 3/10, 128 6/10, 256 4/10). In the later
`reports/stability-tradeoff` rows the fallback difference disappears
entirely. An earlier version of this section claimed a topple-to-
exhaustion shift from a 5-episode block; it does not survive both
blocks.

### Task A is ordering limited, and the objective is not what it looks like

The first-pass change is neutral on Task A placed (25 either way), so
Task A gains come from the ORDER. That much holds.

**But the order is not selected by a weighted objective.**
`OFFLINE_FILL_WEIGHT` / `OFFLINE_STABILITY_WEIGHT` feed only
`DryRunResult.weighted_score()` (`agent.py:941`), which has NO callers.
Selection is `result.rank_key() > best_result.rank_key()`
(`agent.py:6350`), a five-element LEXICOGRAPHIC tuple
`(placed_count, placed_volume, fill_ratio, stability_proxy,
-normalized_center_of_mass_z)`. Sweeping the two weights leaves
`behaviour_sha256` bit-identical while `component_sha256` moves -- the
same probe ADR-003 used for the risk-lambda gap.

It is narrower still: `fill_ratio` is `placed_volume / total_capacity`
with a case-fixed denominator, so it is a monotone transform of
`placed_volume` and structurally redundant in the tuple. The effective
key is `(placed_count, placed_volume)`, and stability and cog are
consulted only between orders that place the SAME items.

So the diagnosis is not "too few components are priced". It is
**`placed_count` dominates lexicographically**, and the work is
replacing `rank_key`, not tuning weights.

**Status of that clean-up, done on this branch.** `context/knobs.json`
marked those two constants `"semantic": true`; they are now
`"semantic": false` carrying an INERT note, and the registry contract
distinguishes inert from telemetry so they are not re-promoted.
`weighted_score` is still present, deliberately: it is the only
coefficient-weighted form in the file and `docs/AGENT_OPERATIONS.md`
section 5.1 now rules that shape out unless the coefficients are
externally fixed or chosen by a pre-registered ablation. Delete it when
the `rank_key` replacement is designed, not before, so the decision is
made once.

**Raising the offline budget is already measured and flat.**
`task-a-episode-outcome-is-machine-speed-dependent` (active): at
`OFFLINE_MAX_EVALUATIONS` of 50, 55, 60 and unlimited the search selects
an IDENTICAL 41-element order. The search converges around 50
evaluations on case 000, and the 25-vs-26 placed difference was machine
speed, not the cap. Convergence is itself evidence that the objective,
not the budget, is binding. (13381bd moved orders evaluated 3.0 -> 51.3
by adopting the bounded dry run; an earlier version of this section had
that direction backwards.)

**ADR-003 is not empty ground.** It defines the offline evaluator as a
cheap deterministic *proposal oracle* rather than a faithful simulator,
and explicitly decides the ranking policy need not be shared. Revise it
before changing `rank_key`.

### The acceptance rule: a spec violation worth keeping, for now

`Agent.optimize` disagrees with ADR-001 section 5. The spec says
`採択: 辞書式評価が改善した場合だけ更新`; the code updates `best_items`
on improvement but then sets `current_items = list(neighbor)`
unconditionally, so the next neighbour is generated from the last order
evaluated whether it was any good or not. That is a diffusion with
best-so-far recording, not a local search, and it is why `rank_key`
cannot steer: the objective picks what to keep, never where to look.

Conforming to the spec was predicted to help. It does not. 60 loop
iterations per cell, deadline pushed to 900 s so the cap binds rather
than the clock, case a000, three seeds, constructive seed placed 16
everywhere:

| acceptance | s20260723 | s1 | s7 | mean placed | mean fill_ratio |
|---|---:|---:|---:|---:|---:|
| `walk` (shipped) | 23 | 20 | 22 | **21.67** | **0.38492** |
| `hillclimb` (ADR-001 s5) | 21 | 19 | 21 | 20.33 | 0.37070 |
| `ils` | 23 | 19 | 20 | 20.67 | 0.36163 |

`walk` wins or ties on every seed, on both axes. n = 3 seeds on one
case, so this is a direction (sign test p = 0.25), not a result.

**That table is on the OLD anchor envelope and its headline does not
survive the correction. Read this before using it.** Re-measured with
`ANCHOR_TRUE_ENVELOPE=1`, same design, same seeds:

| acceptance | s20260723 | s1 | s7 | mean placed | mean fill_ratio |
|---|---:|---:|---:|---:|---:|
| `walk` (shipped) | 24 | 20 | 22 | **22.00** | 0.38762 |
| `hillclimb` (ADR-001 s5) | 21 | 19 | 20 | 20.00 | 0.36295 |
| `ils` | 23 | **23** | 20 | **22.00** | **0.37249** |

`walk`'s sole advantage is gone: `ils` moves +4 at seed 1, ties `walk`
on placed and leads it on the fill delta (+0.01087 against +0.00270).
"`walk` wins on every seed" was a property of a search domain that was
blind along one wall. `hillclimb` stays last on both substrates.

**The mechanism survives, which was the thing at risk.** The worry was
that scrambling the order might be dodging the blind band rather than
finding better orders. On the corrected envelope the two arms that
travel far -- `walk` drift 41/29/36, `ils` 39/39/30 -- both reach 22.00,
while `hillclimb` at 19/18/24 reaches 20.00. Distance still tracks
quality. The constructive seed still evaluates to placed 16 on both
substrates, so widening the domain does not improve the starting point.

Multi-start was re-measured too and is unchanged: 19.67 against 22.00,
identical in every cell on placed and fill, at 59 distinct orders
against 60. Depth is why -- at 15 evaluations per start no start reaches
the widened region and the single start does. What reproduces across
both substrates is that the shipped `blend` construction is the WORST
start in 2 of 3 seeds (17/20/16 against mass 20/18/19), so the open line
is replacing the single start's construction at FULL budget.

The mechanism is the useful part: **quality tracks distance from the
seed.** `walk` drifts 29-37 of 41 positions and scores best; `hillclimb`
drifts 8-21 and scores worst. The directed arms do use their budget
better in the narrow sense -- best found at evaluation 43-52, wasting
7-16 afterwards, against `walk` finding its best at 13-28 and wasting
31-46 -- but they intensify into a worse basin.

So on this case `constructive_order` starts in a bad region and the
search's real job is ESCAPE, not intensification. **The next lever is
the seed or a multi-start, not the acceptance rule.**

**Design that multi-start under `AGENT_OPERATIONS.md` section 5.1.** The
obvious version -- perturb `constructive_order`'s 0.45 volume / 0.30
base_area / 0.25 mass blend and tune -- is exactly the weighted-sum
escape that rule forbids, and those three coefficients have no
derivation to begin with. Use the coefficient-free form instead:
generate a small set of NAMED constructions (volume alone, base_area
alone, mass alone, the current blend), run each as its own start, and
take the `max` over starts. That is an order statistic, so nothing is
tuned, and it also reports what lost.

The same rule reframes the `rank_key` work above. Section 5.1 names
lexicographic order as a PREFERRED coefficient-free form, so the tuple
being lexicographic is not itself the defect -- the redundancy of
`fill_ratio` inside it is. "Replace `rank_key` with a weighted objective
over the components that now have local signals" is not admissible as
written; it needs a pre-registered ablation that reports the losers, or
a form with no free coefficient.

Both alternatives stay in the tree, default-off, behind
`OFFLINE_SEARCH_ACCEPTANCE` (`walk` | `hillclimb` | `ils`), with
`OFFLINE_ILS_STALL_LIMIT` and `OFFLINE_ILS_KICK_STRENGTH`. The default
is unchanged and `behaviour_sha256` is unchanged at `a92092c2`.

`OFFLINE_RANDOM_SEED` is now an environment knob. It was a bare source
literal, which silently invalidated one earlier seed sweep: every cell
returned the same answer and the sweep measured nothing. A search whose
seed cannot be varied cannot have its variance measured.

Caveat carried forward: the neighbourhood was held FIXED across all
three arms (transpositions inside an `item_group` only, so the three
group blocks `constructive_order` lays down are immovable). A local
search losing to a diffusion is also a symptom of a poor neighbourhood.
Nothing here says randomised search is right; it says the acceptance
rule is not what binds.

**Audit of the harness that produced the table above.** Read this before
citing the numbers.

- **It is not exactly equal work.** The cap bounds loop ITERATIONS, and
  `DryRunEvaluator.evaluate` is memoised on the order tuple. Counted at
  seed 20260723: walk 60 distinct orders / 0 cache hits, ils 60 / 0,
  hillclimb **56 / 4**. Returning to `best_items` regenerates orders
  already seen, so hillclimb ran a 6.7% work deficit. That weakens
  walk-vs-hillclimb and leaves walk-vs-ils untouched. It probably does
  not explain a 2-placed gap -- the 4 missing evaluations sit at a tail
  where hillclimb had already stalled 10 iterations past its last gain
  -- but the design is not as clean as first reported.
- **Not the shipped path.** The probe calls `Agent.optimize` directly,
  bypassing `TimedAgentRunner` and `optimization_timeout`, and at a 900 s
  deadline the ADR-001 moving-average guard never fires. **These placed
  values are not shippable results**, only a comparison between arms.
- **Box is faster than CI**: 79 evaluations in 150 s here against 51.3 in
  the CI adoption run, so iteration counts do not transfer.
- **numpy is unpinned** (`requirements.txt`: `>=1.26,<3`); 2.5.1 was used
  here. PyBullet is pinned at 3.2.7, so physics is fixed, but the
  geometry math is not version-controlled.
- The first walk-vs-hillclimb A/B, run under a 150 s clock, gave the arms
  79 and 86 evaluations. **Do not cite those two numbers** -- that
  comparison was unequal work with instrumentation overhead inside a time
  budget. Its 23-vs-21 outcome did reproduce under the iteration cap.

Checks that came back clean: pair-macro generation makes zero
`evaluate()` calls, so the first logged evaluation really is the
constructive seed and the reconstructed accept trajectory is sound; and
the ablation `base` arm scrubs every experiment knob and sets none, so
the reproducibility run below was on shipped defaults, risk-on.

### The priority concern is NOT a blocker (official, 2026-08-03)

An earlier version of this section held back further depth work because
`priority_clean_ratio` read 0.575 at the shipped default against 0.803
at the old one (6W/3L/1T, p = 0.508). submission3334 settles it the
other way: **placement_score 4.45 -> 10.85, +143.8%**, the largest
relative gain of any component. The submission differs from
submission22 by more than the depth change, so nothing is credited to a
single commit -- but the combination did not damage priority placement,
and this must not gate work in the form it was written.

What it leaves open is the PROXY. `priority_clean_ratio` pointed one way
and the official component went the other. The proxy has never been
validated against an official number and this is the first evidence
bearing on it; treat its direction as unverified until a submission
pair moves it and placement_score together.

The stability worry is CLOSED, not carried: 256 shifts 0.202 of items
against 0.310 at 64, with 0 topples against 0.27 per episode. Do not
re-raise it. On Task A the shake proxy is mildly worse at 256 (15/25
shifted against 13/25, peak energy 13.50 against 10.99, n = 1), so
"neutral on Task A" is true of placed and not of everything.

## Current submission artefact

`dist/submission.zip`, sha256 `179de845a131ba498625a39876c55a9cd8996fc272da356f6805ae017b669574`,
built from trunk `77046b5`. Rebuild with
`python3 scripts/build_submission.py`; it packs `agent/agent.py` alone.

Two earlier artefacts from this branch are SUPERSEDED and must not be
submitted: `c9d0751e...` predates the trunk merge and is missing the Task
A bounded offline dry run (placed 20 instead of 25), and `83a41bbc...`
predates the POLICY_ATTEMPT_BUDGET unification. A commit message on this
branch records a third hash `4ba1a5e6...` which was written before the
build and is simply wrong; no such artefact exists.

## Branch close-out: `claude/stride-endgame-saturation-test-gqssix`

Read this before anything else on this branch. One default changed, one
instrument is new, and two lines were closed as negatives.

### The one shipped change

`ANCHOR_FIRST_PASS_ATTEMPTS` 64 -> 256 (`agent/agent.py`). Two paired
blocks, 30 episodes, five development configs: placed 9W/0L/1T against a
simultaneously-run base, sign test p = 0.0039, suite total 143 -> 179.
Four of the five configs return identical values in both blocks.

The fact that carries it: attempts per step is 7649 / 6793 / 7864 across
64 / 128 / 256 and max policy time is unchanged at ~6.53 s. This is the
same work distributed differently, not more work. Task A (offline
enabled) was checked separately and is neutral: placed 20 and fill
30.176 at both depths, offline time 109 -> 119 s inside a 150 s internal
budget and 61 s under the official 180 s limit.

The predicted cost is real: mean items-with-a-candidate in the opening
half falls 9.64 -> 8.28. placed rose on every configuration anyway.

Fallback deaths ROSE (3 -> 6 -> 4 per ten episodes). That is not a
regression. base dies at `placement_core` with `is_placed_safe` false,
toppling at step 12-18, and never reaches an endgame; 256 survives to
17-21 and then runs out of moves. The cause of death moved from early
topple to late exhaustion.

Reverting is one line. `first_pass64` is kept as an arm so the previous
default stays measurable, and `tests/test_board_features.py` pins 256.

**`reports/benchmarks/baseline.json` (dev placed 88 / fill 114.6) is now
stale as a guard**: it predates this change and the base arm re-measured
in the same session gave 69 and 74. Re-baseline before using it.

### The new instrument: placement / soft, locally

See `docs/ATTRIBUTE_PLACEMENT.md`. Four of the six official score
components have never had a local signal; two of them now do, as
violation counts rather than a score, because the violations-to-0-100
mapping is unpublished.

Read the caveats there before using it. The load-bearing one: **neither
development source has a priority container**, so `priority_misrouted`
is structurally always 0 on this suite and the routing rule cannot be
validated locally at all.

Its first run already contradicted an assumption: 1 of 4 priority items
ends up covered by a non-priority item on b000-k40, even though
`support_surfaces()` forbids placing anything on a priority item. The
over-constraint discards the same-attribute stacking the rules allow and
still permits the violation. Unverified mechanism: `support_surfaces()`
governs settled anchor generation only, so a release candidate can land
on one. **This is the highest-value thread left open.**

### Closed as negatives

- **Board receptivity** (A acceptance breadth / R alternativity / H
  repairability, `LOOKAHEAD_SELECTION_MODE=board`). Reproducibly MIXED:
  +4/+5 and +4/+4 wins, a -5/-4 loss, two configs unstable. Pooled
  6W/3L/1T, p = 0.508. Default stays `weighted`; the code stays,
  default-off, with 25 tests. `docs/BOARD_RECEPTIVITY.md`.
- **Soft/priority stacking relaxation as a fallback fix.** The agent IS
  stricter than the rules, but relaxing to the official rule unlocked
  ZERO placements at 3 of 3 terminal states, one of which had seven soft
  items available to unlock. Not the cause of the fallback. Whether it
  costs fill across a whole episode is still untested.

### The new instrument: stability, locally

`Evaluator.shake_test()`, called once from `env.evaluate()` at episode
end inside `saveState`/`restoreState`, so it cannot perturb anything.
Three ingredients are officially fixed (`COMPETITION_RULES.md:70-73`
and `COMPETITION_QA.md:17`): the lid closes, gravity varies, and the
score is displacement / force / kinetic energy with friction feeding it.
The magnitudes and thresholds are not, so the schedule is invented and
the output is a comparator, never the official number.

Stated deviation: **no lid**. An item can leave through the opening; a
lost item is charged as both a shift and a topple, because dropping it
from the averages would let the worst outcome improve the metric.

**This put a question mark over the shipped change, and the follow-up
run has since RESOLVED it -- read the resolution, not the worry.** The
n = 1 reading on b000-k40 (new default placed 16, 9 of 16 shifting,
`priority_clean_ratio` 0.75, against `first_pass64` at placed 11, 5 of
11 shifted, ratio 1.00) prompted the paired run that
`first-pass-256-stability-tradeoff-cleared` records, and the stability
half **reversed**: over ten paired episodes the shifted fraction,
normalised by item count, is 0.202 at 256 against 0.310 at 64, and
topples are 0 at 256 against 0.27 per episode at 64. 256 is if anything
GENTLER on the shake, and the single-episode reading is withdrawn.

Only the priority half survived, in direction and not in significance --
see `What blocks pushing either further` above. Do not carry a general
"deeper search costs stability" worry forward; it was measured and it
did not replicate.

### Where the remaining blindness is

Of the six official components: fill and num_placed are computed by the
bundled simulator; placement and soft now have local violation counts;
stability has the shake proxy. **cog is the only one with nothing** --
it is computable from mass and position but its normalisation is
unknown, and `center_of_mass_z` in `step_metrics` is the closest thing
that exists.

### The score structure that should drive priorities

`docs/OFFICIAL_SCORE_LOG.md`. placed is the GATE for cog / stability /
placement / soft, so a placed gain is worth more than its own component.
Do not try to recover the component weights from a single official log:
83 weight vectors on a 0.05 grid reproduce 17.58143 to within 0.05.

## User's goal

A competitive CPU-first agent for the NEDO airport-baggage constrained 3D
bin-packing competition. GitHub is the source of truth for code, reasoning,
simulator snapshots, tests, and reports.

## Where results live

Persistence differs per experiment **by design** — heavy artifacts stay in
Actions artifacts so git does not bloat; only compact summaries are committed.

| Experiment | Artifact | Auto-committed |
|---|---|---|
| Task B benchmark | raw runs | compact aggregate/history |
| Anchor recall oracle | yes | compact summary only |
| Lookahead comparison | yes | compact summary/history |
| CPU verification | yes | no |

New Task B runs persist `aggregate.md` and `aggregate.json` under
`reports/task-b/history/<run_id>/`; raw traces and per-replicate simulator
outputs stay in the Actions artifact. Historical runs from before this policy
change remain artifact-only unless imported deliberately.
`reports/lookahead/latest-summary.json` is named "latest" but stopped at
2026-07-28 — do not read it as current.

## Merging a forked evidence ledger

Two lines of work now extend `context/evidence.json` concurrently, so the
ledger forks routinely and the entry count differs per branch (this is
normal, not corruption). Merge it by these rules, which follow from the
ledger's own contract (`entries[].status`, `superseded_by`):

1. **Additive.** A merge only ever adds entries. Never drop an entry because
   the other branch does not have it.
2. **Never rewrite a value.** If a later measurement changes a number, the
   old entry stays, gets `status: superseded` and `superseded_by: <new id>`,
   and the new entry is appended. An entry is a record of what was measured
   at a time, not a mutable field.
3. **An id collision is a supersession, not a conflict.** If both sides added
   the same id with different content, do not pick a winner and do not merge
   the text. Rename by measurement (`<id>-v2`, or a date/run suffix), chain
   them with `superseded_by`, and keep both.
4. **Order is not meaning.** `entries` is an append log; a merge that
   reorders it changes nothing semantically. Do not resolve a git conflict by
   interleaving — concatenate, then dedupe by exact id+content.
5. Verify after every merge with
   `python3 scripts/context.py evidence --all`, and check that no id appears
   twice with `status: active`.

The same applies to `HANDOFF.md`: it is current state, so a merge keeps both
branches' sections and reconciles only the "Next engineering task" ordering.

## Established by evidence

Treat these as measured, not as opinion. Each is reproducible from the cited
artifact or from the code line given.

1. **The ranker's volume term has two different roles.** `Ranker.score`'s
   `12.0 * volume` uses `math.prod(candidate.size)`, which is invariant under
   all six orientations and independent of position. *Within one item* it is
   therefore a dead vote: it cannot discriminate between that item's candidate
   placements or poses. *Across items* — which is what Task B does every step
   — it is an active large-item-first bias. Do not quote it as inert without
   that scope. The remaining position terms are
   `2.0*support + 0.35y - 0.12|x| - 0.18*z*mass`; in the run 30340049061
   traces `support` was 1.00 for the candidates that were actually selected,
   which is an observation about that run's selected set, not a property of
   the whole candidate population or of release candidates.
2. **The preview term is the same old score.** In `lookahead_rank_key`,
   `best_next_score` is the immediate `Ranker.score` of the best next
   placement, so `weighted` computes `q_old(a) + gamma * q_old(a')`. It is not
   the theory's `V_hat(sigma(T(s,i,a)))`.
3. **In run 30340049061 the three selection modes degenerated to the same
   action sequence.** Of 2,493 leaf fields, 135 differ and all of them are
   search-effort or timing counters; every placement-relevant field (placed,
   fill, kind, cog, valid, safe) is equal across `weighted`, `depth2` and
   `pool_resilience`. The mechanism is feature saturation: `residual feasible
   = 1.000` throughout, so both lexicographic first keys are constant and the
   modes fall back to score comparisons. **This does not show that preview
   value contributes nothing in general.** It shows that these three keys,
   with this implementation, on this run, did not change the choice. A real
   state value `V_hat(sigma(s'))` is untested.
4. **On one snapshot, widening anchor enumeration alone would not have
   changed the choice.** Anchor recall run 30513511959, case 000 step 13: the
   oracle found 42 physically-settled candidates, the anytime search reached 7
   (recall 0.167), yet `best_score_regret = 0.0`. Scope this narrowly — it is
   one snapshot, with the score held fixed, about *candidate* enumeration. It
   says nothing about which items enter the search (see 5).
5. **Item-level coverage was the dominant bottleneck at pool 40.** The
   class-aware coverage change moved placed 10.67 -> 17.00 and fill
   14.818 -> 24.531, with priority C1 going 0% -> 81.2%. Search breadth *in
   the item dimension* is a live issue, not a closed one. Do not merge this
   with 4: 4 is about candidates for a chosen item, 5 is about which items are
   considered at all.
6. **The current failure is a release settle topple**, not a transport
   collision. Case 000 fails at step 15 with settle 0.871 m / 90.3 deg, case
   001 at step 4 with 0.638 m / 90.0 deg, both `valid: true, safe: false`,
   both on `release_candidate`.
7. **Task B risk-gate ablation, `off` column** (run 30528431757, weighted +
   class_aware, 3 replicates per cell). `off` is the currently adopted
   configuration; `shadow` is instrumentation validation and `enforce` is a
   not-adopted ablation.

   | Pool | placed mean | fill mean |
   | ---: | ---: | ---: |
   | 10 | 17.00 | 17.018 |
   | 20 | 18.00 | 23.161 |
   | 40 | 17.00 | 24.531 |

   These are the risk-ablation `off` cells. For the standalone class-aware
   effect use the dedicated legacy/class-aware comparison run instead.

## Not established

- Whether a real graded state-value `V_hat(sigma(s'))` helps. The binary
  1-ply feasibility stays saturated even under the rich search
  (lookahead-modes-degenerate-rich-search), so the question is now
  sharper: the future term must be graded; no graded estimator has been
  tried yet.
- Whether any hard gate can work. What was rejected is **enforce with the
  current static features and thresholds**, not hard rejection as a form. If
  the replay dataset identifies a dangerous region with a very low false
  rejection rate, a narrow hard reject stays on the table.
- The replay dataset smoke-test numbers are a pipeline check, not results.

## Recent integrated work (originally `claude/release-counterfactual-replay`, merged into the trunk)

`cfbef6b` — telemetry corrections:

- Completed the `selected_*` 2x2 over selected release candidates. The
  reject-and-dangerous cell (TP) previously fell through both branches in
  `summarize_task_b.py` and was dropped. All four cells, the reject total and
  the reject failure rate now exist, and every emission point states the
  selection conditioning.
- Removed `initial_tilt_deg` from the gate rules. Every commandable
  orientation is axis-aligned, so it is identically 0.0 and the `initial_pose`
  reason could never fire; its threshold gated nothing. The field stays for
  schema stability and is reported as `unavailable_placeholder` through
  `feature_availability`.
- Split the physical labels: rotation, 3D displacement, horizontal
  displacement, placed-safe, valid, included, plus the continuous angle and
  xy/z displacements. `physically_dangerous` remains only as the historical
  composite.

`6f9d272` — `scripts/build_replay_dataset.py`, the stratified counterfactual
replay dataset. See `docs/REPLAY_DATASET.md`. One row per sampled candidate,
joining `(s, a, Phi, Q, selected)` with `(x_plus, delta_theta, d_xy, d_z, Y)`,
carrying its stratum and inclusion probability.

## Current live policy and scores (2026-08-01)

The 2026-07-30 sections above describe the pre-risk era. The shipped
defaults in `agent/agent.py` are now:

    Q_old - 1.0 * P_rot(mech-dev-v1) - 0.5 * P_slide(slide-dev-v1)
    + packed-AABB cache (6.4x candidate throughput)

- Rotation model: mechanics features (MATHEMATICAL_MODEL 5.2.1), frozen
  after the one-shot final_holdout evaluation (rotated AUC 0.903
  [0.761, 0.980]). final_holdout is OPENED and no longer an unseen split.
- Slide model: S0 equivariant local-frame logistic (validation AUC
  0.884); lambda 0.5 adopted 2026-08-01 on the 7-case aggregate after
  the rich search reversed the starved-search rejection.
- Regression guard: `reports/benchmarks/baseline.json` (current-default
  episodes; dev 5 configs placed 88 / fill 114.6). Any algorithm change
  reruns `run_risk_ablation.py --arm base` and must not degrade it
  unexplained.
- **Task A only** (offline `optimize`), adopted 2026-08-02 as ADR-002:
  `OFFLINE_DRY_RUN_ATTEMPTS_PER_ITEM=128`,
  `OFFLINE_PAIR_MACRO_BUDGET_SECONDS=0.5`. This does not touch the online
  policy, so none of the Task B numbers above move. That guard is a test,
  not a claim: `test_offline_budget_never_reaches_the_online_policy`.
- History and constraints: `docs/RELEASE_RISK_PROTOCOL.md` section 8;
  measured facts in `context/evidence.json` (the source of truth; the
  prose above is older than several supersessions).

## Latest experiment: deadline-reserved rescue scan (rejected)

Branch `experiment/rescue-scan` implements a default-OFF rescue ablation and
preserves all three Linux runs under `reports/rescue-scan/`. Static replay was
promising (37/37 late snapshots recovered), but the physical runs rejected
the architecture:

- 0.9 s reserve: base/rescue 83/75 placed, 100.32/86.98 fill.
- 0.2 s reserve: base/rescue 80/74 placed, 98.00/88.02 fill.
- trace run: base/rescue 82/78 placed, 100.32/94.25 fill.

The trace run is decisive: b001-k20 and b001-k30 each entered rescue once,
but returned zero rescue actions and still emitted one fixed protocol
fallback. b000-k20 regressed by two placements even though rescue never
triggered, isolating the loss to time removed from the primary search. Do not
enable this feature or tune its reserve further.

The next search experiment should change the primary anytime first pass:
visit one release unit as well as one settled unit for every included item,
so the normal incumbent is established before the deadline. Keep this
separate from Ranker/risk changes and compare fallback count plus placed/fill.

## Latest experiment: cross-step incumbent survival (fallback use rejected)

Branch `experiment/cross-step-incumbent` implements the first measurement
stage of a no-reserved-time fallback design. The normal search retains the
top two accepted candidates per stable item and per settled/release kind,
excludes the selected item, then revalidates those commands against the next
observed state. `CROSS_STEP_INCUMBENT_MODE=off` is the default and preserves
the shipped path; `shadow` records survival and cost but never returns a
carried action. `enforce` is deliberately absent.

Actions run 30707120494 completed 5 base + 5 shadow development episodes.
Across 76 shadow decisions, 702/1,603 retained candidates (43.8%) survived the
complete next-state static contract. Revalidation cost 37.7 ms/step on
average, max 145 ms, and crossed the internal deadline once. The sole
protocol fallback occurred in b001-k30 in both arms. At shadow step 16 all 18
retained candidates still had visible items but zero were valid: 17 failed
`corridor`, one `static_geometry`. `would_prevent_protocol_fallback=0`.

Therefore score-top2 cross-step carryover is rejected as the fallback
guarantee; keep the default `off` and do not add `enforce`. The 43.8% general
survival signal leaves a separately-testable warm-start/diversity use open,
but it did not cover the fatal state. Compact result:
`reports/cross-step-incumbent/history/30707120494/summary.{md,json}`. Contract:
`docs/CROSS_STEP_INCUMBENT.md`.

## Latest experiment: graded visible-pool rollout (signal yes, enforce rejected)

Branch `experiment/visible-pool-rollout` implements the first graded Ranker
future term without changing live selection. `VISIBLE_POOL_ROLLOUT_MODE=off`
is the default; `shadow` collects the best accepted candidate per stable item,
selects a Top-K diverse across `(dimensions, mass, soft, priority)` classes,
and evaluates each with a fixed anchor-attempt budget. The proxy rollout
prefers settled support and does not recursively use Q_live as its main key.

On the known b000-k20 step-9 divergence, the historical item-17 action kept
one additional settled placement (item 28, 0.08 m3), while item 28 kept zero.
The ordering was unchanged at attempt budgets 64/128/256/512. The current
policy's live class-diverse shadow on the same snapshot cost about 0.15 s,
did not alter the returned item-5 action, and graded items 5/17/28 as 2/1/0
future settled placements.

Linux screening run 30708961145 (after preventing shadow from warming the
production Z-interval cache) observed 79 decisions. The value was
non-degenerate on 39 (49.4%), proposed a different item on 17 (21.5%), and
cost 102.8 ms/step average / 398.3 ms max. Shadow remained telemetry-only.
Its aggregate was placed +0.4 / fill +0.674 versus the separately executed
base, but the base mean itself moved 16.2 -> 14.6 between the two screening
runs; do not read the single-run arm difference as an algorithm effect. See
`docs/VISIBLE_POOL_ROLLOUT.md`, `reports/visible-pool-rollout/`, and Actions
run 30708961145.

The repeated enforce test is now complete. The final implementation changes
an action only when its rollout key strictly improves on the selected action
and its `Q_live` loss is at most 0.15. Across eight configurations and three
repeats per arm (Actions 30716558143), same-run totals regressed from placed
137.667 / fill 167.881 to 131.000 / 151.656. Development totals regressed
84.000 / 104.239 to 79.333 / 95.233. b000-k20 and k40 improved, but b000-k15
lost six placements in every repeat. Keep the default `off`; do not adopt or
tune the band without first explaining the b000-k15 first divergence.

The discriminator itself remains real but is early-heavy: 138/240 step 0-9
observations were non-degenerate, versus only 2/166 later observations. It
cost 111.1 ms/step on average (617.6 ms max). Immediate candidate risk is
already in `Q_live`; rollout risk contains future transitions only. The proxy
rollout is not the current Q_live policy, so no textbook policy-improvement
guarantee applies.


## Latest experiment: Task A bounded offline rollout (ADOPTED)

The one adoption on this list — everything above it was rejected or kept as
telemetry. Branch `experiment/task-a-rollout-transfer`, contract
`docs/adr/ADR-002-bounded-offline-dry-run.md`, design and full run history
`docs/TASK_A_ROLLOUT_TRANSFER.md`.

The transfer that worked was **not** porting Task B's online three-step
rollout into Task A. Task A already evaluates complete orders with
`DryRunEvaluator` under the same lexicographic objective, so it does not need
another score. What it needed was for that search to actually run.

It was barely running. ADR-001 §5 assumed a slow placement core would just
reduce the evaluation count, but time control was a global deadline with no
per-item bound, so an unplaceable item's scan made one dry run cost ~35 s. At
the official 150 s budget the shipped agent evaluated **3.0 of its allowed
1000 complete orders** — the seed plus two neighbours, neither of which
improved placed count or first-failure index.

Bounding each item at 128 deterministic anchor attempts and capping pair-macro
construction at 0.5 s, adoption run `30717998654` (bundled case 000, official
budgets, 3 repeats per arm):

| arm | placed | fill | evaluated orders | optimization s |
|---|---:|---:|---:|---:|
| base (legacy) | 20 / 20 / 20 | 29.298 | 3.0 | 112.1 |
| adopted | 25 / 25 / 25 | 34.949 | 51.3 | 147.3 |

CoM height 0.753 → 0.735 m, near-misses 0 in both arms, policy time held at
about 6.51 s. The adopted arm's fill is min = max over three repeats, so the
order and the physics reproduced exactly; base's fill varied 27.541–30.176 on
a constant placed count. Compact result and per-repeat analysis:
`reports/task-a-rollout/history/30717998654/{summary,analysis}.md`.

Confirmed post-flip by run `30719944050`, which re-ran the matrix with the
`default` arm (no `OFFLINE_*` variable set, i.e. the submission path) instead
of `bounded128`. Every outcome column matched, including the base arm's full
fill distribution; only search-effort counters moved. Three independent
executions now agree bit-for-bit on fill, so treat run-to-run variance as a
non-issue here — unlike the visible-pool screening, where the base arm itself
moved 16.2 → 14.6 between runs.

Two things this did **not** establish, both easy to overstate:

- The offline proxy is a **relative order selector**, not a score. It
  predicted 23 where physical execution reached 25, and its error changes
  sign between arms. Do not report or target proxy values.
- The **fallback problem is untouched.** Both arms end with `is_valid` and
  `is_placed_safe` false, so neither is a passing episode. The adopted arm
  just reaches placement 25 before it dies instead of 20.

Also unmeasured: any second case (source 001 was a synthetic conversion and
was dropped from the adoption matrix), budgets at 256+, and an
item-count-adaptive budget. Only 2.7 s of the internal budget is left over,
so re-measure this table after any placement-core slowdown — the Task B
benchmark will not catch it.

Because the shipped default is now the treatment, the `base` arm in
`scripts/run_task_a_rollout.py` pins the legacy values explicitly rather than
unsetting the variables. An arm that merely unsets them would measure the
treatment and report a null result. The runner's new `default` arm unsets
everything and therefore measures exactly what a submission does.

## Latest experiment: stride / item-cap line (parallel branch)

Merged from `claude/stride-endgame-saturation-test-gqssix`. This line
ran concurrently with the Task A work above and neither knew about the
other; the sections are kept side by side per the ledger merge rules.

**That 1.2% late figure has now been diagnosed and it is mostly an
instrument fault.** `docs/ROLLOUT_SATURATION.md` and
`reports/rollout-saturation/local-20260801`: on the 48 committed replay
snapshots (37 at step >= 10), only 4/37 late states have nothing for the
rollout to find. The shipped setting reaches a future placement on 8/37; the
same per-step attempt cap with `stride 8` reaches one on 28/37. The failure
is the anchor **scan order**, not the budget - `budget-512` spends about
8.4x the attempts and reaches only 12/37, and 17 late snapshots are reached
by stride and not by budget (1 the other way). Read non-degeneracy and
future-placement separately: the budget arms score 36/37 non-degenerate
purely on release-risk tie-breaks with no reach. This is a diagnosis of the
measurement only. `VISIBLE_POOL_ROLLOUT_MODE` stays `off` and
`VISIBLE_POOL_ROLLOUT_STRIDE` defaults to 1; the enforce rejection stands.
**The b000-k15 re-run is done, physically, and it reverses that case.**
`reports/rollout-saturation/b000-k15-stride4/` (local PyBullet, 3 repeats per
arm): base 17.000 placed / 23.119 fill, `rollout_enforce` 11.000 / 13.228
(bit-identical across repeats, reproducing the reported -6.000 exactly), and
`rollout_enforce_stride4` 20.333 / 26.018 — **+3.333 placed over base**.

The mechanism is not the assumed one. Both enforce arms take the *same* first
divergence at step 3. At stride 1 the rollout then goes blind (one
enforcement in the whole episode, `step >= 10` non-degeneracy 0/2) and the
trajectory dies at step 11; at stride 4 it keeps discriminating (5/10) and
enforces again at steps 5, 8 and 13. **The -6 was a first action taken and
then abandoned by an instrument that could no longer see**, not a wrong first
action. Cost 77.1/184.7 -> 176.0/278.8 ms mean/max, still under the 617.6 ms
maximum the enforce ablation already tolerated.

This is **one configuration**. The enforce rejection was made on eight, so it
is not revisited yet. The decision point that would revisit it is a repeated
eight-configuration ablation with the `rollout_enforce_stride4` arm (already
wired into `run_risk_ablation.py`) plus the
`reports/benchmarks/baseline.json` regression guard. Until that runs,
`VISIBLE_POOL_ROLLOUT_MODE` stays `off` and `VISIBLE_POOL_ROLLOUT_STRIDE`
stays 1.

Method note now in the ledger as
`offline-snapshot-sweeps-cannot-answer-outcome-questions`: the offline sweep
over saved b000-k15 snapshots said the enforce decision was stride-invariant,
and it was — *at those states*. Saved snapshots come from the base
trajectory, so once an arm diverges the states it visits are not in the set.
Offline sweeps diagnose an instrument; only a physical run decides an
outcome.

### The larger implication is for the live search, not the rollout

The rollout is the smaller consumer of this fix. **The live candidate search
runs through the same `support_plane` generator with the same stride-free
deterministic scan order**, so the same hole is present there, one layer up
and with far more leverage:

- the post-cache coverage hole (accepted anchors clustered in
  `x in [-0.34, 0.83]`) is the live-search symptom of exactly this scan
  order;
- `transport-deaths-are-fallback-poison` in the ledger already traced 45% of
  episode endings to the fixed-coordinate `unsafe_protocol_fallback`, which
  fires when the search returns **no** candidate - a no-candidate branch that
  a wider scan makes rarer.

Both were previously blocked on stride not existing on the shipped generator.
**That line has now been built and screened, and it is rejected as a
default** — see the next section.
## Latest experiment: Task A bounded offline rollout (ADOPTED)

The one adoption on this list — everything above it was rejected or kept as
telemetry. Branch `experiment/task-a-rollout-transfer`, contract
`docs/adr/ADR-002-bounded-offline-dry-run.md`, design and full run history
`docs/TASK_A_ROLLOUT_TRANSFER.md`.

The transfer that worked was **not** porting Task B's online three-step
rollout into Task A. Task A already evaluates complete orders with
`DryRunEvaluator` under the same lexicographic objective, so it does not need
another score. What it needed was for that search to actually run.

It was barely running. ADR-001 §5 assumed a slow placement core would just
reduce the evaluation count, but time control was a global deadline with no
per-item bound, so an unplaceable item's scan made one dry run cost ~35 s. At
the official 150 s budget the shipped agent evaluated **3.0 of its allowed
1000 complete orders** — the seed plus two neighbours, neither of which
improved placed count or first-failure index.

Bounding each item at 128 deterministic anchor attempts and capping pair-macro
construction at 0.5 s, adoption run `30717998654` (bundled case 000, official
budgets, 3 repeats per arm):

| arm | placed | fill | evaluated orders | optimization s |
|---|---:|---:|---:|---:|
| base (legacy) | 20 / 20 / 20 | 29.298 | 3.0 | 112.1 |
| adopted | 25 / 25 / 25 | 34.949 | 51.3 | 147.3 |

CoM height 0.753 → 0.735 m, near-misses 0 in both arms, policy time held at
about 6.51 s. The adopted arm's fill is min = max over three repeats, so the
order and the physics reproduced exactly; base's fill varied 27.541–30.176 on
a constant placed count. Compact result and per-repeat analysis:
`reports/task-a-rollout/history/30717998654/{summary,analysis}.md`.

Confirmed post-flip by run `30719944050`, which re-ran the matrix with the
`default` arm (no `OFFLINE_*` variable set, i.e. the submission path) instead
of `bounded128`. Every outcome column matched, including the base arm's full
fill distribution; only search-effort counters moved. Three independent
executions now agree bit-for-bit on fill, so treat run-to-run variance as a
non-issue here — unlike the visible-pool screening, where the base arm itself
moved 16.2 → 14.6 between runs.

Two things this did **not** establish, both easy to overstate:

- The offline proxy is a **relative order selector**, not a score. It
  predicted 23 where physical execution reached 25, and its error changes
  sign between arms. Do not report or target proxy values.
- The **fallback problem is untouched.** Both arms end with `is_valid` and
  `is_placed_safe` false, so neither is a passing episode. The adopted arm
  just reaches placement 25 before it dies instead of 20.

Also unmeasured: any second case (source 001 was a synthetic conversion and
was dropped from the adoption matrix), budgets at 256+, and an
item-count-adaptive budget. Only 2.7 s of the internal budget is left over,
so re-measure this table after any placement-core slowdown — the Task B
benchmark will not catch it.

Because the shipped default is now the treatment, the `base` arm in
`scripts/run_task_a_rollout.py` pins the legacy values explicitly rather than
unsetting the variables. An arm that merely unsets them would measure the
treatment and report a null result. The runner's new `default` arm unsets
everything and therefore measures exactly what a submission does.


Other open fronts, in order: transport_invalid deaths (37% pre-cache;
re-run `scripts/analyze_terminal_failures.py` post-cache to requantify),
S1/S2 of the slide ladder (patches + encoder plumbing ready in
`reports/slide-patches/`, Gated Iota enters at S2).

## Where this work actually is (read before proposing a board-value idea)

The decision pipeline is

    visible items -> examined items -> candidate placements -> ranking -> a -> s'

A board-value theory — "did this placement leave a container that accepts
unknown future baggage?" — lives in the **last** arrow. Everything measured
so far lives in the first two. `MAX_POOL_ITEMS_EVALUATED = 10` against a
40-item visible pool is a first-arrow fact, and the anchor/stride/interleave
work is a second-arrow fact.

So the item-cap result says nothing about board value. It measured
`delta placed`, not `delta future receptivity`. A placement that raises the
short-horizon count while wrecking the board scores **positive** on that
metric. Likewise the kappa line measured `|A(s)|` and its risk-weighted
total, which is too coarse to be a board value; its negatives close "option
count as a board value", not "board value".

**The entrance is a paired comparison from the same state and the same
candidate set, varying only the board-shaping term.** Today's measurements
give that experiment a quantified spec, and it is demanding:

| requirement | measured constraint | source |
| --- | --- | --- |
| signal density | only **4.8%** of Q-band sibling pairs differ in short-horizon outcome (12 of 252) | Stage B |
| episode noise | placed sd **2.3–2.7**, range 7–9, per source | stream-variance |
| evaluator cost | the rollout board term cost 77–176 ms/decision, and the search is already deadline-limited on **83–87%** of steps | b000-k15 run, stream-variance |

Three consequences a design has to respect:

1. Holding the candidate set fixed is **not sufficient**. A board term that
   costs time changes how much search happens afterwards, which reintroduces
   the confound it was meant to remove. Either evaluate the term offline on
   a frozen candidate set, or charge both arms the same effective budget.
2. At 4.8% signal density, an immediate-horizon sibling test needs roughly
   20 pairs per decided pair. Short horizons are the wrong place to look.
3. Episode-level differences under about 2 placed are not resolvable without
   the paired permutation design.

**The harness for the entrance already exists.**
`scripts/measure_kappa_siblings.py` is exactly the shape: one state, siblings
drawn from one candidate set, a state functional evaluated per sibling, sign
agreement scored against outcome components kept separate. Swapping the
functional is the change. What is missing is not machinery — it is
(a) a board functional worth testing, and (b) a **long-horizon paired
label**, because placed-to-go is confounded by step and occupancy, immediate
survival is unrelated to option counts, and 95% of siblings tie in the short
run.

The affordable version of (b): run an episode to completion from each
sibling successor. PyBullet runs locally at roughly 4 minutes per episode, so
8 states x 3 siblings is about 1.5 hours and yields genuinely paired
long-horizon deltas. That, not another state descriptor, is the next thing
that would put this work inside the board-value question rather than in
front of it.

## Latest experiment: live scan interleave (rejected as a default)

`docs/LIVE_SCAN_INTERLEAVE.md`,
`reports/live-interleave/local-20260801-screening/`.

The live candidate search runs through the same `support_plane` generator as
the rollout, so the diagnosed scan-order hole is present there too. It needs a
**different** instrument, and this distinction is the durable part of the
work: the rollout's future search is capped by an attempt count it can never
exhaust, so a `stride` that *drops* anchors is free reach; the live search is
capped by a deadline it often *does* exhaust, so dropping anchors there would
lose candidates the current search finds. `LIVE_SEARCH_INTERLEAVE` therefore
**permutes** the anchor order instead of subsampling it — at exhaustion the
candidate set is identical, and only what a truncated search reaches first
changes.

Local screening, one repeat per cell, `base` vs `live_interleave4` on the
five development configurations:

| case | base placed | il4 placed | delta placed | delta fill |
| --- | ---: | ---: | ---: | ---: |
| b000-k15 | 17 | 14 | -3 | -10.464 |
| b000-k20 | 16 | 12 | -4 | -4.483 |
| **b000-k40** | 14 | 19 | **+5** | **+6.078** |
| b001-k20 | 18 | 17 | -1 | -1.281 |
| b001-k30 | 18 | 18 | 0 | -2.597 |
| total | 83 | 80 | **-3** | **-12.747** |

`LIVE_SEARCH_INTERLEAVE` stays 1.

**The per-config split is the finding, not the total.** The single winner is
`b000-k40` — the configuration `aabb-cache-guard-mixed` already calls
search-starved, and the same one that gained +10 from the packed-AABB cache
while b000-k20 lost 12. Two independent coverage interventions, one enlarging
the candidate set and one only reordering it, now produce the same
per-configuration signature. Search diagnostics exclude reduced recall as the
cause: both arms are deadline-limited on most steps, the unit completion
ratio does not fall, and no episode ended in a no-candidate branch the base
arm avoided. What changed is which candidate a truncated search settles on,
and so which trajectory is taken.

**This is the second measurement saying selection quality is blocking for
coverage work**, not the reverse. Coverage interventions are now
twice-observed to redistribute placements rather than add them while the
utility stays defective (`Ranker` volume dead vote, `q + gamma*q` lookahead).

Scope and cautions:

- One repeat per cell; the two smallest deltas are on the
  timing-nondeterministic b001 cases.
- Local `base` totals (83 / 104.742) are **below** the registered development
  baseline (88 / 114.6). The search is deadline-limited, so absolute totals
  are machine-dependent — only base-vs-arm inside one run is comparable. That
  caveat binds hardest on exactly this kind of change, whose whole effect is
  about what a deadline truncates. Do not read the local base number as a
  regression.
- This rejects the interleave as an unconditional default. It does not
  retract the scan-order hole, which stays measured and real.

Two designs remain open and are untested: interleaving only when the search
is actually starving (a conditional, not a tuning of this knob), and rotating
`stride_offset` per rollout step or search round so successive passes cover
complementary phases at the same total budget. The measured phase arms
(`stride-4+1..+3`) differ by at most one snapshot, which suggests phases are
near-interchangeable and rotation would be cheap — but that is an inference
from spread, not a measurement.

## Important invariants

- Candidate placement uses container-local coordinates; packed observations
  and container planes use world coordinates; conversion changes only the
  container X offset.
- Shelf geometry is derived from simulator dimensions, never hard-coded.
- Internal boundary guard 16 mm; transport/lateral clearance 16 mm; vertical
  contact with a valid support surface is allowed.
- Settled quaternion determines the subsequent packed-item AABB.
- Soft and priority items are not future support surfaces.
- Block templates are replayed item by item through the common placement core.
- The release risk gate is an experiment layer: it must annotate the candidate
  population, never filter its own denominator.

## Do not

- Do not edit the official simulator to make the agent pass.
- Do not report `selected_*` counts as the gate's precision/recall.
- Do not restate a scoped negative result as a general one. Evidence 3 and 4
  are about specific keys and one snapshot; neither closes preview value or
  search breadth as topics.
- Do not use `initial_tilt_deg` as a gate rule or a learned feature while it
  is constant.
- Do not run the replay dataset with `risk_gate_mode=enforce`; it removes the
  rejected candidates the dataset exists to label.
- Do not call a physics run successful because the process returned zero.
- Do not treat proposed theory as an implemented contract.
- Do not commit the large artifacts listed in `docs/DRIVE_SOURCES.md`.

## Operational notes

- **Python 3.12 is required.** `simulator/src/ground_handling/validator.py`
  uses PEP 701 nested-quote f-strings; 3.11 fails at import with
  `SyntaxError: f-string: unmatched '['`.
- Windows Python 3.12 cannot readily build PyBullet 3.2.7 without MSVC. Use
  the Actions Ubuntu CPU jobs for routine full validation.
- The anchor oracle bot commits results to `experiment/anchor-recall-oracle`,
  so `git fetch origin && git rebase origin/experiment/anchor-recall-oracle`
  before pushing to it.
- Some sandboxed sessions cannot reach `*.blob.core.windows.net`, which is
  where Actions artifacts are served; artifact contents must then be supplied
  by hand. Ref deletion may also be blocked.
- Stale remote branch `claude/nedo-3d-bpp-report-t40pjt` (`8796a6d`, a
  `main`-based cleanup) is discarded and should be deleted server-side.
