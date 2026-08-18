# Post-shake instrument v2 (pose snapshots): fidelity gate adjudication

Protocol: `reports/hazard/post-shake-instrument-protocol.md` -- the same
frozen gates that adjudicated v1. No threshold, no clone constant and no
reconstruction rule was changed after any v2 number was opened. Raw
joined table: `reports/hazard/post-shake/revalidation-fidelity.md` /
`revalidation-fidelity.json`.

## What changed between v1 and v2

Only the reconstruction source. v1 rebuilt each episode from per-step
`settle_final` poses, which record each item at its OWN placement step
and never again; later placements disturb them unrecorded. v2 rebuilds
from `NEDO_POSE_SNAPSHOT=1` policy-trace events (`agent/agent.py`,
registered `diagnostic` / semantic false; `run_risk_ablation
--pose-snapshot`), which carry the CURRENT pose of every packed item at
every policy step as the env itself reports it. The last snapshot
therefore sees every disturbance up to the final decision. The clone,
the shake, the dynamics and the coverage rules are byte-identical to
v1.

The agent's behaviour is unchanged: the knob is log-only and the
optimizer fingerprint `behaviour_sha256` did not move.

## Validation data

42 recorded episodes collected for this adjudication:
`reports/raw/post-shake-revalidation/` -- 7 development configs
(b000-k15, b000-k20, b000-k40, b001-k20, b001-k30, c000-k1, c001-k1) x
arms {base, quiet_guard} x 3 replicates, every run with
`--pose-snapshot`. 42/42 completed, zero harness failures. This meets
the protocol's ">= 40 recorded episodes spanning base and quiet_guard
arms" (21 + 21).

## Gate results (preregistered thresholds, nothing tuned)

| gate | threshold | v1 | v2 | result |
|---|---|---|---|---|
| Spearman cloned vs recorded `shake_max_shift` | >= 0.8 | 0.256 | **0.762** | **fail** |
| Spearman cloned vs recorded `shake_items_shifted` | >= 0.8 | 0.820 | **0.931** | pass |
| `shake_items_toppled` within +-1 | >= 80% of episodes | 79.4% | **95.2%** (40/42) | pass |
| quiet_guard peak-KE excess sign | matches recorded | -32.6% vs +23.9% | -24.9% vs +19.3% | **fail** |

## Verdict: FAIL -- the instrument is still not trusted

Every gate moved in the right direction and two of the four now clear
the bar, but the protocol's fail branch is unconditional: until all
four pass, the clone does not become a wave-adjudication column, and
**rung 3's label generation stays blocked** (ledger rule
`post-shake-instrument-fails-on-reconstruction`). Official submissions
remain the only trusted soft readout.

## Where the residual lives -- it moved

v1's failure was reconstruction: 31/63 episodes drifted >0.3 m when
rebuilt, precarious late boards collapsed before the shake even
started, and all three geometry gates failed together. The snapshot fix
removed that failure mode. v2's two survivors have separate,
better-localized causes.

### 1. Displacement geometry is now good, but max_shift is a tail problem

Per-episode clone-vs-recorded error across the 42 episodes:

| quantity | median abs err | p90 abs err |
|---|---:|---:|
| `shake_max_shift` | 0.0435 m | 0.2001 m |
| `shake_items_shifted` | 0.5 items | 2 items |

The bulk of the distribution is tight; the correlation is dragged under
0.8 by a tail. The report's own non-binding low-drift diagnostic
(episodes whose rebuilt poses moved <= 0.3 m during the pre-shake
re-settle, 30 of 42) reads Spearman 0.913 for max_shift and 0.974 for
items_shifted -- i.e. once the rebuilt state is a true equilibrium, the
shake clone tracks the real one. What remains unrecorded in BOTH modes
is the final placement's own 300-step settle: the last snapshot
precedes the final decision, so whatever that last drop pushes is
invisible, and `max_shift` -- a single-item extremum -- is exactly the
statistic a single unrecorded nudge can move.

### 2. Peak kinetic energy is not reproducible in the clone at all

The direction gate rides entirely on peak KE, and peak KE is the one
recorded quantity the clone cannot track:

- `|log(cloned/recorded)|`: median 0.116, mean 0.451, max 1.745
- **13 of 42 episodes have a cloned peak KE off by more than 2x**
  (e.g. 118.1 vs 32.7, 49.4 vs 8.6, 97.9 vs 21.8, 2.9 vs 8.2)

Peak KE is a transient extremum over the shake, set by contact
micro-state -- the least stable thing a rebuilt world could be asked to
reproduce, and unlike shift/topple it is not a quantity the official
score reads. A gate built on it was the wrong instrument for the
question, which is a finding about the protocol, not an excuse: the
gate was preregistered and it failed.

### 3. This stream cannot separate the arms well enough to test a direction

Counting recorded episode signatures (`max_shift`, `items_shifted`,
`toppled`, `peak KE`, item count):

| case | distinct outcomes across 6 runs | base runs with an identical quiet_guard twin |
|---|---:|---:|
| b000-k15 | 3 | 1/3 |
| b000-k20 | 3 | 1/3 |
| b000-k40 | 3 | 1/3 |
| b001-k20 | 2 | 2/3 |
| b001-k30 | 3 | 1/3 |
| c000-k1 | 1 | 3/3 |
| c001-k1 | 1 | 3/3 |
| **total** | | **12/21** |

On c000-k1 and c001-k1 the guard never changed the episode at all, and
overall 12 of 21 base runs have a byte-identical outcome twin in the
guard arm. The guard fires on ~20% of steps and approves the incumbent
most of the time, so on easy boards the arms coincide; the residual
variation is the time-budgeted search landing in different basins on a
loaded 4-core runner. The recorded +19.3% excess is therefore carried
by ~9 effective pairs. That does not rescue the verdict -- the gate
failed as written -- but it means this stream was underpowered for that
particular contrast, and a future direction gate needs an arm-separation
precondition rather than a raw arm average.

## What this does and does not license

- Rung 3 (learned proposer trained on probe-generated labels) stays
  BLOCKED. Labels must be (settle_safe, post_shake_stable,
  post_shake_coverage); the third component is still not measurable to
  gate standard.
- The post-shake coverage columns in the joined table are NOT adopted
  as a measurement column and take no part in any wave adjudication.
- Nothing in the shipped agent changes. `PHYSICS_PROBE_MODE=guard_quiet`
  and its embedded safety model are untouched; `NEDO_POSE_SNAPSHOT`
  stays default-off and log-only.
- No constant in this instrument may now be adjusted and re-scored on
  these 42 episodes. Any v3 must be preregistered separately and
  adjudicated on a fresh stream.
