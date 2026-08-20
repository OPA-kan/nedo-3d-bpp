# Handoff — current state

Updated: 2026-08-18 JST (the 2026-08-16 text below is retained; the
sections added on 2026-08-18 are the soft axis, the death budget, the
measurement-hygiene defects, the post-shake instrument, and the fifth
official submission). The most advanced line is now
`claude/v5-hypothesis-validation-cyna2c` (continues
`experiment/counterfactual-graph` from `f3bd29e` through the regime
expedition: powered v5/v6 rejections, phase structure, freezing points,
guard recalibration, and two preregistered live-mechanism trials). The
2026-08-10 audit text below is retained for the older branches.

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
| physics probe guard | `PHYSICS_PROBE_MODE=guard_quiet`, safety artifact embedded in agent.py | adopted 2026-08-17 (`quiet-guard-confirmed-adoption-licensed`); fail-safe: no pybullet or no weights degrades bit-identically to the old default; SAFETY_RERANK_MODE stays off — the guard materializes the observed pool itself |

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

The instrument and the first Linux physical H3 condition matrix are complete:

- `scripts/counterfactual_graph.py` defines horizon 3–5, deterministic IDs,
  DAG state convergence, branch/node/edge budgets, atomic JSON output and an
  independent-env prefix replay contract.
- replay-dataset snapshots now retain the optimized item order, visible pool,
  stream offset, exact action prefix, future-stream ID and board fingerprint.
- prefix replay refuses to label a branch unless the reconstructed root
  fingerprint matches. PyBullet `saveState` alone is explicitly insufficient
  because it omits Python stream/container state.
- `scripts/build_counterfactual_graph.py` now performs bounded breadth-first
  physical expansion. It runs fixed-attempt `PlacementCore.top_candidates`
  separately per visible item, then retains the best candidate per stable item
  so graph width is not consumed by either the first easy item or its
  near-duplicate poses. It reconstructs every
  candidate path in a fresh env, records multi-axis node totals and edge
  deltas, merges equal same-depth states, and stops terminal branches. It does
  not use a wall-clock deadline.
- The post-shake instrument now separates pre-existing soft coverage from
  shake-introduced coverage. `post_shake_soft_clean_to_covered_events` counts
  only exact in-shake `soft_covered_by_other == 0` to `> 0` transitions and is
  accumulated across H3 paths for teacher export. Older post-shake graphs omit
  the optional axis and reproduce their prior signal and manifest byte-for-byte.
- no ranker, policy default, simulator rule or final holdout was changed.

The original pilot remains in `reports/counterfactual-graph/summary.md`.
The scaled H3/B2 matrix is recorded in
`reports/counterfactual-graph-scale/{summary,signal}.{json,md}` and Actions runs
31556144806 and 31557059281. Both runs reproduced the aggregate counts. All 8
requested conditions completed: 51 edges, 47 safe edges,
4 physical failures and 32 terminal trajectories (23 horizon, 5 no-candidate,
4 physical-failure). Of 24 sibling pairs, 8 unequal-score pairs had different
downstream ranges. A lower immediate-score branch still had a better reachable
leaf on fill (2 pairs), CoG (2), surface variation (4), or soft coverage (2).
The 15 exact-score ties did not separate on the recorded outcome axes.

Run 31558667741 enlarged the matrix to 24 roots, 207 edges and 127 terminal
trajectories. Immediate-score order counterexamples reproduced in both the
18-root discovery split and the 6-root step-15 late holdout. The lower-score
branch reached a better leaf on fill/CoG/surface/soft in 35/25/16/1 pairs.
All 42 exact-score pairs remained identical on recorded outcome ranges and
graph topology. A narrowly scoped H5 diagnostic then completed in Actions run
31559232452 and
`reports/counterfactual-tie-h5/`: three H5/B2 graphs, 186 safe edges and 96
horizon leaves. Exact-score pairs still separated 0/39, so exact ties are not
an H3 horizon artifact on these roots and remain excluded controls.

The first model-input corpus is now complete. Final Actions run 31563973521
produced 25 H3 roots and 108 sibling pairs. `scripts/build_counterfactual_teacher_pairs.py`
exports 58 discovery rows, 8 late-holdout rows and 42 controls without combining
outcome axes. Every informative row has an observed source-state set tensor and
both candidate-action tensors (66/66 for each contract). Inputs exclude the
step index and future/outcome labels. The action vector retains the official
command, immediate score and source-visible item fields.

`scripts/evaluate_counterfactual_teacher_baseline.py` freezes discovery-only
normalization and 1-NN labels, then evaluates late roots once. The state+action
ranker scored fill 6/7, surface variation 7/8 and CoG 5/8, versus immediate
score at 5/7, 4/8 and 6/8. Run 31563029977 returned 6/7, 9/10 and 7/10 for the
same axes. Candidate-action 1-NN beat immediate score on fill and surface in
both runs. Source-state features improved isolated cells by one decision but
not consistently over action-only 1-NN, so incremental residual-state value is
not established yet. Placed/priority have no directional rows in the final
holdout and soft has two. This is a small diagnostic, not generalization or
official-score evidence. Compact evidence, including the two-run comparison,
is in `reports/counterfactual-teacher-{pairs,baseline}/`; raw graphs remain
Actions artifacts. No live ranker, policy default, simulator rule or final
holdout was changed.

The next representation gate has been selected without reopening late roots.
`scripts/evaluate_counterfactual_teacher_discovery.py` performs leave-one-
physical-graph-out evaluation on the 58 discovery rows only. Candidate-local
geometry (container margins, nearest settled neighbours, overlap/support gaps,
relative occupancy and visible-pool summaries) with a fixed-L2 linear ranker
reached CoG 44/58 versus action-only 34/58 and seven within-fold state
permutations at 30--36/58. Surface variation reached 46/58 versus action-only
29/58 and permutations at 25--41/58. It did not transfer to fill (36/54 versus
44/54), so the frozen policy uses action-only for fill, candidate-local state
only for CoG/surface, and abstains on the under-supported axes. The complete
pre-late policy and its one-run acceptance gate are in
`reports/counterfactual-teacher-discovery/policy.json`. Do not retune it on the
next late result.
Retrospective application to the already-observed run 31563973521 late rows
fails that gate (CoG 3/8 versus action 5/8; surface 5/8 tied; pooled 8 versus
10). This was recorded, not used to alter the policy.

The preregistered new-late evaluation is complete on physical run 31565624982.
The policy was committed before the run. Fill's frozen action-only model scored
6/7. Candidate-local state beat action-only on surface (6/8 versus 5/8) but
lost on CoG (3/8 versus 5/8), for a pooled 9 versus 10. The gate therefore
failed: **do not scale the current hand-designed candidate-local state
representation into a larger model**. This closes that representation, not the
H3 teacher corpus or the replicated candidate-action signal.

The remaining action signal was then tested across four independent physical
runs: train on the other runs' discovery roots, test a whole target run's late
roots. A no-intercept geometry-utility difference (candidate swap negates the
prediction) scored fill 26/33 versus immediate score 16/33 and surface 31/42
versus 25/42; it lost on CoG (29/42 versus 36/42). This is an axis-level
diagnostic, not a selector. Requiring fill and surface to agree proposed on
10/30 late pairs and still contradicted an attained axis on 4/10.

Schema-v3 teachers therefore retain every jointly attainable leaf outcome
vector and label Pareto-frontier coverage without a weighted sum. On latest run
31566975749, 10/62 informative pairs had a strict reachable-set dominance and
52/62 were incomparable. Across four run-held-out late splits only nine strict
dominance rows appeared; immediate score classified 9/9 and geometry utility
6/9. **Do not ship an action-value shadow or invent an axis weight from this
corpus.** The usable result is the H3 teacher/instrument plus an offline
fill/surface signal; the safe live decision rule remains unestablished.

Schema v4 now exposes the missing state-value target. A fresh Linux physical
matrix, Actions run `31595519595`, completed all eight conditions and verified
both child tensors on 67/67 informative pairs.
Every informative sibling row joins both physical child-state tensors and
labels per-axis H3 continuation gain after subtracting each child's cumulative
H0 outcome. With continuous differences below 1e-12 treated as equal, five-run
held-out evaluation found afterstate fill 15/16 versus action geometry 10/16
and every state permutation at no more than 10/16. The paired result is 6 wins
/ 9 ties / 1 loss, with exact two-sided p=0.125. Surface fails to transfer:
afterstate is 13/26 and
worse than immediate score (2/13/11, p=0.02246). This establishes a direct
physical afterstate teacher and a promising fill-only hypothesis, not a live
policy. Keep H5 and live selection closed; the next representation experiment
must preregister fill only and increase discordant held-out roots.

The fill-only follow-up is frozen before new physics in
`reports/counterfactual-afterstate-value/fill-policy.json`. Container summaries
was designed after inspecting the same five runs. Under the corrected numeric
contract, its agreement gate retrospectively gives 66/67 on discovery and
15/15 at 15/16 coverage on the already-inspected late rows. Do
not call that confirmation: the rule was designed after viewing those errors.
Its preregistered next-run gate is >=75% late coverage, zero errors, and no
covered-row regression versus either constituent or action geometry.

The preregistered confirmation passed on new physical Actions run
`31598349094`. After applying the corrected numeric label contract (continuous
outcomes within absolute tolerance 1e-12 are equal), it covered 4/4 directional
late fill rows and was correct 4/4, versus action geometry 2/4. All eight matrix
conditions and aggregate succeeded.

The fixed-policy independent replication in Actions run `31600369286` also
completed all eight conditions and aggregate, but failed the same gate: 3/3
coverage, 2/3 correct, versus action geometry 1/3. Across both corrected new
runs the consensus is descriptively 6/7 versus action 3/7, but pooled accuracy
does not override the preregistered per-run zero-error gate. Status is
`replication_failed_not_shadow_ready`: do not retune on these runs, start H5,
or enable a shadow/live selector. The tolerance correction also removed a
spurious directional label caused only by a roughly 3.6e-15 float difference.

Post-failure diagnosis is committed in
`reports/counterfactual-afterstate-value/diagnosis-31600369286.md`. It never
trains on either confirmation run. The single replication error had 15 exact
scenario-axis training rows, so this is not an unseen matrix condition, but
its standardized nearest-training distance was 6.380 for packed and 7.986 for
packed+visible, versus training-only leave-one-out p95 values 2.556 and 2.559.
All four first-confirmation rows were inside both p95 thresholds. A posthoc
support gate would remove the error but cover only 2/3 rows (66.7%), so it still
fails the original 75% gate and cannot rescue the policy. The next experiment
is preregistered in `next-support-experiment.json`: keep both evaluation runs
sealed, increase independent mid/late H3 roots in the same eight conditions,
require at least 12 directional late rows before refreezing, and only then use
a later physical matrix for confirmation. Do not deepen to H5 yet.
`build_replay_dataset.py --environment-seed` now exposes and records the
simulator reset seed (default 42 remains backward compatible); repeated seeds
are deterministic replications, while declared distinct seeds supply the new
root trajectories required by this experiment.

That assumption was tested and rejected. Four successful eight-condition
matrices used seeds 314159, 271828, 161803 and 141421 (Actions runs
`31655945368`, `31656259168`, `31656261414`, `31656617967`). They produced 14
raw directional late fill rows, but only six unique exact model-visible
afterstate-delta signatures (42.9%); 13/14 rows belonged to cross-run duplicate
groups. Discovery was similarly duplicated: 25 unique signatures from 53 rows.
Therefore different seeds are necessary but not sufficient for independent
support. The collection independence gate failed; do not fold these runs into
training or refreeze. The next generator change must vary the actual scenario,
item stream/order, or root trajectory policy and pass
`audit_counterfactual_afterstate_collection.py` before model evaluation.
The next collection is frozen before physics: stream variants `source-001`,
`reverse-000`, and `interleave`, all at environment seed 42 and unchanged
H3/B2. Admission requires at least 12 unique directional late signatures and
at least 75% unique fraction. The default `original` builder remains exactly
backward compatible. Run the independence audit before fitting anything.

That collection now passes independence but not the model gate. Actions runs
`31658418482`, `31658420380`, and `31658422923` supplied 30 directional
discovery rows with 28 unique signatures (93.3%) and 14/14 unique directional
late signatures, with no cross-run duplicate groups. The source-001 and
interleave workflows remain FAIL because one root reconstruction failed in
each; only already validated graph artifacts were recovered under the
preregistered graph-level rule, without looking at labels, and their union
still covers all eight scenario labels. Do not describe those workflows as
passing.

The unchanged support-gated consensus then covered only 9/14 variant-held-out
late rows (64.3%) and made three errors, so it failed both coverage and
zero-error requirements. Eleven declared alternatives were audited without
sealed confirmation data. Height grids and their kNN variants reached at most
10/14; no zero-error representation exists in this audit. Do not refreeze or
confirm. The next preregistered question keeps H3 fixed and widens only the
erroneous roots from B2 to B3, testing whether optimistic continuation labels
are stable before spending capacity on a richer model or opening H5.

That B3 test ran as Actions `31670257775`; all four physical graphs completed.
Only one of four preregistered error pairs remained directly comparable and it
kept the B2 relation. Two required depth-1 parent paths were absent from the
B3 graph and one root sibling pair was absent because widening changed the
selected candidate set. This fails the stability gate: three rows are not
fixed-label examples across branch widths. Do not train an agent to imitate
those B2 labels. The next teacher design must preserve the target candidate
paths explicitly (forced-pair continuation expansion) rather than equating
top-B candidate selection with ground-truth state value.

The forced-pair follow-up is preregistered before execution. It does not replay
stored B2 coordinates. At each target path it asks the unchanged provider for
its current best physical action per item, forces the specified parent item
and sibling items into the B3 set, and fills the remaining width by normal
ranking. A missing provider item fails the graph. All four relations must be
directly comparable and stable before agent-model work resumes.

Forced-pair Actions run `31671441984` completed all four graphs and made all
four pairs directly comparable. Two relations remained
`lower_afterstate_better`; two changed from that directional B2 label to
`equal` under B3 (source-001 dual-empty and reverse-000 dual-shelf). There was
no direction reversal. Thus half of the apparent four representation errors
were B2 search-width label noise, while reverse dual-empty and interleave
dual-preloaded remain genuine B3 model errors. Retire B2 directional labels
as the training standard; do not edit them post hoc or mix them with B3. The
next corpus must be generated directly at H3/B3 and evaluated with entire
stream variants held out before any agent can be called promising.

The first H3/B3 corpus collection ran as `31672407187`, `31672410385`, and
`31672413055`. Reverse completed all eight conditions; source-001 and
interleave retained their known single-condition strict reconstruction
failures, and only validated graphs were recovered. After fixing the B3
exporter to enumerate all three unordered pairs per width-three parent, all
three corpora are schema-v4 training-ready. Together they contain 90
directional fill discovery rows (60 exact model-visible signatures) and 34
late rows (18 signatures). The original 75% raw-row uniqueness gate therefore
fails at 66.7%/52.9%; do not reinterpret it as a pass. Crucially, repeated
signatures have zero conflicting labels and none cross streams. Before a new
holdout is generated, the next unit is fixed as one consistent exact
signature, with no multiplicity weighting. A new `rotate-000-7` stream is
reserved as whole-stream H3/B3 holdout; it must not be used for model choice.

The signature-unit whole-stream leave-one-out audit is now reproducible in
`h3-b3-signature-policy-audit`. Of 11 declared representations,
`height_grid_4_plus_action` is the unique best at 17/18, but the preregistered
zero-error development gate fails. The sole error has asymmetric optimistic
continuation support. Requiring at least two continuation values on both
afterstates removes that error (12/12), but retains only 12/18 signatures
(66.7%), below the unchanged 75% coverage gate. Therefore no agent candidate
is frozen. Actions run `31676609549` for the reserved `rotate-000-7` holdout
was cancelled before aggregation or teacher-label inspection; one condition
had already failed strict root reconstruction. Its labels remain sealed and
must not be opened after this failed development gate.

The next collection is preregistered as development stream `rotate-001-5`
(case 001 rotated left five, identities preserved), seed 42, unchanged H3/B3
eight-condition matrix. It must add at least six new late signature units with
two or more continuation values on both sides. Four-stream whole-stream LOO
must then be uniquely zero-error with at least 75% supported coverage; neither
threshold may move. Exploratory continuation aggregation, nonlinear feature,
and ridge-strength variants did not exceed the 17/18 result and are closed.

That collection ran as Actions `31678079848`. Six conditions contributed 16
completed graphs under the preregistered graph-level recovery rule; the run
itself remains failed. It added only three unique directional late signatures
and one symmetric-support unit, below the required six. Four-stream LOO is
18/21 for `height_grid_4_plus_action`; symmetric support is 13/21 (61.9%) and
12/13 correct. No candidate is frozen. The remaining errors are one supported
2-vs-2 continuation and two asymmetric 1-vs-many continuations. The next
preregistered test reconstructs those exact three pairs at H4/B3. Every
relation must remain directional and unchanged before model work can resume.

The H4/B3 test completed all three physical graphs as Actions `31687012973`.
Only reverse dual-empty remained stable. Interleave dual-shelf reversed from
higher to lower afterstate, and interleave single-preloaded became equal.
Thus two of the three H3 model errors were depth-three teacher noise; the
supported reverse error is genuine at H4. Polynomial height transforms did
not improve 18/21. H3-trained agent freezing remains blocked. The next
preregistered step is one reverse-000 H4/B3 eight-condition pilot; it must
produce at least 12 unique directional late signatures, no conflicts, and
75% symmetric continuation support before broader H4 collection.

The reverse-000 H4/B3 pilot completed all eight conditions and 21 graphs as
Actions `31688879334`. It passed count and consistency (16 unique directional
late signatures, zero conflicts) but failed symmetric continuation support at
9/16 (56.2%). Do not expand optimistic-max H4 teachers. Matching identical
continuation item sequences removed opportunity bias but collapsed signal:
78 of 81 unique signatures were equal and the three directional signatures
each had only one common path. H3/H4 also changed one of 16 overlapping
discovery signatures. The selected next target is therefore depth-independent:
for each afterstate, exhaust visible items and count/volume those with at least
one physical candidate, without the graph's top-three item cap. Existing H4
states show candidate-loss signal (41 of 186 late non-leaf states have zero
children), while ordinary child count otherwise saturates at three.

The unchanged candidate-local gate subsequently returned FAIL on 31566153353
and PASS on 31566975749 after its preregistered FAIL on 31565624982. This is
runner-variable, not a reason to reopen selection. The policy remains closed;
the exact replication table is committed beside the discovery audit.

The distributional-fill pre-action student line is closed with power. After
v3 (linear ridge, seed-58) and v4 (kNN, seed-59, underpowered at three
discordant pairs) failed their new-stream confirmations, v5 refit the same
116-feature label-blind local-geometry family on all 29 opened runs and
looked strong in strict cross-fit (719/1053 versus 657/1053, 127/65,
p=9.05e-6, 14/14 streams non-regressing). Its frozen power gate — the
prospective sign test may only be opened at 37 or more discordant pairs,
countable label-blind from prediction disagreement — rejected the first
seed-60 cohort as underpowered without opening labels, and the expanded
twelve-stream cohort (42 discordant) then delivered a powered verdict:
161/229 versus 157/229, 23 wins/19 losses, p=0.644, three streams
regressing. The cross-fit advantage does not transfer to new streams. Do not
retune these features into a v6; the powered-gate protocol itself is sound
and should be reused by any future candidate. See
`reports/counterfactual-afterstate-value/distributional-fill-preaction-v5.md`
and ledger entry `preaction-local-geometry-family-rejected-with-power`.
The first replacement hypothesis, a physics-free stamped height grid, was
then rejected in development on all 41 opened runs: no policy achieved
26-stream non-regression, and its pooled advantage regressed the structured
interleave/reverse orders. Nothing was frozen and no confirmation stream was
spent; see `distributional-fill-preaction-v6.md`. The next pre-action
candidate must model arrival-order structure or change the label target.

The long-horizon ranker-ordering question is now measured and
regime-dependent. Run 31931772512 (branch labels with per-sibling
RankEvaluation components on five b-configs) first suggested the live
ordering is mildly concordant with final fill; the independent
replication in run 31938388838 weakened that to fill-only (pooled over
both runs 51/80, p=0.018; placed 32/62, no signal — the instrument is
deadline-sensitive, never quote one run alone), and a leave-one-config-out
reweighting of the Ranker's own components still loses held-out. The same
run extended labels to the certified-fatal pool-1 cases at steps 2-20
with same-item top-candidate siblings and a support-surface ledger:
c001-k1 is intrinsic (0/9 states have a better sibling; the 21-placed
ceiling reaches back to step 2 — not suicide), while c000-k1 is
avoidable suicide territory: 6/8 states had a strictly better sibling
(one alternative placement at step 8 is worth 6 placements) and the
higher-q sibling wins only 3/17 decided pairs on final placed (p=0.013)
— the q tiebreak among the policy's own top candidates is inverted
exactly in the fatal regime, echoing the settled_share regime split. The
support ledger is directional only (4/4 comparable fill pairs, p=0.125).
Licensed next steps: a scoped pool-1 selection experiment among retained
top candidates and a mechanism-first audit of the inverted pairs; not a
global weight sweep. See
`reports/branch-labels/fatal-31938388838/summary.md`. The follow-up
causality probe already closed the obvious move: per-step inversion of
the tiebreak collapses the episode (10 placed versus 23), so the
observational advantage is single-deviation only, and any offline
reconstruction selector must carry the top-q control arm
(`scripts/run_tiebreak_probe.py`).

The feasibility side of the regime question now has a measured phase
structure. Crossing all 51 schema-2 anchor-recall oracle states with
their decision-time telemetry: P0 found 26 states, P1 deadline-miss 17
(reachable settled candidates exist, none accepted), P3 true-empty 8,
and P2 generator-hole zero — the support-plane generator always covers
part of any nonempty settled set. The transition is
trajectory-endogenous (the same case-step coordinate spans 0 to 798
settled candidates across agent generations), and near the cliff the
candidate space implodes so the scan finishes, which yields a
decision-time detector: zero settled accepted plus scan-unit completion
of at least one third calls true-empty at precision 1.0, recall 7/8 raw
(1/2 on the two distinct true-empty boards). See
`reports/anchor-recall/phase-structure.md`, ledger entry
`feasibility-phase-structure-and-true-empty-detector`, and
`scripts/analyze_phase_structure.py`.

Its first live use is already measured and rejected: turning that
classifier into an in-flight early-stop (`VACUUM_SETTLED_CUTOFF=0.34`,
skip remaining settled units and hand the deadline to releases) failed
all four preregistered gates in paired run 31941364445 — c001-k1
collapsed 21 to 16 placed in every replicate by trading a late
transport_invalid for an earlier topple, paired placed 2 wins/7 losses,
even though transport_invalid endings did fall 5 to 1. A post-hoc
classifier's precision says nothing about an early-stop rule's
false-fire cost, and full settled exhaustion is already handled by
anchor_fallback. The knob stays registered at default 0 only to
reproduce the negative; see `reports/vacuum-cutoff/verdict.md`.

The fixed protocol fallback finally has a measured variation, and the
fixed version survives by measurement rather than neglect.
`LAST_RESORT_RELAXATION_SECONDS` (default 0) rescans down a clearance
ladder only when the deadline search accepted nothing, exchanging the
certainly-dead fixed coordinate for a candidate with positive survival
probability. Development run 31947384483 passed all four preregistered
gates and broke c001-k1's certified policy-conditional 21-placed
ceiling to 22 in every replicate; fresh-permutation confirmation run
31947832632 failed pooled placed (200 vs 206, the rescue inert on four
of six k20 streams), so the knob stays 0 and the arm is closed. The
algorithm and both experiments are in `docs/LAST_RESORT_RELAXATION.md`
and `reports/last-resort/`; `protocol-fallback-never-varied` is closed.
A future variant must target regimes where fallback deaths carry mass.

The learning mainline is alive, replicated, and one bridge short of live
contact. Rerunning the state-model trainer under the identical LOCO
protocol on the grown committed corpus (7764 rows / 189 boards, +57%)
reproduces `state_model_beats_incumbent` and widens it: candidate_mlp
within-state safety AUC 0.825 versus the incumbent 0.705, top-1 safe
rate 0.968 versus 0.849 — the incumbent's safety ranking degrades as
boards accumulate while the learned model holds, and set_attention
still only ties the MLP, so board attention buys nothing at this scale.
The winning arm's full-corpus final fit is exported to numpy weights in
`reports/state-model/candidate-mlp-safety-v1.json` (torch-vs-numpy
parity 8.8e-6; phi is the agent's own `release_risk.features`, so the
live agent can score it without torch;
`scripts/export_state_model.py::numpy_forward` is the reference
inference). The live campaign runs through three preregistered gates.
Gate 1 (calibration) has PASSED: the log-only `SAFETY_RERANK_SHADOW`
first verified bit-identical trajectories on one paired episode, then
the calibration wave (7 guard configs x 3 replicates, run 31952503520)
showed the live logit separates the 14 physically-fatal final
placements from 378 surviving decisions at pooled AUC 0.933 (bar
0.70), monotone calibration, every death a release_candidate, and the
model conservative in the useful direction below logit 0
(`reports/state-model/calibration-protocol.md`, `calibration/`,
evidence `safety-shadow-calibration-pass`). Gate 2 is therefore
licensed: a rerank arm among retained top-K candidates (no refusal —
the vacuum-cutoff lesson stands), with a physical negative control and
a paired episode A/B under the powered-gate discipline with the
baseline.json floors. Gate 3 is a fresh-permutation confirmation. See
`reports/state-model/replication-20260816.md`.

The deviation line is likewise closed pending a new representation.
Twelve permuted pool-1 streams (run 31941899714) pooled with the fatal
cases give 14 streams and 77 branch states: 36% have a sibling of the
policy's own top-3 that strictly beats its choice on final placed
(mean one placement, tails to six) — avoidable value is common — but no
tested feature set carries a usable trigger. A second independent
schema-4 collection added 4x4 board grids and pool composition: board
features are uninformative (placed AUC 0.532), single-collection AUCs
swing (0.512 to 0.620), and the pooled two-collection number is placed
AUC 0.561 with top-quartile precision at the base rate. The decisive
extra finding: the avoidable label itself agrees 72/77 (kappa 0.86)
across the independent collections, so the target is a near-
deterministic function of the decision-time state — the line is
representation-bounded, not unknowable. Reopening requires beating
pooled placed AUC 0.561 offline on the committed two-collection corpus
(`reports/deviation-corpus/`, including `schema4/`) with a richer state
representation before any physics is spent.

## Official score history

| submission | total | fill | cog | stability | placement | soft | placed fraction |
|---|---:|---:|---:|---:|---:|---:|---:|
| submission22 | 17.581 | 29.276 | 14.224 | 20.721 | 4.45 | 7.65 | 0.434 |
| submission3334 | 23.246 | 31.413 | 21.505 | 29.424 | 10.85 | 12.65 | 0.452 |
| trueenvelope | **35.375** | **34.246** | **40.683** | **53.240** | **16.95** | **21.30** | **0.505** |
| deathband | 29.959 | 33.635 | 32.243 | 41.288 | 14.70 | 17.45 | 0.491 |
| quietguard | 35.195 | 33.851 | 41.665 | 53.480 | 16.30 | 19.65 | 0.497 |

The best known official result is `trueenvelope` at 35.375.

**Read these components against placed before reading them as mechanism**
(`reports/official/placed-regression.md`, ledger
`soft-regression-was-the-placed-drop-not-a-coverage-failure`). Every
component tracks `num_placed_items` above r = 0.96, and `soft` is the
one placed explains best: r = 0.988, strictly monotone across all five,
178.4 points per unit placed. `quietguard`'s headline -7.7% on soft is
its -1.6% on placed through that slope; its residual against the trend
is **+0.20**, and controlling for placed it was ABOVE trend on every
component and markedly so on the two it was built to move (stability
+4.36, cog +3.71) while the `deathband` build it replaced sat below
trend on exactly those. Caveats: n = 5 with two degrees of freedom
spent, residuals are small differences of large numbers, and the
observed placed range is only 0.434-0.505.

That regression is a statement about agents, not about actions. It does
NOT say soft is unmovable within a state, and reading it that way is an
ecological-inference error that was made and retracted here
(`placed-regression-does-not-license-dropping-soft-from-labels`). Its implementation
is now present on the live branch: commit `3b1635c` is an ancestor and
`ANCHOR_TRUE_ENVELOPE` defaults to 1. The old active ledger claim that the
trunk lacked this code has been superseded.

A submission artifact was rebuilt on 2026-08-17 from the quiet-guard
adoption commit `d63bace` (repository defaults, now including
`PHYSICS_PROBE_MODE=guard_quiet` with the safety artifact embedded — the
campaign's first shipped-behavior change; the offline optimizer's
`behaviour_sha256` is unchanged because the guard sits in `Agent.policy`,
outside the fingerprint's DryRunEvaluator probe graph, while
`component_sha256` moved with the default): `dist/submission.zip`,
SHA-256
`6ce23e7013149908cf13d3eb0848305b9430166a6d51e7e54e30a20b1d62ca9a`,
containing `submit/agent.py` byte-identical to `agent/agent.py`. The zip
itself stays uncommitted; rebuild with `python scripts/build_submission.py`
from a fresh fetch and re-record both values if any commit lands later.
The superseded 2026-08-16 build from `ab198d7` was
`6aea7fae446bd53194f43f1badce44242a8d3bde7c85a8425fed97ab97c43bf8`.

## The soft axis (2026-08-18): already compliant, no headroom

> **Corrected the same day, before this section was a day old**, by
> `reports/official/soft-rule-correction.md` and ledger
> `soft-stack-aware-reading-contradicts-the-published-rule`. The text
> below originally called the published rule ambiguous and treated the
> shipped predicate as a defect. It is neither. `simulator/README.md`'s
> 評価指標 section defines the Placement Score with an explicit
> **上方向からの接触判定** — contact — and `docs/ATTRIBUTE_PLACEMENT.md`
> had already transcribed it from there. The shipped predicate is a
> faithful transcription; the "stack-aware" variant contradicts the
> rule and was chosen only because its number sat nearest the official
> one. Read this section for the measurements, not for that framing.
>
> Two further corrections travel with it. The count-to-score mapping is
> unpublished and `docs/ATTRIBUTE_PLACEMENT.md` explicitly forbids
> presenting `clean_ratio` as a score, so comparing local 98.14 with
> official 19.65 was comparing incommensurable quantities. And the
> placed gating the score table below reports is **documented** —
> simulator/README.md's 積載数カットオフ and `docs/COMPETITION_QA.md:9` —
> so the r = 0.988 regression rediscovered a rule rather than finding
> one.
>
> **What the measurements then mean, inverted from what was written
> here first:** with the shipped predicate, violations run at 0.19 soft
> items per episode and 34 of 42 boards are completely clean, mean
> `soft_clean_ratio` 0.98. We are already compliant on nearly every
> board, so there is nothing left on this axis for a selector, filter,
> guard or ranking term to buy, and the attribute filter's 0-of-16 was
> the right answer rather than a symptom. Soft is not a separate lever;
> the route to it is placed, which is what the cutoff rule says
> outright.

The rule as published: "優先手荷物やソフト貨物が自分以外の属性の手荷物の
下敷き(上方向からの接触判定がある)になっている" -- an upward contact
determination. Both the bundled diagnostic (`_covers_from_above`) and
the agent (`candidate_attribute_violations`) implement exactly that:
the mover's bottom within `CONTACT_TOLERANCE` of the protected top.

Measured on 42 recorded terminal states
(`reports/official/soft-rule-gap.md`, ledger
`soft-proxy-is-contact-only-and-therefore-inert`), that predicate fires
on **0.19 soft items per episode and is identically zero on 34 of 42**.
The soft axis has never carried a gradient, so nothing built on it could
move -- which is the mechanical reason the preregistered attribute
filter came back inert at 0 of 16 swaps. A stack-aware reading of the
same states gives 2.24 violated soft items and 5.45 violating pairs,
with 1 of 42 episodes clean, and moves the local ratio from 98.14 to
33.42 (25.17 counting pairs) against an official `soft_item_score` of
19.65. This does NOT identify the official rule -- its normalization and
scene set are unpublished and the closest variant is still 5.5 points
off on development configs.

`candidate_attribute_violations(..., stack_aware=True)` now exists and
is logged beside the shipped reading for every retained candidate.
Nothing selects on it; both fingerprints are unmoved. The staged
protocol is `reports/hazard/soft-stack-protocol.md`, whose Stage 1
shadow measures reach BEFORE an arm is built, precisely because the
attribute filter spent a wave establishing that a predicate which is
zero on four fifths of episodes does nothing.

**A hard attribute gate stays closed.** `release attribute hard reject`
was measured and rejected on placed cost; a wider predicate costs more,
not less.

### The axis is now closed end to end, with no arm licensed

Three measured findings, in order, each with its own preregistration
and verdict:

1. **The shipped predicate is inert** (above): 0.19 violations per
   episode, zero on 34 of 42 boards.
2. **Fixing the predicate gives selection nothing to act on.**
   `reports/hazard/soft-stack/verdict.md`, ledger
   `stack-aware-soft-tiebreak-has-no-reach-in-selection`. A dominance
   tie-break's reach is **0 of 273** multi-candidate decisions against
   a 5% entry gate frozen beforehand, and the verdict is robust rather
   than knife-edge: even R1, which ignores score entirely and is the
   most generous rule writable on that data, reaches 2.2%. Retained
   candidates differ on the axis in only 8 of 273 decisions, because
   retention is by score and the top poses of one item are
   near-duplicates. Stage 2 was therefore never built. The R4 control
   at 0.0% under the shipped reading confirms the attribute filter's
   inert verdict was mechanically guaranteed.
3. **The clean placement is unreachable where it is most needed.**
   `reports/hazard/soft-stack/generation-verdict.md`, ledger
   `soft-clean-placement-exists-in-40pct-of-violating-states`. On 48 of
   293 decisions the played placement covers a soft item; a clean
   candidate was accepted and dropped on 39.6% of them and a better one
   on 52.1%, but on the other 29 decisions **not one of ~311 accepted
   candidates avoids it**. Ambiguous by the frozen thresholds, so no
   arm is licensed. Ceiling of a perfect retention rule: **19 of 293
   decisions, 6.5%**, before any score cost -- and half the reachable
   value needs item-spanning retention, whose three widenings all
   failed fresh-permutation confirmation.

The remaining route to soft is placing more items, which is what every
official component is made of. Nothing in this line changed shipped
behaviour; both fingerprints are unmoved.

### The first H3 post-shake soft learner is rejected at the late gate

Run 32351615182 supplied the first schema-5 distributional H3 labels for
`post_shake_soft_covered_by_other`.  A discovery-only, whole-graph-folded
comparison now runs in `scripts/develop_post_shake_soft_reranker.py`; its
rule-faithful topology representation explicitly preserves the four upper
item classes (plain, priority, soft, soft+priority), and a physical-afterstate
permutation is the negative control.  The discovery winner was the broader
pooled physical afterstate: **26/34**, versus immediate score **25/34**,
action geometry **23/34**, and all seven permuted controls **11--18/34**.
It passed the frozen discovery gate (graph W/T/L **2/1/1**).

The separately frozen one-shot late evaluation then failed decisively:
pooled afterstate **10/32**, action geometry **13/32**, immediate score
**26/32**.  Evidence and the serialized candidate are in
`reports/counterfactual-afterstate-value/post-shake-soft-*-32351615182.*`.
Therefore no live reranker is licensed and `agent/agent.py` is unchanged.
The matrix workflow now repeats both gates for each new collection, leaving
late roots unread whenever discovery fails.  Reopen only on a new physical
collection whose frozen model passes both gates; do not tune on this late
split.  The result localizes the problem as a mid/late condition shift, not
absence of a discovery signal.

## Why each proxy is a proxy (2026-08-18)

`docs/PROXY_SUPPORT.md` is the standing answer to "what is the strategy,
what has to be measurable for it, and why does each local quantity
count as a proxy". Read it before proposing anything that reads a
component.

Its load-bearing result: **a proxy needs variance, not fidelity.** The
soft transcription is correct -- the rule says upward contact and the
code implements upward contact -- but local `soft_clean_ratio` sits at
0.982 and barely moves between arms while the official component moved
threefold across submissions. Computing
`g = official / (local ratio * 100)` independently from the soft and
placement axes gives nearly the same value per submission and one that
climbs steeply with placed (0.07 at 0.434 to 0.22 at 0.505), which is
the amplification `num-placed-gate-amplifies-downward-too` measured
directly. So the official attribute components behave as
`local ratio * g(placed)` and the proxy does not contain `g`. A proxy
saturated at 0.98 is not a control variable however faithful it is.
`priority_clean_ratio` at 0.760 is not saturated, so that side is
healthier.

Consequence for labels: keep all six axes, but treat soft as a
constraint rather than a signal in the current operating regime.

## The attribute-support arm: development FAIL (2026-08-18)

`ATTRIBUTE_SUPPORT_RULE=1` makes `support_surfaces()` admit a protected
top exactly when the mover carries every attribute it is protected by --
the same-attribute stacking the rule allows and the shipped
over-approximation discards. Paired 42-episode wave,
`reports/hazard/attribute-support/development.md`.

The mechanism gate passes decisively: **physical ending rate 38.1% ->
0.0%**. The over-approximation IS costing survival. But only 1 of 7
configs clears its own frozen floor, violations per placed item rise on
both axes, and `shake_max_shift` worsens, so it is not adopted and the
knob stays off. The effect is strongly config-dependent -- three configs
produced identical episodes, one cleared its floor at +6.33 -- which is
the shape any narrower variant would have to exploit, in its own
preregistration on a fresh stream.

## What ends our episodes (2026-08-18)

`reports/hazard/death-budget.md` joins 66 episodes' harness rows with
the last decision of their traces, which separates two things
`terminal_channel` conflates. Replicates and refines
`terminal-failure-channels`.

| cause | share | mean placed fraction |
|---|---:|---:|
| surrender: search accepted nothing, fixed fallback fired | **57.6%** | 0.5052 |
| topple from placement_core | 22.7% | 0.4407 |
| slide from placement_core | 13.6% | 0.4228 |
| topple after a physics_probe_guard rescue | 6.1% | 0.4695 |

In all 38 surrender episodes the deadline was reached and NO candidate
was found for any item, after a mean 7371 attempts. The shipped physics
probe therefore guards the minority channel. This does not reopen the
majority one: `vacuum-cutoff` already turned the true-empty detector
into an in-flight early stop and failed all four gates, and
`last-resort-relaxation` already spent extra effort in exactly this
regime and failed fresh-permutation confirmation. The feasibility phase
structure (P1 deadline-miss 17 vs P3 true-empty 8) already answered
whether those boards are full.

## Measurement hygiene defects found and fixed (2026-08-18)

- **`base` stopped being a baseline** at the quiet-guard adoption. It
  sets no environment variables, so once `PHYSICS_PROBE_MODE` defaulted
  to `guard_quiet`, `base` WAS the shipped agent with the guard -- its
  traces carry `physics_probe_guard` on every step -- and no arm could
  turn the guard off. Every post-adoption base-vs-quiet_guard contrast
  compares the guard against itself plus the observed-pool shadow.
  Fixed: a `guard_off` arm, plus a test that reads the agent's own
  defaults and fails when a knob defaulting to an active value has no
  arm able to switch it off. Ledger
  `base-arm-stopped-being-a-baseline-at-the-guard-adoption`.
- **`measurement_budget` was not concurrency-safe.** A non-atomic
  read-modify-write cost a real episode when a paired batch ran two arms
  at once. Fixed with atomic replace plus an exclusive lock and
  concurrency regression tests.

## The post-shake instrument (2026-08-18): PASSED

Three versions. v1 and v2 both tried to rebuild the terminal state in a
clone and both failed their fidelity gates, v2 on peak kinetic energy,
which a rebuilt world cannot reproduce in principle. The rebuild was
never necessary: `Evaluator.shake_test` computes the post-shake poses in
the LIVE world and discards them at `restoreState`. v3
(`scripts/postshake_capture.py`) records them, so reconstruction error
is zero by construction. All gates pass on 41 episodes across 7 configs
and both arms; `reports/hazard/post-shake/direct-verdict.md`.

Payload: **the shake changes attribute coverage on 6 of 41 episodes**,
soft in both directions and priority one-directionally worse. The
pre-shake proxy is not a noisy version of the post-shake truth. This
does NOT separate the arms -- the apparent arm inversion is two
episodes and both arms are flat with them excluded.

**Rung-3 label generation is unblocked**: labels may be
`(settle_safe, post_shake_stable, post_shake_coverage)` with the third
measured. `NEDO_POSTSHAKE_CAPTURE` is default-off and log-only.

The H3-H5 builder now exposes that same exact capture through
`--post-shake-labels`. It runs one bundled shake on the reconstructed root and
each physical child, then retains the separate stability, soft and priority
axes in `cumulative_outcomes`; the condition-matrix workflow enables it.
`tests/test_attribute_placement_pybullet_e2e.py` settles all 16 lower/upper
soft/priority combinations in PyBullet and compares the resulting bundled
diagnostic against the agent's pre-action legality predicate. Integration CI
sets `NEDO_REQUIRE_INTEGRATION=1`, so a missing PyBullet installation cannot
turn that physical contract into a green skip.

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
- F8 is now measured rather than assumed. Run `31569837492`, two bundled
  cases x two arms x three repeats, found risk-on proposal ranking regressed
  a000 from 28.67 to 22.67 placed and improved a001 only 19 to 20. It also
  evaluated fewer orders under the same budget. Keep the ADR-003 risk-off
  proposal oracle; `OFFLINE_RISK_RERANK=1` remains an experimental arm. Exact
  unpaired permutation testing gives an equal-case placed delta of -2.5
  (p=0.9525 for improvement, p=0.05 for harm, p=0.10 two-sided). With n=3 per
  arm, 0.10 is the best possible two-sided resolution; this is a failed
  adoption gate, not a claim of universal statistical falsification.

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
- Four-point calibration now includes reconstructed `submission22` from
  physical run `31568295912` (4 scenarios x 3 repeats). The fourth point
  refutes the earlier blanket statement that all proxy directions agree:
  several readable cells are only partially concordant.
- The 0–100 normalization and component exchange rates remain unknown. The
  proxies remain diagnostics and can support within-state Pareto checks, not
  a fabricated total score or an attribute-aware live selector.
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

Rewritten 2026-08-16 after the expedition that closed most of the old
list. Everything below is stated with its entry gate; nothing here is a
suggestion to re-run a closed line.

0. **Read the ledger before designing anything** — this list has been
   re-derived by an agent that skipped it, and the cost was a withdrawn
   protocol whose question `reports/anchor-recall/phase-structure.md`
   had already answered, plus a death-budget entry recorded as a
   discovery when it was a replication of `terminal-failure-channels`.
   `AGENT_OPERATIONS.md` §0.2: 導出しない、照会する.
1. **Submission readiness is done — submit when a slot exists.**
   `dist/submission.zip` built from the 2026-08-17 quiet-guard adoption
   commit `d63bace` (SHA-256
   `6ce23e7013149908cf13d3eb0848305b9430166a6d51e7e54e30a20b1d62ca9a`),
   `submit/agent.py` byte-identical to the repository agent, repository
   defaults — which now include `PHYSICS_PROBE_MODE=guard_quiet` with
   the embedded safety artifact, fail-safe when the platform lacks
   pybullet. Rebuild from a fresh fetch if any commit lands after the
   adoption commit.
2. **Safety-reranker campaign: CLOSED 2026-08-16, and what it proved.**
   Gate 1 calibration passed (`safety-shadow-calibration-pass`: live
   perception AUC 0.933, monotone bands, all deaths
   release_candidates). Three Gate 2 waves then ran with clean
   negative controls throughout. Waves 1-2 were inert and the audits
   located two independent blocks (relative-Q pricing vanishes at
   near-zero danger-state scores → absolute bound 1.0; score-selected
   top-3 pools contain no safe alternative, 0/27 versus 18/27 for the
   full set → observed-candidate pool). Wave 3 made the arm act — 35
   swaps — and the gates closed it decisively
   (`development_fail_arm_closed`, run 31955129725): pooled placed
   -37, paired 7W/13L, two no-harm floors breached, and topple+slide
   went 10 → 11, so the swaps did not even buy the safety they paid
   placed for. SAFETY_RERANK_MODE stays default off as a reproduced
   negative experiment. The durable finding: one-step settle safety
   does NOT convert to episode value even with correct pricing and a
   full pool — safety-selected placements are bad board moves whose
   costs compound (the min-q collapse at pool scale). The binding
   constraint on the topple channel is afterstate VALUE, not safety
   perception. The selfplay hazard line then ran and CLOSED at its
   preregistered entry gate (2026-08-17,
   `hazard-entry-gate-failed-line-closed`): the model that robustly
   predicts survival inside the physics-free world (rho 0.48, AUC
   0.835, clean cross-container transfer; transformer rematch lost on
   transfer at 12x data) scores real branch siblings at AUC 0.512
   versus the 0.561 bar — the fourth independent representation to
   fail it. Cheap decision-time state summaries do not carry
   real-physics episode value here, even when they carry value in a
   correlated synthetic world. What remains open is mid-game search
   and labels from real physics at scale; the 94k-row corpus, trainer
   and gate evaluator are committed as reusable instruments. The
   campaign then produced its first shipped-behavior change after all:
   using the physics clone as the arbiter and the calibrated logit only
   as a trigger, the quiet probe guard passed development and a
   corrected fresh-permutation confirmation on three independent stream
   sets (`quiet-guard-confirmed-adoption-licensed`), and
   `PHYSICS_PROBE_MODE=guard_quiet` was adopted as the shipped default
   on 2026-08-17 with the safety artifact embedded in `agent.py`.
3. **State-dependent risk pricing** is the ledger's own named lever for
   the topple channel (`terminal-failure-channels`: most fatal topples
   sat in the ambiguous P band, "insufficient endgame penalty"). Entry
   gate before designing any lambda form: re-derive the 57-death
   postmortem with candidate alternatives and show that at fatal steps a
   materially lower-P accepted alternative existed. Without that, the
   lever is empty; a global lambda raise is already refuted (lambda=2
   loses everywhere).
4. **Pre-action branch direction** needs a new representation. The bar
   is offline and committed: beat pooled placed AUC 0.561 on the
   two-collection deviation corpus (`reports/deviation-corpus/`,
   avoidable label stability kappa 0.86, so the target is real). The
   powered-gate protocol (v5) is the confirmation machinery to reuse.
5. **Fallback v2**: the last-resort clearance ladder passed development
   but failed fresh-permutation confirmation because the rescue is
   inert on ordinary streams (`reports/last-resort/`). A variant must
   target regimes where fallback deaths carry mass and carry its own
   preregistration.
6. **Adjudication discipline** (applies to all of the above): paired
   same-run A/B only, floors from `reports/benchmarks/baseline.json`
   (3v3 resolves 2.2-7.1 placements), never quote a single-run AUC or a
   single-episode delta, and never turn a post-hoc classifier into an
   in-flight controller without measuring its false-fire cost
   (`vacuum-cutoff`).
7. Standing items from the previous list that remain live: the residual
   metric second defect (weighting inside the sum), the untrained
   residual-distance target, and the second real Task A case (external
   data). The 57-substitution multi-axis replay and temporal chunking
   remain closed on their previous terms.

## Verification and operating rules

### Current agent candidate (2026-08-13)

Run `31700909383` paired live-cap and all-visible scans on identical physical
roots. Every pool-over-10 condition had safe cap-excluded items (7/7, gains
+10 to +19), while the pool-10 control was unchanged. Feasible count itself
nearly equals pool size and is rejected as a state-value teacher. The useful
signal is acting-side: cap 20 changes the score-ordered best safe candidate in
all seven affected conditions. The opt-in `late_item_cap20` arm now preserves
cap 10 before six placed items and expands to 20 only in the measured mid/late
band. This is the first current candidate with a direct expected selection-
score mechanism; it still requires a fresh paired episode experiment before
claiming episode or competition-score gain. See
`reports/counterfactual-afterstate-value/paired-feasible-31700909383.md`.

**Final result (2026-08-14): no candidate survived independent arrival-order
confirmation.** Late cap 20 failed the development regression/safety gate
despite pooled placed +0.666. Late cap 16 passed its 30-episode development
gate at placed +2.134 and fill +1.469 with no per-case placed regression, but
fresh k20 permutations reduced it to pooled placed +0.250 with 4 wins / 5
losses. Scoping cap 16 to pools of at most 16 also failed fresh k15
permutations: pooled placed 0.000, 6 wins / 7 losses, and source-001 fill
-0.384. Keep cap 10. The opt-in arms reproduce negative experiments only;
do not describe them as score-improving agents. See
`late-narrow-pool-cap16-confirmation-31706701682.md` in the same report folder.

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
