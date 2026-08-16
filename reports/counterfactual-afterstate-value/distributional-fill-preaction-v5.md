# Distributional fill pre-action student v5

The frozen artifact is `distributional-fill-preaction-v5.json` (SHA-256
`52494cddfc5a5d486f7e753e7ff408982540f2edb48f1b37f18e576f13ae2590`).
It keeps v4's 116 label-blind local-geometry features and its standardized
k-nearest-neighbor predictor family, and refits under the identical
group-complement cross-fit contract on every opened stream. Immediate score,
step, post-settle state, and future labels remain excluded.

## Why v5 exists

Frozen v4 failed its seed-59 prospective confirmation on the predeclared
gate, but not by measuring an effect: it scored 40/74 versus 39/74 with only
2 wins and 1 loss, an exact sign test of `p=1.0`. Three discordant pairs
cannot reach `p<=0.05` under any outcome, so the confirmation was structurally
underpowered before its labels were opened. Two consequences:

1. The five seed-59 streams are now opened development data and joined the
   training corpus.
2. The prospective protocol gains a power gate so a confirmation that cannot
   detect the development-sized effect is never spent again.

## Development contract

All eligible discovery and late rows through the five seed-59 confirmation
streams produce 3,776 rows and 1,053 exact pre-action signatures across 14
streams. Cross-fitting predicts every exact signature exactly once; every
stream attached to a signature is simultaneously removed from its training
fold. The fixed grid is v4's 288 policies over neighbor count, distance
weighting, training-only nearest-support quantile, and override margin.
Selection first requires every stream to be non-regressing, then maximizes
pooled correctness, minimizes losses, maximizes wins, and applies the same
documented deterministic conservative tie-breaks.

The selected policy uses nine distance-weighted neighbors, the maximum
training leave-one-out support distance, and an override ratio of 1.0.
Strict group-complement cross-fit scores 719/1053 versus 657/1053 for action
geometry: 127 wins, 861 ties, and 65 losses (two-sided exact sign test
`p=9.05e-6`). All 14 development streams are non-regressing.

These are inspected development results after model selection, not
prospective evidence. V5 is `frozen_pending_powered_new_stream_confirmation`.

## Powered prospective gate

The development win fraction is 127/192 = 0.661. At that effect size the
exact two-sided sign test at `alpha=0.05` reaches 50% detection probability
only at 37 or more discordant pairs; below six it cannot reject at all. The
frozen artifact therefore carries `minimum_discordant_pairs = 37`, computed
at freeze time and not tunable afterwards.

Discordance is countable label-blind: on a directionally eligible row, the
candidate and action geometry predict from tensors alone, and when their
binary directions differ exactly one of them will be correct. The
`--power-audit-output` mode of `develop_distributional_fill_preaction_v5.py`
opens only directional eligibility, never which direction is true.

The confirmation protocol is:

1. Admit stream variants by root-only availability screens, exactly as for
   v4. No H3 label evidence may exist when a cohort is declared.
2. Run the strict eight-condition H3 matrix on every admitted stream.
3. Run the label-blind power audit over all admitted completed streams. If
   supported prediction disagreements are below 37, declare and screen more
   streams; do not open direction labels.
4. Only when the audit is powered, evaluate the unchanged artifact exactly
   once. The gate requires at least four complete streams, at least 30
   unique late signatures, at least 50% unique support, every completed
   admitted stream non-regressing versus action geometry, pooled wins
   greater than losses, a two-sided exact sign test at most 0.05, and at
   least 37 discordant pairs.

An underpowered evaluation, should one ever be recorded, neither confirms
nor rejects the candidate; its labels become opened development data.

Passing establishes an offline branch-direction candidate only. Episode-score
A/B remains a separate required gate before claiming a scoring agent.

For cohort sizing only, the frozen model disagrees with action geometry on
31/74 unique late signatures of the (in-training, therefore optimistic)
seed-59 cohort. At that rate roughly six to nine admitted streams reach 37
discordant pairs; the audit, not this estimate, decides.

## Label-blind root screen

The v5 cohort is declared before any v5 confirmation labels exist:
`permute-000-151`, `permute-000-157`, `permute-000-163`, `permute-000-167`,
`permute-000-173`, `permute-000-179`, `permute-001-151`, `permute-001-157`,
`permute-001-163`, `permute-001-167`, `permute-001-173`, and
`permute-001-179`, all at environment seed 60 and unchanged H3/B3. Root
availability remains the sole admission criterion. Every admitted stream
that later completes strict H3 must be evaluated. If the label-blind power
audit over admitted completed streams stays below 37 discordant pairs, the
cohort is expanded with further fresh salts under the same rule.

The screen completed with no H3 label evidence in existence. Admitted with
all eight root conditions: `permute-000-157` (run `31922206907`),
`permute-000-163` (`31922208084`), `permute-000-167` (`31922213297`),
`permute-000-173` (`31922214137`), `permute-000-179` (`31922215300`),
`permute-001-151` (`31922219161`), `permute-001-157` (`31922220380`), and
`permute-001-167` (`31922224805`). Rejected on failed root conditions:
`permute-000-151` (`31922202291`, dual-empty), `permute-001-163`
(`31922221445`, dual-empty and single-shelf), `permute-001-173`
(`31922226138`, dual-empty), and `permute-001-179` (`31922227127`,
dual-empty). The fixed prospective H3 set is therefore these eight admitted
streams at environment seed 60.

## First power audit: expand before evaluating

All eight admitted streams completed the strict eight-condition H3 matrix
and aggregation in runs `31922956917`, `31922959491`, `31922962709`,
`31922965559`, `31922968969`, `31922972142`, `31922975070`, and
`31922977895`. The label-blind power audit over their 311 eligible late rows
(145 unique pre-action signatures, 46.6% unique support) counted 27
prediction disagreements, below the frozen minimum of 37. Following the
predeclared protocol, no direction label was opened and no confirmation was
evaluated.

The cohort is expanded with eight further fresh salts, declared with no v5
direction-label evidence in existence: `permute-000-181`, `permute-000-191`,
`permute-000-193`, `permute-000-197`, `permute-001-181`, `permute-001-191`,
`permute-001-193`, and `permute-001-197`, all at environment seed 60 and
unchanged H3/B3. Root availability remains the sole admission criterion, and
every admitted stream that completes strict H3 joins the audit population.

The second screen also completed label-blind. Admitted with all eight root
conditions: `permute-000-181` (run `31924378093`), `permute-000-193`
(`31924385051`), `permute-001-181` (`31924393295`), `permute-001-193`
(`31924400471`), and `permute-001-197` (`31924403151`). Rejected:
`permute-000-191` (`31924381636`, dual-empty), `permute-000-197`
(`31924389044`, dual-empty), and `permute-001-191` (`31924397063`,
single-preloaded). The admitted prospective set is therefore thirteen
streams: the eight first-wave streams plus these five.

Wave-2 strict H3 completed for `permute-000-181` (run `31924933160`),
`permute-000-193` (`31924935917`), `permute-001-181` (`31924939279`), and
`permute-001-193` (`31924942234`). `permute-001-197` (`31924945370`) failed
its dual-empty condition and is excluded as an incomplete strict matrix; its
labels were never opened. The second label-blind power audit over the twelve
completed streams counted 452 eligible late rows, 229 unique signatures
(50.7% unique support, all within the frozen support threshold), and 42
prediction disagreements, at or above the frozen minimum of 37. The
confirmation was therefore opened.

## Prospective confirmation result

The frozen artifact was evaluated exactly once, without refitting or
changing any threshold. V5 scored 161/229 versus 157/229 for action
geometry: 23 wins, 187 ties, and 19 losses (two-sided exact sign test
`p=0.644`). Three completed streams regressed: `permute-000-167` (27 versus
28), `permute-001-151` (12 versus 14), and `permute-001-157` (9 versus 10).
Full results are in `distributional-fill-preaction-v5-confirmation-60.json`.

The predeclared gate **failed** on both the non-regression and significance
checks, and this time the test was powered: 42 discordant pairs could have
detected the development-sized effect with even odds. The out-of-development
win fraction was 23/42 = 0.548 against 0.661 in cross-fit. V5 is rejected as
a confirmed branch-direction agent.

## Verdict on the representation line

This is the third consecutive candidate from the 116-feature label-blind
local-geometry family to fail a new-stream confirmation: v3 (linear ridge,
seed 58), v4 (kNN, seed 59, underpowered), and v5 (kNN on all opened
streams, seed 60, powered). With adequate power the family's strict
cross-fit advantage did not transfer to genuinely new streams. Do not
develop a v6 by re-tuning the same features on the enlarged corpus; the next
candidate requires a new representation hypothesis or a different label
target. The seed-60 labels are now opened development data. The powered-gate
protocol itself worked as designed and carries forward: the first cohort's
underpowered state was detected label-blind and no confirmation was wasted
on it.
