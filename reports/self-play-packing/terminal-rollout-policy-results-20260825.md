# V-free terminal-rollout policy pilot — 2026-08-25

Actions run `32753033451` at commit `d78ee2f` completed all six physical
scenario cells and the aggregate successfully.  The paired arms used the same
scenario, item stream, environment seed and deterministic physics.  No value
model or scalar utility participated in search or action selection.

## Aggregate result

| Measure | Result |
|---|---:|
| cells | 6/6 |
| complete terminal-truth roots | all |
| censored roots | 0 |
| terminal-dominance switches | 1 |
| terminal rollout physical steps | 882 |
| mean live placed-step delta | +0.167 |
| final Pareto relation | 1 rollout-dominates, 5 equal |

Five cells exactly reproduced the legacy trajectory.  In
`dual-preloaded-dedicated-source-001`, terminal rollout switched the action at
live step 6.  That trajectory placed one additional item and improved fill
from `9.6279` to `10.6318`.  CoG fell from `0.7874` to `0.6665`, surface total
variation fell from `0.016080` to `0.015897`, peak shake KE fell from `4.5634`
to `4.5121`, and direct published-rule soft/priority violations remained zero.
Maximum shake shift increased by about `9.5e-6`; toppled items stayed zero.

At the switching root, incumbent terminal continuation produced fill gain
`4.1094` with six further placements, while the chosen candidate produced fill
gain `5.1133` with seven.  The chosen candidate was non-worse on every active
dominance head and strictly better on fill and surface variation.  Its
stack-aware soft diagnostic increased, but the direct-contact published-rule
soft metric stayed zero; stack telemetry is not used as an official violation
surrogate.

## Verdict

This is a positive capability result, not yet a prevalence or production-cost
result.  Exact rollout can discover a trajectory improvement that the legacy
ranker misses, and the conservative dominance-only selector did not regress any
of the six terminal vectors.  The effect is sparse (one switch) and expensive
(882 simulated physical steps for 54 live rollout-policy placements), so the
next experiment should preserve rollout as the oracle while reducing when and
how many candidates receive full continuation.

## Identical-item symmetry ablation

Actions run `32758581833` at commit `1e767da` repeated the same six cells after
enabling exact identical-item reuse. It reproduced the original result exactly:
one terminal-dominance switch in `dual-preloaded-dedicated-source-001`, one
additional placement, one rollout-dominating terminal vector, five equal
vectors, and zero censored roots.

The root-local genuine-terminal cache recorded 24 hits and reduced executed
terminal rollout steps from `882` to `737`: `145/882 = 16.4%`. It also reports
`1,287` replay-inclusive physical-step equivalents avoided. The executed
terminal workload was `5,959` replay-inclusive equivalents, so the estimated
uncached workload is `7,246` and the corresponding reduction is `17.8%`.

The exact legal-filter action-orbit reuse path recorded zero hits in this
workload. Frozen rank-0 continuation asks the filter for only the first safe
candidate and stops before a second identical alias is classified. The path is
active for wider callers, but this run provides no empirical speedup claim for
it. The separately rerun physical equivariance workflow `32758581451` remained
green across all six cells; Linux CPU verification `32758581897` also passed.
