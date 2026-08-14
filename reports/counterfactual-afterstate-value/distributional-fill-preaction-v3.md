# Distributional fill pre-action student v3

The frozen artifact is `distributional-fill-preaction-v3.json` (SHA-256
`ff770d0c116743879c9ed9b426f6994504deaff64d2825c2b455aa8589397649`).
It uses 116 inference-time features derived from the source tensor and two
candidate commands: container clearances, nearest packed-item distances,
horizontal overlap, vertical support gap, nearby soft/priority counts, pool
statistics, item physics, and their pairwise differences. Immediate score,
step, post-settle state, and future labels are excluded.

## Development result

The same 1,971 inspected discovery rows through seed 57 reduce to 338 exact
pre-action signatures. Any signature appearing in a held-out stream is removed
from training even when it also appears under another stream. Under this strict
leave-one-stream-out contract, L2 `10.0`, override margin ratio `1.0`, and a
training-only nearest-support q90 gate score 242/350 versus 224/350 for action
geometry, with no regression in any of the four streams.

On 137 globally unique inspected late signatures, v3 scores 99 versus 86 for
action geometry and 75 for v1. The paired v3/action result is 16 wins, 118 ties,
and 3 losses (`p=0.004425048828125`). Late per-stream v3/action results are
17/14 (`interleave`), 70/60 (`original`), 10/9 (`reverse-000`), and 3/4
(`source-001`). The remaining one-row source regression is why new-stream
confirmation is mandatory despite the stronger primary CV result.

## Confirmation gate

Before labels, declare deterministic multiset-preserving item-stream variants
not used by v3. A snapshot-only screen may reject a variant solely for missing
declared roots across the eight-condition matrix. At least three complete
variants, 30 unique late pre-action signatures, and 50% unique support are
required before scoring.

The unchanged v3 passes only if every admitted variant is non-regressing versus
action geometry on unique signatures, pooled paired wins exceed losses, and
the two-sided exact sign-test is at most 0.05. Passing establishes an offline
branch-direction agent candidate only; an actual episode-score A/B is the next
separate gate.

## Label-blind root screen

The initial screen used Actions runs `31771576478`, `31771577234`,
`31771574718`, and `31771576168` with graph expansion disabled. Only
`permute-000-17` and `permute-001-31` completed all eight conditions.
`permute-000-29` missed single-preloaded; `permute-001-23` missed
single-preloaded and dual-empty. No H3 labels were generated or scored, and the
initial minimum-three admission gate was inconclusive.

Before any label run, expand the label-blind cohort with `permute-000-41`,
`permute-000-53`, `permute-001-43`, and `permute-001-59`. Continue only if at
least four of all eight declared variants complete every matrix condition.
The two previously complete variants remain unopened; root availability is the
only admission criterion.

The expansion screen ran as `31772304481`, `31772303043`, `31772303592`, and
`31772300707`. `permute-001-43` and `permute-001-59` completed all conditions;
`permute-000-41` missed single-preloaded and `permute-000-53` missed
dual-empty. The fixed four-variant admitted set is therefore
`permute-000-17`, `permute-001-31`, `permute-001-43`, and `permute-001-59`.
This meets the expanded four-of-eight availability gate without opening H3
labels.

Full H3 collection then completed for `permute-001-31`, `permute-001-43`,
and `permute-001-59` in runs `31772903807`, `31772905024`, and `31772905325`.
Run `31772905671` (`permute-000-17`) failed strict root reconstruction in
dual-shelf: quaternion-component drift was `0.0022308429`, above the fixed
`0.002` tolerance. The tolerance is unchanged and no completed label artifact
has been opened. Before scoring the three sealed complete runs, screen
`permute-000-61` and `permute-001-67` as label-blind replacements; at least one
must subsequently complete the full H3 matrix to restore the fixed four-run
confirmation set.
