# Route-survival shadow screen

- scope: five saved geometry states
- hypothetical immediate placements evaluated: 27
- accepted route probes in the current states: 350
- after hypothetical placement: 169 survived, 181 space-lost, 0 route-lost
- physics: not replayed
- rank effect: none; telemetry only

| case | step | evaluated placements | baseline probes | survived | space-lost | route-lost |
|---|---:|---:|---:|---:|---:|---:|
| b000-k20 | 9 | 15 | 218 | 133 | 85 | 0 |
| b000-k20 | 14 | 1 | 14 | 10 | 4 | 0 |
| b000-k20 | 15 | 7 | 70 | 0 | 70 | 0 |
| b001-k20 | 15 | 1 | 0 | 0 | 0 | 0 |
| b001-k30 | 14 | 3 | 48 | 26 | 22 | 0 |

The implementation can observe corridor-only loss: a focused actual-geometry
test creates a non-overlapping blocker on the transport sweep and obtains one
`route_lost` probe. The zero observed here is therefore a measurement result,
not a dead counter. It does not justify live ranking. See
`docs/ROUTE_SURVIVAL.md` for the contract and scope limits.

The `b001-k20` row has an explicit empty denominator because all retained route
probes belonged to the hypothetically placed item and were excluded.
The upstream generator is deadline-driven, so repeat runs can change the exact
number of evaluated cohort members; these totals describe the committed source
reports.
