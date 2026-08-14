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
