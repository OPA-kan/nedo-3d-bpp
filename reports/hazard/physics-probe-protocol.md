# In-process physics probe: preregistered fidelity protocol

Committed 2026-08-17 JST before any probe result is opened. Successor
to five closed geometry-proxy lines
(`tree-search-stage1-fail-line-closed`): the one lever that does not
rest on the heightmap proxy is asking the real physics.

## Mechanism (knob `PHYSICS_PROBE_SHADOW`, default off, log-only)

pybullet is importable inside the agent process (the official harness
runs it); the import is guarded so absence degrades to the shipped
behavior with zero footprint. When on, after every placement-core
decision is frozen (the standard seam), the probe:

1. Builds a DIRECT-client scene: container floor/walls from the
   observation's geometry, every packed item spawned at its settled
   pose with the OFFICIAL dynamics copied from
   simulator/src/ground_handling/items.py (lateralFriction 0.8,
   rollingFriction 0.01, spinningFriction 0.01, restitution 0.0,
   angularDamping 0.8; soft items add contactStiffness 5000,
   contactDamping 500, linearDamping 0.8), gravity -9.8,
   deterministicOverlappingPairs=1.
2. Replicates place_item: warps the chosen candidate to its command
   pose and steps the official settle count (settle_wait_step, 300 in
   the development configs).
3. Records a `physics_probe` trace event: predicted settle angle,
   displacement norm, predicted-safe at the official thresholds
   (displacement_threshold 0.3; angle threshold from config), scene
   size, elapsed seconds. Nothing about the played action changes.

Measured cost basis: 40 ms per crowded-scene probe, 66 ms scene
build (spike, 2026-08-17); one probe per step fits the shipped
budget's slack with an order of magnitude to spare.

## Fidelity gates (all required before ANY behavioral wiring)

On 7 guard configs x 2 replicates of probe-shadow episodes, joining
each step's probe prediction with the environment's own settle
outcome (step_metrics):

1. **Discrimination**: pooled AUC >= 0.80 for predicting the
   environment's unsafe settles (angle or displacement over the
   official thresholds) from the probe's predicted values.
2. **Fatal recall**: of the physically-fatal final placements that
   occur in the wave (topple/slide channels), the probe flags at
   least half as unsafe.
3. **Calibration direction**: mean predicted displacement strictly
   higher on actually-unsafe steps than on safe steps; same for
   angle.
4. **Zero footprint**: probe episodes' trajectories within baseline
   floors of base (the log-only contract), per-step time within the
   shipped budget.

Pass licenses a behavioral experiment (probe-gated candidate choice
at trigger steps) under its own preregistration with the standard
{base, null, enforce} x floors machinery. Fail closes the line with
the recorded confusion table — sim-real gap measured at the physics
level — and the fallback direction is shake-component optimization
using the same instrument offline. No retuning of probe physics
constants on these episodes in either case; they are the official
simulator's own constants or nothing.
