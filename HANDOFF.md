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
- Whether an observed-outcome split can turn the globally matched v3 portfolio
  into an admissible positive-transition training set while retaining unsafe
  rows as negative risk examples. v3 establishes semantic diversity but misses
  the placed-safe guard by one late-step candidate.

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
  Run `31369511973` establishes global semantic matching and stronger physical
  dispersion, but misses the late-step placed-safe guard by one; do not merge
  as a finished positive-transition training pipeline yet.

Exact ancestry counts and rationale are in `docs/BRANCH_INVENTORY.md`.

## Next engineering task

1. Replay the 57 multi-axis substitutions from run `31362302154` as paired
   selected/proposed physical trials. Determine which static dominance axes
   fail to predict settle angle, displacement and placement safety before
   designing v2. Do not tune another weighted sum from episode aggregates.
2. Reconstruct or locate the `submission22` build and add it as the fourth
   calibration point. This is the shortest path to pricing component trades.
3. Fix Task A F8 behind a flag: make the offline proposal oracle evaluate the
   same risk-on placement policy as execution, then rerun the paired Task A
   order experiment. Revise ADR-003 before adopting.
4. Only after calibration, design an attribute-aware support policy that preserves
   plain support earlier without the placed collapse of the hard attribute
   guard. Do not begin with another weighted sum.
5. Review the exclusive `task-bottleneck` L1/L2 commits individually. Port an
   instrument only if its question is still open and its negative control can
   be reproduced on current trunk.
6. Treat temporal chunking as closed for plain voting.  Reopen only with an
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
