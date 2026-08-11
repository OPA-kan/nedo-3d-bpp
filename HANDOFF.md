# Handoff — current state

Updated: 2026-08-10 JST. Repository state was re-audited after fetching every
remote branch. The live branch at the time of this audit is
`experiment/anchor-recall-oracle` after the temporal stride-4 shadow run.

## Start here

```powershell
git fetch --all --prune
git switch experiment/anchor-recall-oracle
python scripts/context.py show handoff
python scripts/context.py show operations
```

`main` is frozen and is not the implementation branch. Do not infer the live
branch from file size or age; verify the named branch after every fetch. The
2026-08-06 consolidation brought the true-envelope implementation and the
official transport-plane ruling together on the live branch. See
`docs/REPO_AUDIT.md` and `docs/BRANCH_INVENTORY.md`.

## Current implementation baseline

These are source defaults in `agent/agent.py`, not proposed settings:

| area | current default | status |
|---|---|---|
| release rotation risk | mechanical model, lambda 1.0 | adopted |
| release slide risk | lambda 0.5 | adopted |
| visible-pool coverage | `class_aware`, item cap 10 | adopted |
| Task A offline dry run | 128 attempts/item, pair macro cap 0.5 s | adopted |
| online first pass | 256 attempts/unit | adopted |
| anchor envelope | real container half-spaces (`ANCHOR_TRUE_ENVELOPE=1`) | adopted |
| lateral guard | 10 mm beyond transport clearance | restored after 2 mm failed |
| death-band fallback | off | officially rejected |
| release attribute hard guard | off | placed cost too large |
| anchor-space fallback | off | not adopted |
| temporal chunk ensemble | off | shadow measured; delay voting did not form consensus |
| structured placement pipeline | opt-in | contracts accepted; eager live materialization failed its physical negative control |

`agent/agent.py` and `simulator/agent.py` must remain byte-identical after an
agent change. The official simulator itself must not be changed to make an
agent pass.

## Active dataset branch: 3–5 step counterfactual graph

Branch `experiment/counterfactual-graph` starts from the latest observed-state
dataset line (`aebc4bd`) and is intentionally separate from the live agent.
The direction is fixed in `docs/COUNTERFACTUAL_GRAPH.md`: preserve bounded
multi-step futures as a deterministic DAG, not as independent one-step rows.
Nodes are settled residual states; edges are commanded placements with
separate physical and multi-axis labels. Sibling branches must share the same
future stream and fixed attempt budget.

The first slice is implemented but is not yet a physical H3 result:

- `scripts/counterfactual_graph.py` defines horizon 3–5, deterministic IDs,
  DAG state convergence, branch/node/edge budgets, atomic JSON output and an
  independent-env prefix replay contract.
- replay-dataset snapshots now retain the optimized item order, visible pool,
  stream offset, exact action prefix, future-stream ID and board fingerprint.
- prefix replay refuses to label a branch unless the reconstructed root
  fingerprint matches. PyBullet `saveState` alone is explicitly insufficient
  because it omits Python stream/container state.
- no ranker, policy default, simulator rule or final holdout was changed.

Next: add the bounded physical branch executor, beginning with branch factor
2–3 and horizon 3 on development/validation roots; verify independent-env
prefix identity in Linux CI before expanding to horizon 5. Raw graphs remain
artifacts, while compact manifests and aggregate evidence are committed.

## Official score history

| submission | total | fill | cog | stability | placement | soft | placed fraction |
|---|---:|---:|---:|---:|---:|---:|---:|
| submission22 | 17.581 | 29.276 | 14.224 | 20.721 | 4.45 | 7.65 | 0.434 |
| submission3334 | 23.246 | 31.413 | 21.505 | 29.424 | 10.85 | 12.65 | 0.452 |
| trueenvelope | **35.375** | **34.246** | **40.683** | **53.240** | **16.95** | **21.30** | **0.505** |
| deathband | 29.959 | 33.635 | 32.243 | 41.288 | 14.70 | 17.45 | 0.491 |

The best known official result is `trueenvelope` at 35.375. Its implementation
is now present on the live branch: commit `3b1635c` is an ancestor and
`ANCHOR_TRUE_ENVELOPE` defaults to 1. The old active ledger claim that the
trunk lacked this code has been superseded.

There is no checked-in `dist/submission.zip` in the current worktree. Build a
new artifact only from a freshly fetched live branch and record both commit
and SHA-256. Do not reuse hashes in old prose.

## Established by evidence

### Task A

- The bounded complete-order dry run is adopted. It raised the sample Task A
  result from 20 to 25 placements by increasing evaluated orders from about 3
  to about 51 inside the 150 s optimization budget.
- Increasing the evaluation ceiling beyond roughly 50 does not change the
  selected 41-item order on the measured case. The current bottleneck is not
  simply more offline evaluations.
- Order selection is lexicographic `DryRunResult.rank_key()`, effectively
  `(placed_count, placed_volume)` for most comparisons. The apparent fill and
  stability weights feed an unused `weighted_score()` and do not change
  behavior.
- The offline proposal oracle still does not use the same risk-adjusted
  placement policy as online execution. This is the open F8 contract gap.

### Task B

- Class-aware item coverage and first-pass depth 256 are adopted.
- Task B is wall-clock/runner sensitive. Compare arms on the same Linux runner;
  do not compare a local Windows run directly with committed CI baselines.
- Item-cap 16 was refuted after fixing a paired-control-floor bug. More visible
  items is not a current adoption candidate.
- The visible-pool graded rollout, future-option quotient, and route-survival
  tie-breaks produced useful telemetry but were rejected as live policies.
- Temporal chunk shadow runs at stride 1 and 4 established that delayed
  proposals can survive, but not that they agree.  Stride 4 raised scheduled
  proposals from 84 to 192 and statically valid proposals from 48 to 148;
  nevertheless, all 10 multi-origin steps had zero repeated action votes and
  zero repeated item votes.  Do not add an enforce mode for the current
  deterministic greedy rollout.

### Task C and common placement core

- Candidate proposal facts, named immediate/risk evaluation, selector policy,
  and simulator command are now separate contracts. A richer selector can
  consume one generated candidate stream without rerunning search or parsing
  an opaque score. The default path still executes the former scalar loop;
  fixed-work comparison at 128 and 512 attempts matched the pre-refactor
  action, ordered top three, scores, and attempt counts exactly. See
  `docs/PLACEMENT_PIPELINE.md` and
  `reports/placement-pipeline/parity.md`.
- The first physical negative control for that seam failed.  Fixed-work scalar
  versus rich evaluation was bit-exact at 128/512 attempts, but eager rich
  construction perturbed deadline-bound trajectories.  On `b000-k15`, six
  control runs were identical at 21 placements/fill 23.929; the structured arm
  averaged 18.333/20.849 and worsened three shake proxies, while improving some
  priority/terminal proxies.  Do not place a new Ranker on the eager
  per-candidate path.  Preserve scalar streaming and enrich only retained
  Top-K/selected candidates, then repeat the negative control.  See Actions
  `31356809615` and `docs/STRUCTURED_SELECTOR_EXPERIMENT.md`.
- The retained-only repair passed its 45-episode physical negative control.
  Candidate generation, scoring and heap/incumbent updates remain scalar;
  only the final decision or Top-K portfolio is enriched.  All per-case
  differences across placed/fill, CoM, shake, priority/soft, terminal state,
  policy time and attempt coverage stayed inside the pooled control spread.
  Structured telemetry appeared on 283/286 decisions and attempts/decision
  remained in the control regime.  Multi-axis shadow selection may now use
  this retained portfolio.  See Actions `31358020306` and
  `docs/RETAINED_SELECTOR_EXPERIMENT.md`.
- A post-selection multi-axis shadow is now an admissible instrument. It keeps
  priority/soft cover, routing, rotation/slide risk, support and predicted CoM
  separate, with no fabricated total. Run `31360283401` kept every reported
  case metric inside the pooled control spread and proposed a different
  retained action on 51/285 multi-candidate steps (14 different items). The
  earlier pre-lookahead placement failed because it consumed lookahead time.
- Conservative Pareto enforcement v1 is rejected. Run `31362302154` made 57
  substitutions and improved aggregate priority/soft cleanliness, but
  b000-k20 worsened topples and peak kinetic energy sharply and b001-k30 even
  worsened priority cleanliness. One-step static dominance is not
  trajectory-level dominance. Default `MULTI_AXIS_SELECTOR_MODE` stays `off`;
  see `docs/MULTI_AXIS_SELECTOR.md`.
- The box-derived anchor envelope was a real generator defect. Deriving bounds
  from the container half-spaces produced the largest measured improvement and
  the best official score.
- On the corrected true-envelope trajectories, the measured terminal boards
  are genuine capacity/support exhaustion, not another envelope-coverage bug.
- The latest structural finding is support exhaustion: at the c000-k1 fatal
  board, all 950 release candidates rest on soft or priority tops, and none
  clears the settled support threshold.
- The implementation contract is asymmetric: settled anchors exclude every
  soft/priority top, while release has no support test. The competition rule
  penalizes covering a *different* attribute, so neither path exactly matches
  the published rule.
- Elevated connected support cannot grow under the current candidate set in
  the measured states. A naive “reward support creation” term is closed.

### Residual-state learning data

- A first offline-only residual-state maximin sampler and paired PyBullet
  measurement path exist on `experiment/residual-diversity-dataset`; they do
  not change the live policy or Ranker.
- Run `31367396930` compared maximin and stratified-random portfolios from the
  same b000-k20 snapshots at steps 3, 6 and 9. Mean observed settle-afterstate
  nearest-neighbour distance improved at all three steps (+0.022704, +0.019394,
  +0.008419; mean +0.016839), so the proxy does transfer to physical dispersion.
- This is not yet a usable training distribution. Unique item coverage changed
  by -2/-1/-1, item-orientation coverage by -1/-1/0, step 3 lost two physical
  spatial cells, and step 9 had two fewer placed-safe candidates. Unconstrained
  maximin is therefore a measured trade: farther states, narrower semantic
  support, and a late-step safety cost.
- The next sampler must guarantee item and item-orientation coverage first,
  keep physical safety separate, and only then maximize residual distance.
  Do not train a Transformer or claim live-policy benefit from this pilot.
- Run `31368589378` tested that constrained v2. It retained positive physical
  dispersion at all three steps (+0.025438/+0.012888/+0.005581; mean
  +0.014636) and eliminated the item-orientation deficit, but still failed the
  preregistered guards: global unique-item coverage was -1 at step 3 and
  placed-safe replay count was -2 at step 9. The constraint was local to each
  stratum, so several strata could still spend quota on the same item.
- Do not train from v2. If this line continues, coordinate semantic coverage
  across the whole portfolio (while retaining stratum minima), and treat
  observed physical safety as an outcome/acceptance axis rather than claiming
  the current static risk proxy is a safety label.
- Run `31369511973` implemented that global coordination with maximum-cardinality
  item-to-stratum-slot matching. It solved the semantic deficit: physical
  unique-item deltas were +1/+3/+3 and item-orientation deltas +4/+1/+1. The
  observed settle-afterstate NN-distance delta stayed positive at all steps
  (+0.027739/+0.058524/+0.022009; mean +0.036091), materially stronger than v2.
- The preregistered verdict is still `fail` only because placed-safe was
  0/+1/-1. This narrows the remaining problem to physical outcome handling,
  not state diversity. Keep v3 as the semantic sampler. The next dataset stage
  should overdraw, replay, form the positive residual-state arm only from
  observed placed-safe transitions, and retain unsafe rows as a separate
  negative-risk arm. Do not revive the rejected static hard gate.
- Run `31370546291` implemented that observed-outcome split with 2x overdraw
  and passed all four preregistered guards. Positive-transition physical
  NN-distance deltas were +0.030116/+0.017396/+0.017448 (mean +0.021654),
  unique-item deltas +1/+2/+2, item-orientation +4/0/0, and placed-safe 0/0/0.
  It yielded 30/13/12 safe positive transitions plus 0/7/15 deduplicated
  negative-risk examples at steps 3/6/9.
- Schema v3 is therefore accepted as a bounded offline dataset contract:
  `step-*-candidates.jsonl` is the safe residual-state arm and
  `step-*-negative-risk.jsonl` is the unsafe physical-risk arm. This does not
  establish a learned value function or any live-policy score improvement.
- Runs `31372071696` and `31372706195` scaled that contract across the core
  1/2-container x shelf/no-shelf matrix at steps 3/9/15. Every condition ran
  through official PyBullet and produced safe positive plus negative-risk
  rows. The 2x run yielded 281/69 labels and passed 3/4 scenarios; only
  dual-empty step 15 missed one safe-control row. The 3x run yielded 282/108
  labels and fixed dual-empty, but passed only 2/4 scenarios.
- More overdraw is not monotone. At 3x, the two shelf conditions both lost
  physical NN distance at step 15 (-0.007839 dual mixed, -0.009555 single)
  even though the run-wide means stayed positive. Dual mixed also lost one
  item-orientation there. The command/predicted-contact proxy therefore does
  not preserve observed settle-state dispersion in late shelf states.
- Every row now carries `scenario_context` (container count, shelf/dedicated
  patterns, initial load, stream settings and geometry). Do not pool these
  conditions without conditioning. Keep the paired safe-random arm and do not
  tune another overdraw factor; the next sampler question is observed
  afterstate-aware final selection or an explicit proxy-fidelity model.
- Run `31380879143` replaced only that final distance calculation with official
  replay `x_plus`. It fixed the prior two-container shelf failure: dual mixed
  step 15 moved from physical NN delta -0.007839 / item-orientation -1 to
  +0.009883 / +9, and both two-container scenarios passed.
- The matrix still failed 2/4 conditions. Single no-shelf step 9 had physical
  mean-NN delta -0.004446 and single shelf step 15 had -0.017559. Their minimum
  NN deltas were nevertheless positive (+0.002102/+0.002309) and semantic
  coverage was non-regressive. The remaining defect is objective mismatch,
  not the old command-to-settle proxy gap: semantic-first greedy maximin
  optimizes minimum distance, while the guard measures mean NN against the
  paired control. Do not train from this matrix yet.
- The control-seeded observed-state swap optimizer cleared the matrix. Run
  `31388832646` passed all four cells at +0.073926, +0.070353, +0.049806 and
  +0.064257 and produced 307 safe-positive and 134 negative-risk rows. Three
  of the four guards are now structural, not lucky: the seed IS the control,
  so the search starts at delta exactly 0.0, the seeded portfolio is a
  superset of the control so the semantic deltas cannot be negative, and both
  arms are all-safe and equal size so the placed-safe delta is 0. Only the
  strict mean-NN guard needs an improving swap to exist. See
  `docs/OBSERVED_STATE_SWAP.md`.
- The ablation arm was then run, and it moved the conclusion. Run
  `31389892147` (`--observed-swap-rounds 0`, same commit) ALSO passed 4/4,
  although that identical greedy construction failed two cells in
  `31380879143`. The greedy verdict is runner-variable, so a passing greedy
  run proves nothing and "the optimizer made the matrix pass" is not
  supported. What survives: the greedy deltas are bit-identical across both
  greedy runs on the two-container cells and vary only on the two
  single-container cells that failed; every seeded delta in both seeded runs
  exceeds the ablation's in all four cells; and the seeded arm has a
  structural zero floor the greedy arm does not. Compare the arms on the
  delta ordering and the floor, never on the verdict.

### Local score proxies

- Fill and placed are the bundled evaluator outputs.
- Directions for `com_z`, shake metrics, priority-cover violations, and
  soft-cover violations agree with the reconstructible official submissions;
  no tested proxy points in the opposite direction.
- The 0–100 normalization and component exchange rates remain unknown. The
  proxies support Pareto/dominance checks, not a fabricated total score.
- `fill` did not clear the local noise floor across the calibration builds and
  remains unresolved as a discriminator.

## Rejected or closed lines — do not restart without new evidence

- static hard release-risk gate;
- deadline-reserved rescue scan;
- score-top2 cross-step incumbent as fallback;
- visible-pool rollout enforce mode;
- quotient-capacity and route-survival live tie-breaks;
- 2 mm lateral guard;
- death-band fallback (official score -15.3%);
- zone loading doctrine;
- release attribute hard reject;
- board receptivity as a global ranking rule;
- Monte-Carlo rollout value v1/v2;
- item-cap 16;
- multi-axis static Pareto enforce v1;
- using heightmap drop heights to compare Ranker scores.

Negative results are scoped. Read their active ledger entries before reusing
their instruments. A superseded or historical entry is not current evidence.

## Not established

- The official component weights or normalizations.
- A reliable exchange rate between placed and priority/soft/stability/cog.
- A graded board value that ranks same-state candidate actions.
- A safe replacement for the fixed protocol fallback when no safe action
  exists. Some terminal states are now certified truly empty, so fallback
  cannot create a legal move there.
- A second independent real Task A case.
- Whether the Task A offline proposal oracle improves when made risk-on.
- Whether the unmerged L1/L2 selection-gate instruments transfer onto the
  current live branch. They must be ported surgically, not merged wholesale.
- Whether a learned or outcome-weighted delayed proposal aggregator can
  distinguish proposal quality.  Plain randomized-delay voting has been
  measured and produced no action-level or item-level consensus.
- A model trained on the board beats the incumbent, and it survives the leak
  worth worrying about. On a FROZEN copy of the same 130 boards over 8 cases,
  mean within-state AUC is 0.733 incumbent / 0.767 MLP-on-the-eight-scalars /
  **0.842** candidate-geometry MLP / 0.835 set attention. Restricting the
  positives to the stratified-random control arm -- which removes the swap
  optimizer's diversity selection from the safe class -- gives 0.745 / 0.768 /
  **0.851** / 0.841: the same ordering, and a slightly larger margin. Six
  measurements now agree (three corpus sizes, two positive sources). Capacity
  alone clears the incumbent, so the audit's linear arm was under-powered;
  the largest jump comes from the candidate's own position, size, orientation
  and container, which `phi_modelling` never carried. Attention loses on
  safety ranking and wins on the settle regression in every arm (R^2 up to
  0.337 and 0.390 against the audit linear arm's 0.147 and 0.081). Quote AUC,
  not top-1: top-1 tracks the safe fraction per board, which is a sampling
  design. See `docs/STATE_MODEL_EXPERIMENT.md`.

- More states was never the constraint, and neither was the model family on
  its own: the FEATURES were. Withdrawn along with the saturation claim.
  Scaling boards is still worth doing for condition coverage, and the
  learning curve should be re-read on the state model rather than on the
  eight scalars.

- Whether the accepted rows support a learner at all. The corpus is small and
  narrow: 37 committed schema-v1 states (2732 rows, no `scenario_context`, and
  a modelling vector only on the 1765 release rows), plus about 12 states per
  schema-v3 matrix run. Rows inside one state share a parent and are strongly
  correlated, so 307 positives is not 307 independent examples.
- A state is a board, not a `(case, step)` label, and this changes the scaling
  answer. The policy is deadline-limited, so two runs of one scenario reach
  different boards at the same step index: `m-single-empty-noshelf` step 9 was
  measured three times locally and gave three different placed-item
  configurations (one shelf pair did collide, so it happens both ways).
  Re-running the matrix therefore ADDS roughly 12 fresh states for about six
  minutes of CI, and is the cheapest scaling axis available. `corpus.md`
  reports fingerprint-based `distinct_states` beside the `case_step_slots`
  count so the two are never confused again.
- Whether the retained corpus is large enough to learn from. Retention is now
  decided: the matrix commits its rows and snapshots to
  `reports/residual-diversity-scale/history/<run_id>/dataset/`, indexed by
  `scripts/index_replay_corpus.py`. That deliberately revises the keystone
  requirement "raw physical data stays in artifacts" -- one run is about
  0.46 MB compressed, and artifacts expire 90 days out while the wall-clock
  dependent trajectory cannot be regenerated. Read `corpus.md` for what is
  held: it separates rows from distinct states and never merges arms.
- Whether the mean-NN guard is itself size-fair. The positive arm is usually
  larger than its paired control, and mean nearest-neighbour distance falls as
  a portfolio grows, so part of a negative delta may be arm size rather than
  sampler quality. Arm sizes are recorded; the confound is not yet measured.
- Whether a model trained on the condition-labelled safe/risk rows improves
  residual-state ranking or official component proxies.

## Branch disposition

The live branch already contains the accepted Task A, first-pass, true-envelope,
scenario-matrix, proxy-calibration, and support-exhaustion work. Old research
branches are retained as evidence, not as competing trunks.

- `claude/task-bottleneck-optimization-o3qtkk`: research branch with 25
  exclusive commits; contains potentially useful L1/L2 instrumentation but is
  166 live-branch commits behind. Review and cherry-pick individual ideas only.
- `claude/task-a-rollout-bounded128-dneq4n`: old Task A/scenario branch; results
  are already represented on live trunk. Do not merge wholesale.
- `experiment/future-option-tiebreak` and
  `experiment/route-survival-shadow`: rejected experiments; preserve as archive.
- `claude/algorithm-improvement-testing-uni3wj`: one old soft-settle evidence
  entry aimed at MC v1; MC v1/v2 was later closed, so no merge is needed.
- `experiment/task-a-rollout-transfer`: preserved Codex result/history branch;
  its accepted implementation and compact report are already on live trunk.
- `experiment/residual-diversity-dataset`: active offline dataset experiment.
  Run `31370546291` accepts the schema-v3 bounded positive/negative dataset
  contract. Matrix runs `31372071696`/`31372706195` establish condition-aware
  generation but refute unconditional command-proxy diversity in late shelf
  states. Run `31380879143` fixes the dual-shelf proxy failure with observed
  afterstates but exposes a remaining mean-vs-min distance objective mismatch
  in single-container states. It is not a live policy change or trained model.

Exact ancestry counts and rationale are in `docs/BRANCH_INVENTORY.md`.

## Next engineering task

1. The four-condition guard now passes (`31388832646`), so the sampler
   question is closed and the data question is open. In order:
   (a) the ablation arm is done (`31389892147`) and showed the guard verdict
   is runner-variable for the greedy arm, so any further arm comparison needs
   repeated runs and per-step deltas, not one verdict; (b) retention is decided and
   implemented -- rows and snapshots are committed under
   `reports/residual-diversity-scale/history/<run_id>/dataset/` and indexed by
   `scripts/index_replay_corpus.py`; (c) the learnability audit has now run
   once and returned `no_established_signal`
   (`reports/learnability/summary.md`). The next move is more distinct
   STATES, not more rows per state. Repeating the matrix is the cheapest
   axis: a widened run lands ~46 fresh boards in ~25 CI minutes. But the
   state model now beats the incumbent at ranking (0.851 against 0.725 mean
   within-state AUC, `reports/state-model/summary.md`), so the open question
   is no longer "is there signal" but "does it survive contact with the live
   policy". That needs a physical negative control, not another dataset run:
   this project has rejected selectors that looked better statically and lost
   on trajectories (multi-axis Pareto enforce v1), and the incumbent is
   consumed inside a deadline-bounded search, so latency is a live
   constraint. Two gaps remain regardless: settled candidates carry no
   feature vector at all, and there is no board-value label whose noise is
   smaller than its effect (`sigma-branch-is-the-size-of-the-effects`). Do
   not open final holdout data.
2. Fix the residual metric before spending more runs optimizing against it.
   Two defects are now measured, not suspected. (a) It spans two coordinate
   frames: commands are container-local, settled `x_plus` is world, and the
   containers sit 2.5 m apart against item extents of tens of centimetres, so
   a cross-container pair saturates the position term and container
   membership is counted twice. `settled_proxy_record` must emit
   container-local coordinates in the live pipeline; the offline measurement
   in `scripts/measure_residual_metric_defect.py` shows what changes when it
   does. **(a) is now fixed at the source** -- `settled_proxy_record` takes
   `container_offsets` and `build_replay_dataset` passes them, so the search,
   the guard and the coverage report read one frame. Guard deltas from runs
   before commit `2ccb262` are in the old frame and must not be compared
   directly against later ones on multi-container boards. (b) It averages two
   different questions into one sum -- where the item landed, and which item
   left the pool -- and the discrete half carries most of the ordering: four
   of eleven terms are categorical, and identity alone reaches 0.747 mean
   within-board rank agreement against the full metric's 0.844.
   `occupancy_distance` and `consumption_distance` are now reported beside
   the sum, and **the search no longer maximises the sum alone**: the
   `pareto_gate` rule refuses a swap that degrades either component, adopted
   on paired within-board evidence and replicated with the arms in opposite
   slots (runs `31491047020` and `31492719115`, 90 boards). It raises
   consumption diversity (+0.030 and +0.034, sign-test p=0.0001 and
   p=0.0009) and does NOT measurably move occupancy (p=0.0989 and p=0.1081)
   -- that second one is not a win, do not quote its positive mean as one.
   The sum still ORDERS the admissible moves, so the weighting nobody chose
   is reduced rather than gone. `--observed-swap-acceptance sum` restores
   the old rule, and whichever is chosen the other runs as a shadow so the
   comparison keeps being measured. Neither defect explains the optimizer's
   margin: it survives collapsing the frames (+0.0742 to +0.0718 over 454
   boards) and is positive on both components independently. Do NOT read the
   residual-space result (`reports/residual-space/summary.md`) as "a learned
   space is not worth building". That comparison has now been redone on equal
   terms and the caveat is retired: scored against the OCCUPANCY half of the
   truth alone -- the part physics decides, with no field the proxy carries
   verbatim -- command_proxy 0.709 against set_attention 0.502 and
   candidate_mlp 0.491, over 162978 pairs from 182 boards. The unfair
   advantage was real but small; the gap only falls from 0.344 to 0.207. Even
   commanded geometry alone reaches 0.667. What the result does NOT say, and
   must not be cited as saying: those arms were trained on safety
   classification and settle regression and had their embeddings read out.
   **No model has ever been trained directly on the residual-distance
   target.** So embeddings trained for safety ranking do not transfer to
   ordering residual difference; that is not the same claim as a learned
   residual space being unreachable.
3. Replay the 57 multi-axis substitutions from run `31362302154` as paired
   selected/proposed physical trials. Determine which static dominance axes
   fail to predict settle angle, displacement and placement safety before
   designing v2. Do not tune another weighted sum from episode aggregates.
4. Reconstruct or locate the `submission22` build and add it as the fourth
   calibration point. This is the shortest path to pricing component trades.
5. Fix Task A F8 behind a flag: make the offline proposal oracle evaluate the
   same risk-on placement policy as execution, then rerun the paired Task A
   order experiment. Revise ADR-003 before adopting.
6. Only after calibration, design an attribute-aware support policy that preserves
   plain support earlier without the placed collapse of the hard attribute
   guard. Do not begin with another weighted sum.
7. Review the exclusive `task-bottleneck` L1/L2 commits individually. Port an
   instrument only if its question is still open and its negative control can
   be reproduced on current trunk.
8. Treat temporal chunking as closed for plain voting.  Reopen only with an
   explicit proposal-quality target and a negative control that can show why
   one delayed origin should outrank another.

## Verification and operating rules

```powershell
python -m unittest discover -s tests
python scripts/run_checks.py       # required after agent changes
python scripts/context.py evidence --topic <topic>
python scripts/coverage_report.py
```

Python 3.12+ and Linux CI are the canonical environment. On Windows, PyBullet
integration tests may skip; `OK (skipped=3)` does not prove the physical
contract. A process exit code of zero is not a physical success unless
`is_included`, `is_valid`, and `is_placed_safe` are all true.

Large raw logs stay in Actions artifacts or ignored raw directories. Commit
compact summaries and additive evidence entries. Never open final holdout data
outside the one-shot protocol in `docs/RELEASE_RISK_PROTOCOL.md`.
