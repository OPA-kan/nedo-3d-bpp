# Handoff for the next model

Updated: 2026-08-01 JST

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
- History and constraints: `docs/RELEASE_RISK_PROTOCOL.md` section 8;
  measured facts in `context/evidence.json` (the source of truth; the
  prose above is older than several supersessions).

## Ranker mis-ranking decomposition (implemented 2026-08-01)

`scripts/analyze_ranker_divergence.py` now finds the first action divergence,
reconstructs either a JSONL sample or the unlimited policy-item oracle, and
emits every requested score term, old/live candidate and item ranks, selected
margins, three-valued search-only evidence, and a static next-state candidate
survival proxy. Usage and limitations are in `docs/RANKER_DIVERGENCE.md`.

The first full report is
`reports/ranker-divergence/b000-k20-step009-full/report.md` (3,800 candidates):

- old selection item 17: Q_old -0.1614, Q_live -0.4481, live ranks 75/9/6,
  next-state survival proxy 2,712;
- rich selection item 28: Q_old -0.1414, Q_live -0.3465, live ranks 13/1/13,
  next-state survival proxy 1,140;
- the rich action wins immediate Q_live by 0.1016 but loses 58% of the static
  residual candidate population. This is a concrete mis-ranking candidate,
  not yet a physical counterfactual result.

The report deliberately does not claim item 28 was new-search-only. The old
source contains only 25 stratified rows, so absence outside that sample is
unknown. A fresh 6.5 s rerun is recorded separately and cannot replace the
historical deadline schedule; selected actions themselves are forced-in as
primary reachability evidence.

## Future-option tie-break experiment (2026-08-01)

Branch `experiment/future-option-tiebreak` implements the first default-off
graded residual-option selector. It does not add a learned value or change the
live ranker. The contract is:

    item-diverse immediate representatives
    -> Q_live gap <= 0.15
    -> fixed 32-probe future-option tuple
    -> lexicographic tie-break

The tuple is `(feasible items, feasible item-orientations, distinct support
regions, valid sampled probes)`. The placed item is removed and no unseen
future arrival is introduced. Full details are in
`docs/FUTURE_OPTION_TIEBREAK.md`.

Fresh geometry-only replay of the saved `b000-k20` step-9 observation:

- feature OFF: item 5 in 3/3 runs, 5.005--5.013 s;
- feature ON: item 17 or 21 in 3/3 runs, 5.813--5.906 s;
- fixed future stage: 0.803--0.894 s;
- item 17, which global top-K had starved, entered the item-diverse shortlist
  in every ON run.

The 17/21 variation comes from the existing deadline-driven generator feeding
slightly different probe populations, not from a variable future validation
budget. This does not reproduce the historical item-28 action.

Five-config Actions run `30684302181` completed all 10 episodes and persisted
`reports/future-option/history/30684302181/summary.{md,json}`. The feature
raised mean placed `16.4 -> 19.0` (82 -> 95 total) but reduced mean fill
`21.479 -> 18.806`. Per-case placed/fill deltas were: b000-k15 `0/-8.523`,
b000-k20 `+11/+3.731`, b000-k40 `0/-2.650`, b001-k20 `+3/+3.901`, b001-k30
`-1/-9.824`. This is one run per arm, so it is screening evidence. The default
remains OFF: feasible-item count has real signal, but alone it can preserve
many small-item options while destroying volume value.

The next shadow-only instrumentation is now implemented on the same branch.
It records item/pose equivalence classes, coarse corridor/action classes,
unique-class volume, maximum feasible volume, and deterministic greedy
static-conflict capacity. None of these fields changes `rank_key()`. On the
saved step-9 state, all fields saturated across the live 32-probe cohort. A
64-probe diagnostic exposed more spatial classes but item 17 and item 21 still
had identical greedy capacity `(2, 0.1934 m^3)`. See
`reports/future-option/b000-k20-step009-quotient-shadow*/` and
`docs/FUTURE_OPTION_TIEBREAK.md`.

Linux guard run `30692389788` passed all ten physical episodes after the
instrumentation change. Its independent five-config screen again showed the
same aggregate trade-off: placed `14.2 -> 16.4`, fill `18.042 -> 16.734`.
Individual case deltas moved substantially relative to the first screen, so
case-level claims remain unstable; the repeated count-up/fill-down direction is
the durable result. Compact output is in
`reports/future-option/history/30692389788/summary.{md,json}`.

## Next engineering task

Do not add the new descriptors to the rank. Corridor-stratified route-survival
telemetry is now implemented without changing the live probe population or
rank key. Its committed five-state screen evaluated 27 hypothetical placements
and 350 accepted probes: 169 survived, 181 were structurally lost, and 0 were lost
only to the transport corridor. A focused actual-geometry test confirms that
the `route_lost` channel detects a sweep-only blocker. This is useful negative
evidence, not an adoption result. The next route experiment should restore
exact pre-action states followed by `transport_invalid`; do not broaden the
saturated capacity proxy or alter the release-risk model to rescue it. See
`docs/ROUTE_SURVIVAL.md` and
`reports/future-option/route-survival-summary.{md,json}`.

Other open fronts, in order: transport_invalid deaths (reported post-cache
share about 45%; preserve the seven-case placed-count non-regression gate),
S1/S2 of the slide ladder (patches + encoder plumbing ready in
`reports/slide-patches/`, Gated Iota enters at S2), live stride
sampling port for further recall.

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
