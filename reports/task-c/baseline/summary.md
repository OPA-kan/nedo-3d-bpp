# Task C baseline (first measurement)

Date: 2026-08-02. Local 4 vCPU, Python 3.12, PyBullet 3.2.7.

Task C had never been run in this repository. Every ablation case is
`b<source>-k<pool>` with pool >= 10, and `reports/benchmarks/baseline.json`
has no pool-1 row. This is the first Task C measurement, so there is nothing
to compare it against and no claim of improvement is made here.

## Configuration

Task C is `agent.optimize = false` with `item_stream.look_ahead = 1`, which is
what `scripts/build_task_b_config.py --look-ahead 1` produces. The bundled
sample cases are neither: case 000 is `look_ahead 1` but `optimize true`
(Task A) and case 001 is `look_ahead 10` (Task B).

| case | source | items | shelf | policy timeout |
|---|---|---:|---|---:|
| `c000-k1` | sample case 000 | 41 | no | 8.0 s |
| `c001-k1` | sample case 001 | 42 | yes | 8.0 s |

Arm `base` (shipped defaults: rot lambda 1.0 mech, slide lambda 0.5,
class-aware coverage, rescue/cross-step/rollout all off), 2 repeats each.

## Result

| case | repeat | placed | fill | steps | process s |
|---|---:|---:|---:|---:|---:|
| c000-k1 | 0 | 21 | 17.310 | 22 | 81.5 |
| c000-k1 | 1 | 21 | 17.310 | 22 | 81.4 |
| c001-k1 | 0 | 18 | 23.560 | 19 | 52.2 |
| c001-k1 | 1 | 18 | 22.256 | 19 | 51.7 |

`c000-k1` is bit-identical across repeats. `c001-k1` holds placed constant and
moves fill by 1.3, the same timing nondeterminism already recorded for b001
configurations.

Neither episode is a passing episode: both end with `is_valid` and
`is_placed_safe` false. Per the repository rule, a zero exit code is not a
success.

## The single death channel

All four episodes end the same way:

| case | final step | action | status |
|---|---:|---|---|
| c000-k1 | 21 | item 21, orientation 0, `[0.0, 0.0, 0.25]` | included, not valid, not safe |
| c001-k1 | 18 | item 18, orientation 0, `[0.0, 0.0, 0.25]` | included, not valid, not safe |

`[0.0, 0.0, 0.25]` with orientation 0 is the `unsafe_protocol_fallback`
constant in `agent.py`. The policy trace confirms it directly: 21 decisions
from `placement_core` and one from `unsafe_protocol_fallback`, with
`internal_outcome = no_safe_action` and `top_candidate_count = 0` on the
fatal step.

So in Task C the fixed-coordinate fallback is **4 of 4** episode endings.
Under Task B the same channel is 45% of endings
(`transport-deaths-are-fallback-poison`). The mechanism is the one predicted
by `TASK_C_BOARD_VALUE.md` section 13: with a pool of one there is no
alternative item to escape to, so every no-candidate step is fatal.

## Fatal-step search state (c000-k1 step 21)

From `candidate_diagnostics.search`:

- `units_total` 12 (1 item x 6 orientations x 1 container x 2 kinds)
- `units_started` 24, `units_completed` 9, `rounds_started` 13
- `deadline_reached` true, `incumbent_updates` 0
- `item_indices_with_candidates` empty
- support-plane search reports 15 components and 1420 anchors for
  orientation 0 alone

The search therefore did **not** exhaust the space before the deadline: 3 of
12 units never completed and zero candidates were accepted. Whether an
acceptable candidate existed in the unvisited part is not established by this
run; it is the question the next experiment has to answer, and the Task B
rescue-scan evidence (37/37 late snapshots recovered a statically valid
candidate) is suggestive but was measured on a different search load.

## Timing

Episodes are far cheaper than Task B: 22 steps in 81 s including physics.
Early steps finish well inside the 6.5 s internal budget; the late steps,
including the fatal one, hit `deadline_reached`. So spare budget exists
early and not late, which is the opposite of what a terminal time reserve
assumes -- the design already rejected as `deadline-reserved-rescue-rejected`.

## Scope

Two cases, two repeats, one arm, local hardware. This fixes a reference
point and identifies the death channel. It does not compare policies, and
none of the numbers should be quoted as a competition score.
