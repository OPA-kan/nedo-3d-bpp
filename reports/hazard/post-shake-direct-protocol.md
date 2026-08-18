# Post-shake instrument v3: direct capture (preregistration)

Written before any v3 number exists. The v2 adjudication
(`reports/hazard/post-shake/revalidation-verdict.md`) is closed and
FAILED; nothing below is a retune of it, and none of its 42 episodes
may be rescored under this protocol.

## Why v3 is a different instrument, not a tuned v2

v1 and v2 both tried to *rebuild* the terminal state in a second
DIRECT world and shake the copy. v2's snapshots removed most of the
reconstruction error but two gates still failed, one of them
(`peak KE` direction) on a quantity that a rebuilt world cannot
reproduce in principle: 13 of 42 episodes were off by more than 2x.

Reading `simulator/src/ground_handling/evaluator.py` closes the
question. `Evaluator.shake_test` already computes, in the LIVE world:

    before = self._live_poses(containers)     # exact terminal pre-shake state
    ... official shake schedule ...
    after  = self._live_poses(containers)     # exact post-shake state
    finally: restoreState(...)                # discards it

The post-shake state we have been trying to approximate is computed by
the official code on every run and then thrown away. `_live_poses` is
called from nowhere else in the module (`settled_snapshot` reads poses
directly and does not use it), so it is an unambiguous interception
point.

v3 therefore does not rebuild anything. It records what the official
shake already produced. There is no clone, no re-settle, no
reconstruction and hence no reconstruction error to gate.

## What v3 does

A harness-side recorder (`scripts/postshake_capture.py`, imported by a
thin wrapper the ablation harness invokes instead of the bundled
`run_test.py`) wraps `Evaluator._live_poses` for the duration of one
`shake_test` call. On the SECOND call inside that invocation -- the
post-shake one -- it delegates to the original and then, while the
world is still in its post-shake state, additionally calls the
evaluator's own `settled_snapshot(containers)`. That call only reads
(`get_pose`, `getAABB`); it steps nothing, and `shake_test`'s `finally`
restores the state either way.

The captured post-shake metrics are produced by
`calculate_attribute_placement` -- the same function the pre-shake
proxy uses. The soft/priority contract is NOT reimplemented for the
post-shake side.

Nothing under `simulator/` is modified. The agent is not modified; no
knob is added to `context/knobs.json`; `behaviour_sha256` must not
move.

## Gates (frozen; a gate that fails is reported as failed)

**G1 -- no-op.** For >= 6 episodes spanning >= 3 configs and both arms,
running with the recorder installed and with it absent must produce
identical `evaluation_results.json` content apart from the single added
`post_shake` key: every official component (`fill_score`,
`num_placed_items`), every `step_metrics` entry, and the whole
`shake_response` dict must compare equal. Any difference fails G1 and
the instrument is discarded, because a measurement that perturbs the
thing it measures is not a measurement.

**G2 -- pre-shake self-consistency.** On every episode whose final step
is a safe placement, the recorder's pre-shake capture (taken at the
instant `shake_test` begins) must reproduce that episode's last safe
step's recorded settled metrics EXACTLY on the attribute counts
(`soft_*`, `priority_*` violation counts and item totals). Nothing
steps the simulation between the last placement's settle and
`evaluate()`, so any disagreement means the capture is not reading the
state it claims to read. Threshold: exact equality on >= 95% of
qualifying episodes (allowing for episodes whose terminal step removed
an unsafely placed item).

**G3 -- no reimplementation.** A test must assert that the post-shake
attribute counts come from `calculate_attribute_placement` as imported
from the simulator package, not from a copy. Structural, checked by
`tests/`.

G1 and G2 are the whole fidelity question for v3. There is no Spearman
gate because there is no approximation to correlate: the recorded
numbers are the official shake's own.

## Data

A fresh stream. The v2 stream is adjudicated and closed. v3 collects
its own episodes: >= 6 paired runs for G1 (recorder on/off on identical
config and arm), and >= 40 episodes across >= 5 configs and both arms
for G2 and for the payload.

## If the gates pass

The instrument becomes the post-shake readout and rung 3's label
generator is unblocked: labels become
`(settle_safe, post_shake_stable, post_shake_coverage)` with the third
component measured, not proxied. The first published payload will be
the question v2 could not answer -- whether `quiet_guard`'s soft
coverage differs from `base` AFTER the shake, which is the axis the
official feedback says we are blind on.

## If they fail

Reported as failed, rung 3 stays blocked, and the failure is localized
in the same way v1 and v2 were. No constant in this instrument may be
tuned on a stream it has already scored.
