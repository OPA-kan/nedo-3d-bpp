# bench smoke run — what the first measurements say

Arm `ladder` (rule-alpha, shipped config), suite `smoke` (4 scenes) and the
same four streams under the Task A flow (`smoke-a`).  Physics runs on this
machine ran four processes in parallel, so wall-clock columns are inflated.

## 1. Negative control passes

`ladder-smoke` vs `ladder-smoke-repeat`: identical step for step, every
physical metric identical on all 4 scenes.  The PyBullet episode is
deterministic under `env.reset(seed=42)` and `deterministicOverlappingPairs`.
Only `policy_time_max` differs, which is why it is reported as `timing-only`.
See `ladder-smoke-control.md`.

## 2. Task C and Task A are different problems for the same rules

Same streams, same containers; the only change is whether `optimize()` is
called (Task A) or not (Task C).  All episodes end `declined`.

| scene | Task C placed | Task A placed | Task C fill_volume | Task A fill_volume |
|---|---:|---:|---:|---:|
| c1  s0001 | 18 / 41 | 24 / 41 | 25.2 | 39.7 |
| c1s s0002 | 14 / 41 | 16 / 41 | 24.5 | 32.9 |
| c2  s0003 | 30 / 82 | 32 / 82 | 26.7 | 33.8 |
| c2p s0004 | 18 / 82 | 25 / 82 | 13.0 | 24.2 |

rule-alpha's headline numbers (24/41 on sample task 000) were measured with
the manifest handed over.  Under the Task C flow the same rules place fewer
items and considerably less volume, and the two-container priority layout is
the weakest case.  Any ranker comparison has to state which flow it ran.

## 3. The shipped fill margin removes real volume

| scene (Task C) | fill_volume | evaluator, margin +0.005 | evaluator, margin −0.005 (shipped) |
|---|---:|---:|---:|
| c1  s0001 | 25.2 | 23.9 | 16.7 |
| c1s s0002 | 24.5 | 23.4 | 12.1 |
| c2  s0003 | 26.7 | 21.7 | 14.8 |
| c2p s0004 | 13.0 | 11.4 | 7.4 |

Under the shipped sign a third to a half of the placed volume is discarded
because settled boxes sit within 5 mm of a container plane.  Under the Task A
flow `fill_evaluator_tolerant` equals `fill_volume` exactly on all four
scenes, so the tolerant margin loses nothing there.  Which sign the real
evaluation uses is not known; the bench reports all three.

## 4. Analytic validate() vs the official validator (580 probes)

| | physics accepts | physics rejects |
|---|---:|---:|
| analytic accepts | 414 | 2 |
| analytic rejects | 81 | 83 |

* **False accepts: 2 of 416 (0.5 %).**  Both are tall standing poses on a
  terrace (a 0.45 m and a 0.56 m tall box resting on packed items) that the
  settle toppled through 90°.  The rigid-body centre-of-mass criterion does
  not see the release drop's dynamics for tall poses on item supports.
* **False rejects: 81 of 164.**  By analytic reason:
  `no-support` 69/70 accepted by physics (a box released above its support
  simply drops, which the official settle allows),
  `centre-of-mass-outside-support` 4/4 accepted,
  `outside-container` 5/5 accepted (the 16 mm analytic clearance is three
  times the official 5 mm),
  `overlaps-packed-item` 2/32, `transport-hits-packed-item` 1/3,
  `settled-pose-outside` 0/47, `overlaps-main_shelf` 0/3.

So the analytic model is safe to plan on (almost nothing it accepts fails),
but it forbids a large space of placements the competition would accept:
released-and-dropped poses, poses nearer the walls, and some tighter
lateral gaps.  A learned ranker trained only on analytic survivors inherits
that restriction.

Probe cost was about 0.3 s each; 4 + 4 probes per decision roughly doubles
episode time.
