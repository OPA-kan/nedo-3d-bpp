# Direct post-shake instrument: PASS, and the blind spot is closed

Protocol: `reports/hazard/post-shake-direct-protocol.md` (frozen before
the instrument existed; G1's amendment was made and dated before any G1
datum was collected, with its reason recorded there). Gate table and
payload: `reports/hazard/post-shake/direct-gates.{json,md}`.

## The instrument

Two earlier versions tried to rebuild each episode's terminal state in a
second DIRECT world and shake the copy. v1 failed on reconstruction
(`verdict.md`); v2's pose snapshots fixed that but still failed 2 of 4
gates, one of them on peak kinetic energy, which a rebuilt world cannot
reproduce in principle -- 13 of 42 episodes off by more than 2x
(`revalidation-verdict.md`).

The rebuild was never necessary. `Evaluator.shake_test` computes the
post-shake poses in the LIVE world and then discards them at
`restoreState`. v3 records what the official shake already produced:
`scripts/postshake_capture.py` wraps `shake_test` for one call and, on
the post-shake `_live_poses` call, additionally takes the evaluator's
own `settled_snapshot` while the world still holds the shaken state.
Reconstruction error is zero by construction rather than by tuning. The
attribute counts come from `calculate_attribute_placement` -- the same
function the pre-shake proxy uses -- so the contract is not
reimplemented. Nothing under `simulator/` is modified; the agent is
untouched and `behaviour_sha256` is unmoved.

## Gate results

| gate | threshold | measured | result |
|---|---|---|---|
| G1a wrapped-vs-unwrapped shake equal | all episodes | 41/41 | **pass** |
| G1a exactly two `_live_poses` calls per shake | all episodes | 41/41 | **pass** |
| G1a span | >= 6 episodes, >= 3 configs, both arms | 41 episodes, 7 configs, both | **pass** |
| G2 pre-shake capture == last safe step counts | >= 95% | 41/41 = 100.0% | **pass** |
| G3 no reimplementation of the contract | structural | `tests/test_postshake_capture.py`, 10 tests | **pass** |
| stream sufficiency | >= 40 episodes, >= 5 configs, both arms | 41, 7, both | **pass** |

### Verdict: PASS

## One episode lost, and why

The stream is 41 of a planned 42. `c001-k1-base-r0` produced no
artifacts at all: the batch ran paired arms concurrently, and
`measurement_budget.record` did a non-atomic read-modify-write, so one
runner read a half-written ledger and died with `JSONDecodeError` at
char 0 before the episode started. That is a defect in the harness I
introduced with the concurrency, not a property of the instrument or of
that config. Fixed under the same change: atomic `os.replace` plus an
exclusive lock around the whole read-modify-write, with concurrency
regression tests. The gate thresholds are met on 41 without it, and the
loss is recorded rather than backfilled, because re-running one arm of a
pair alone would break the load symmetry the design exists to preserve.

## Payload: what the shake does to attribute coverage

**The shake changes attribute coverage on 6 of 41 episodes.** That is
the finding the whole line was built to get, stated at the size the data
supports:

| episode | soft clean pre -> post | priority clean pre -> post |
|---|---|---|
| `b000-k20-base-r0` | 0.917 -> **1.000** | 1.00 -> 1.00 |
| `b000-k20-base-r1` | 1.000 -> 1.000 | 1.00 -> **0.75** |
| `b000-k20-base-r2` | 1.000 -> 1.000 | 1.00 -> **0.75** |
| `b000-k20-quiet_guard-r0` | 1.000 -> 1.000 | 1.00 -> **0.75** |
| `b000-k20-quiet_guard-r2` | 1.000 -> 1.000 | 1.00 -> **0.75** |
| `b000-k40-quiet_guard-r2` | 1.000 -> **0.750** | 0.50 -> 0.50 |

Soft moves in BOTH directions: the shake repaired a violation on one
episode and created one on another. Priority moves in one direction
only, always worse, on four episodes.

So the pre-shake proxy is not merely a noisy version of the post-shake
truth -- on these episodes it reads a different value, and on one of
them the opposite sign of change. That is the blind spot, measured
directly instead of inferred.

### What the payload does NOT support

The arm-level means invite a claim they cannot carry. Base reads soft
0.9808 pre and 0.9850 post; quiet_guard reads 0.9857 pre and 0.9738
post -- an apparent rank inversion across the shake. **It is driven
entirely by two episodes.** Excluding the six changed episodes, both
arms are exactly flat (base 0.9824 pre and post; quiet_guard 0.9833 pre
and post). Nothing here says the guard is worse after the shake, and
this document does not claim it. Separating the arms on post-shake
coverage needs its own preregistration and a stream sized for it.

## What this licenses

**Rung-3 label generation is UNBLOCKED.** The ledger rule
`post-shake-instrument-fails-on-reconstruction` blocked it until this
instrument passed a fidelity gate. It has. Labels can now be
`(settle_safe, post_shake_stable, post_shake_coverage)` with the third
component measured by the official shake's own arithmetic rather than
proxied by a pre-shake read that is demonstrably different on 15% of
episodes.

### Correcting a wrong turn that nearly closed this line

An earlier reading of `reports/official/placed-regression.md` -- soft
tracks `num_placed_items` at r = 0.988 across the five submissions --
was used in this session's narration to argue that the post-shake line's
motivation was weakened. **That inference was invalid and is retracted
here.** The regression is a correlation ACROSS AGENTS at the submission
level; the learning objective is an effect WITHIN A STATE, over the
choice between two placements on one board. An aggregate relation
between agents says nothing about a per-decision action effect, and
treating it as if it did is an ecological-inference error. If anything
the relation cuts the other way: if the official soft component charges
for unplaced soft items, then it mechanically tracks placed, and the
part an agent can actually control is coverage among the items it does
place -- which is exactly what this instrument measures. The regression
supports one narrow claim only, that the -7.7% soft headline was not
evidence of guard damage.

## What this does NOT license

- No shipped behaviour changes. `NEDO_POSTSHAKE_CAPTURE` is default-off
  and log-only; the recorder is not on any decision path.
- No wave adjudication column yet. The instrument is validated as a
  measurement of the terminal state; using it to adjudicate an arm needs
  a protocol that says in advance how it enters the verdict.
- No arm comparison, per the payload caveat above.
