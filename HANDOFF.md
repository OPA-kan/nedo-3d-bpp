# Handoff for the next model

Updated: 2026-07-30 JST

## Start here

Repository: https://github.com/OPA-kan/nedo-3d-bpp

- **Live trunk is `experiment/anchor-recall-oracle`, not `main`.** `main` is
  frozen at `d3986a9` and is ~39 commits behind. Reading `main` will give you
  an `agent/agent.py` that is 2,629 lines out of date.
- Current review branch: `claude/release-counterfactual-replay`
  (`6f9d272`, branched from `a410943`), awaiting read-only review.
- Run `git fetch --all --prune` before judging what exists.

```powershell
python scripts/context.py list
python scripts/context.py show handoff
```

Do not load the whole repository. Select a profile and add `--full` only when
source-level detail is needed. New here: the `replay-dataset` profile.

## User's goal

A competitive CPU-first agent for the NEDO airport-baggage constrained 3D
bin-packing competition. GitHub is the source of truth for code, reasoning,
simulator snapshots, tests, and reports.

## Where results live

Persistence differs per experiment **by design** — heavy artifacts stay in
Actions artifacts so git does not bloat; only compact summaries are committed.

| Experiment | Artifact | Auto-committed |
|---|---|---|
| Task B benchmark | yes | **no** (`contents: read`) |
| Anchor recall oracle | yes | compact summary only |
| Lookahead comparison | yes | compact summary/history |
| CPU verification | yes | no |

So the headline off/shadow/enforce numbers are **not in git**; they are
downloaded from the Task B aggregate artifact. `reports/lookahead/latest-summary.json`
is named "latest" but stopped at 2026-07-28 — do not read it as current.

## Established by evidence

Treat these as measured, not as opinion. Each is reproducible from the cited
artifact or from the code line given.

1. **The immediate ranker's volume term is inert.** `Ranker.score`'s
   `12.0 * volume` uses `math.prod(candidate.size)`, which is invariant under
   all six orientations and independent of position. It cannot discriminate
   between candidate placements; it only biases *which item* to take when the
   pool has several. The live position score is
   `2.0*support + 0.35y - 0.12|x| - 0.18*z*mass`, and `support` is 1.00 for
   every chosen candidate, so depth, |x| and height x mass carry the decision.
2. **The preview term is the same old score.** In `lookahead_rank_key`,
   `best_next_score` is the immediate `Ranker.score` of the best next
   placement, so `weighted` computes `q_old(a) + gamma * q_old(a')`. It is not
   the theory's `V_hat(sigma(T(s,i,a)))`.
3. **The three selection modes choose identically.** Lookahead run
   30340049061: of 2,493 leaf fields, 135 differ and all of them are
   search-effort or timing counters. Every placement-relevant field (placed,
   fill, kind, cog, valid, safe) is equal across `weighted`, `depth2` and
   `pool_resilience`. `residual feasible = 1.000` saturates the lexicographic
   first keys, so both lexicographic modes degenerate to score comparisons.
4. **Score does not predict survival.** Anchor recall run 30513511959,
   case 000 step 13: the oracle found 42 physically-settled candidates, the
   anytime search reached 7 (recall 0.167), yet `best_score_regret = 0.0`.
   Widening the search alone will not change the chosen action.
5. **The current failure is a release settle topple**, not a transport
   collision. Case 000 fails at step 15 with settle 0.871 m / 90.3 deg, case
   001 at step 4 with 0.638 m / 90.0 deg, both `valid: true, safe: false`,
   both on `release_candidate`.

## Not established

- **Gate-wide precision/recall.** The `selected_*` confusion matrix is
  conditioned on the ranking having selected the candidate; the selected set
  is the top of the ranking, not a sample. More benchmark replicates will not
  fix this. Only the stratified replay dataset can estimate gate-wide
  behaviour.
- Whether a real state-value `V_hat` would beat the current preview term.
- The replay dataset smoke-test numbers are a pipeline check, not results.

## Recent work (branch `claude/release-counterfactual-replay`)

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

## Next engineering task: the algorithm

The ordering is deliberate. Do **not** start by rewriting the immediate score.

1. Identify `Phi(s,a) -> (delta_theta, d_xy, d_z, Y)` from the replay dataset.
   Until candidate physical safety is predictable, changing the ranker only
   moves which unsafe candidate gets chosen.
2. Only then re-decompose immediate ranker vs preview value. Note that
   evidence item 3 already shows the preview contribution is currently zero,
   so the question is whether `V_hat` can be made a real state value, not
   whether to reweight the existing terms.
3. Facts 1 and 2 above are the concrete defects to design against: an inert
   volume term, a non-discriminating support term, and a future term that
   re-applies the same positional bias.

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
