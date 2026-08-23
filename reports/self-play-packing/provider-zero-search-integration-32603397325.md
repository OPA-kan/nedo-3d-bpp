# Provider-zero rescue searchable integration

Run: `32603397325` (8/8 shards plus aggregate, success).

## Candidate-support result

- reference censored exhaustion events: 2,473 -> 310 (-2,163)
- reference unique exhausted nodes: 1,206 -> 116 (-1,090)
- provider-zero stride-4 rescue applications: 2,701
- lazy physical checks: 3,523 (1.304 per application)
- physical rejections before the first safe action: 822
- adaptive-K rescue applications: 164
- recovered candidates entering search: 1,939
- root deep-Q-top changes: 15/58
- root deep-visit-top changes: 14/58
- prefix mismatches: 0

This passes the bounded candidate-support repair. It does not establish that a
changed root action improves a fresh trajectory.

## Search-allocation result

- deterministic repeats: 58/58
- H2 S24-to-S48 stable: 40/58
- H2/H3/H5 S48 stable: 15/58
- bounded Q-top stable: 39/58
- bounded visit-top stable: 43/58
- bounded full Q-order stable: 16/58
- stable unique game-state groups: 9/36

The aggressive no-NN schedule matched both deep bounded tops on 45/58 roots
at a mean rollout-step upper bound of 151.4. Full-order confirmation reached
58/58 by construction at 1,239.7. Before provider-zero rescue those values
were 54/58 and 958.3 respectively.

## Verdict

Freeze lazy stride-4 provider-zero rescue as the bounded candidate-support
contract. Do not treat the enlarged-support visit distribution as a stable
policy target. The next model is a played-state multi-head
`V^pi_behavior`, followed by fixed-support `H2+V` versus `H2+0`. Policy and
progressive widening remain later gates.
