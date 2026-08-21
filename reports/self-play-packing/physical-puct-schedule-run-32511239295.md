# Physical PUCT revisit and temperature audit

## Decision

Twelve physical simulations are sufficient for PUCT values to change root
visits in late states. Sampling from those visits at every step can still pick
a known worse action. Sampling through step five and taking the maximum-visit
action from step six removes that observed self-inflicted attribute penalty.

This is evidence that the search/action interface works, not yet evidence that
PUCT beats the rank-0 baseline across fresh scenarios.

## Paired progression

All arms used the same single-container, no-shelf scenario and environment/game
seeds.

| Arm | Root budget | Action rule | Non-rank-0 | Attribute violations | P0 reward | Fill score |
| --- | ---: | --- | ---: | ---: | ---: | ---: |
| rank-0 control | none | rank 0 | 0 | 0 | +50 | 9.5477 |
| PUCT cold start | 6 | sample all steps | 5 | 1 | +45 | 9.4348 |
| PUCT revisit | 12 | sample all steps | 5 | 1 | +45 | 9.4348 |
| PUCT scheduled | 12 | sample steps 0-5, greedy after | 2 | 0 | +50 | 9.5477 |

The 12-simulation sampled run first produced non-uniform roots at steps eight
and nine. At step nine its visits were `7,1,4` and Q estimates were
approximately `+0.43,-1,0`. The six-simulation run had ended at equal `2,2,2`
visits everywhere, so it could not express the Q separation as a policy.

The scheduled run followed the same early exploratory rank-1 moves at steps
two and five, then selected rank 0 at every step from six onward. At step nine
it selected the seven-visit action rather than sampling either inferior edge.
It produced zero selected physical failures, zero attribute violations, 120
fresh physical simulations, 10 policy targets, and 11 eligible value targets.

Its final physical metrics were effectively identical to the paired rank-0
control: 10 placements, fill score 9.5477, fill proxy 14.8766%, and shake peak
kinetic energy 7.6708 versus 7.6709. Therefore the measured gain is recovery
from the always-sampling PUCT arm, not superiority over baseline.

## Next gate

Run the scheduled policy across multiple paired environment/game seeds and the
representative scenario matrix. Keep a separate always-sampling arm for state
distribution coverage. Only call the search agent better if the scheduled
evaluation arm improves prevalence-weighted production metrics on held-out
paired scenarios without increasing physical rejects or soft/priority
violations. The generated `(state, pi, G_t)` rows are now ready for an initial
P/V learner after that evaluation split is fixed.

## Evidence

- six-simulation run: https://github.com/OPA-kan/nedo-3d-bpp/actions/runs/32509769499
- twelve-simulation sampling run: https://github.com/OPA-kan/nedo-3d-bpp/actions/runs/32510546821
- twelve-simulation scheduled run: https://github.com/OPA-kan/nedo-3d-bpp/actions/runs/32511239295
- implementation commits: `53e669d`, `3d113e6`, `e5288c2`, `0406761`
- scheduled raw artifact: `self-play-physical-puct-32511239295`
