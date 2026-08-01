# Visible-pool rollout shadow

- snapshot: `reports/replay-dataset/20260731_143112-b000-k20-weighted-class_aware-shadow-0fb74669-53f3e88bdd6f/step-009-state.json`
- depth: 3
- attempts per future step: 512
- initial release transitions use the settled proxy and are marked; future release transitions stop the branch before application.

| rollout rank | item | immediate rank | Q_live | placed | added volume | P_rot sum | P_slide sum | terminal | observed |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| 1 | 17 | 75 | -0.4481 | 1 | 0.0800 | 0.1543 | 0.1413 | release_transition_uncertain | left |
| 2 | 28 | 1 | -0.2056 | 0 | 0.0000 | 0.6497 | 0.1057 | release_transition_uncertain | - |
| 3 | 28 | 2 | -0.2317 | 0 | 0.0000 | 0.6497 | 0.1057 | release_transition_uncertain | - |
| 4 | 28 | 3 | -0.2373 | 0 | 0.0000 | 0.6497 | 0.1057 | release_transition_uncertain | - |
| 5 | 28 | 4 | -0.2477 | 0 | 0.0000 | 0.6497 | 0.1057 | release_transition_uncertain | - |
| 6 | 28 | 5 | -0.2652 | 0 | 0.0000 | 0.6497 | 0.1057 | release_transition_uncertain | - |
| 7 | 28 | 6 | -0.2653 | 0 | 0.0000 | 0.6497 | 0.1057 | release_transition_uncertain | - |
| 8 | 28 | 7 | -0.2709 | 0 | 0.0000 | 0.6497 | 0.1057 | release_transition_uncertain | - |
| 9 | 28 | 8 | -0.2899 | 0 | 0.0000 | 0.6497 | 0.1057 | release_transition_uncertain | - |
| 10 | 28 | 13 | -0.3465 | 0 | 0.0000 | 0.6497 | 0.1057 | release_transition_uncertain | right |

## Interpretation boundary

This is a deterministic static-proxy rollout over the currently visible pool. It is not a value over unknown future arrivals and does not claim physical validity for a release settle.
