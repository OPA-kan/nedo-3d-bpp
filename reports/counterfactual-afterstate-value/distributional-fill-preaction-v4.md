# Distributional fill pre-action student v4

The frozen artifact is `distributional-fill-preaction-v4.json` (SHA-256
`a606c534d34d8c5d6606df2e7768b9b071bd4dcaff5dfd02367247b734847c58`).
It retains v3's 116 label-blind local-geometry features and replaces the linear
ridge predictor with a standardized k-nearest-neighbor predictor. Immediate
score, step, post-settle state, and future labels remain excluded.

## Why v4 exists

Frozen v3 failed its seed-58 prospective confirmation: 29/43 versus 30/43 for
action geometry, with 2 wins and 3 losses. Its linear boundary did not reliably
separate locally similar states. The five confirmation streams are now opened
development data and cannot be used to confirm v4.

## Development contract

All eligible discovery and late rows through the five seed-58 confirmation
streams produce 3,159 rows and 716 exact pre-action signatures. Cross-fitting
predicts every exact signature exactly once. When a signature occurs in more
than one stream, all attached streams are simultaneously removed from its
training fold. This prevents both exact-signature leakage and duplicate pooled
scoring.

The fixed grid contains 288 policies over neighbor count, distance weighting,
training-only nearest-support quantile, and the margin required to override
action geometry. Selection first requires every stream to be non-regressing,
then maximizes pooled correctness, minimizes losses, maximizes wins, and uses
documented deterministic conservative tie-breaks.

The selected policy uses three distance-weighted neighbors, the maximum
training leave-one-out support distance, and an override ratio of 8.0. Strict
group-complement cross-fit scores 472/716 versus 452/716 for action geometry:
33 wins, 670 ties, and 13 losses (two-sided exact sign test
`p=0.004533861582189047`). All nine development streams are non-regressing.

These are inspected development results after model selection, not prospective
evidence. V4 remains `frozen_pending_new_stream_confirmation`.

## Prospective gate

Before any new H3 labels are opened, admit stream variants using root-only
availability checks. At least four admitted streams must complete the strict
eight-condition H3 matrix. The unchanged artifact passes only with at least 30
unique late signatures, at least 50% unique support, every completed admitted
stream non-regressing versus action geometry, pooled wins greater than losses,
and a two-sided exact sign-test at most 0.05.

Passing establishes an offline branch-direction candidate only. Episode-score
A/B remains a separate required gate before claiming a scoring agent.
