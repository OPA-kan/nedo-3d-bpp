# Anchor-space fallback: first Task C ablation

Date: 2026-08-02. Local 4 vCPU, `run_queue --parallel 3`, arm `base` versus
arm `anchor_fallback` (`ANCHOR_FALLBACK_ENABLED=1`), 5 repeats per cell.

## Result

| case | arm | placed (5 repeats) | mean | fill |
|---|---|---|---:|---:|
| c001-k1 | base | 18, 18, 18, 18, 18 | 18.00 | 23.5599 |
| c001-k1 | **anchor_fallback** | **19, 19, 20, 20, 20** | **19.60** | 25.3662 |
| c000-k1 | base | 18, 19, 21, 21, 21 | 20.00 | 16.228 |
| c000-k1 | anchor_fallback | 21, 21, 21, 21, 21 | 21.00 | 17.3104 |

## c001-k1: the predicted effect, at the predicted step

The base arm is perfectly deterministic here: placed 18 and fill 23.5599 in
all five repeats. The fallback arm fires in all five, always at **step 18** --
the exact state the exhaustive oracle analysed -- and never anywhere else:

| repeat | fired at | kind returned | placed |
|---|---:|---|---:|
| r0, r1 | 18 | `release_candidate` | 19 |
| r2, r3, r4 | 18 | `candidate` (settled) | 20 |

First accepted candidate at 0.385 s into the fallback, matching the 0.38 s
measured on the saved snapshot before any physics ran. There is no overlap
between the arms' placed distributions.

The split between repeats is the release-first ordering trade showing up in
data. Under tighter timing the ladder returns a release candidate (19); with
slightly more room it reaches the settled units and returns a settled one
(20). Both beat the fixed-coordinate death, and the settled outcome is the
better one, so the ordering costs quality only when the budget is tightest.

Unexplained and flagged rather than smoothed over: `fill_score` is 25.3662 in
all five fallback repeats although placed is 19 in two of them and 20 in
three. A twentieth placement that adds no fill credit is consistent with the
official wall-flush exclusion (`wall-flush-fill-exclusion`), but that is a
hypothesis, not a check that was run.

## c000-k1: no effect, and the difference is variance

The fallback **never fired and never even attempted** in any of the five
repeats. Its exhaustion guard requires the primary search to have completed
every unit, and at c000-k1's fatal step the primary search is deadline-limited
(`units_completed` 9 of 12), so the guard correctly refuses to switch anchor
spaces while the current one is still unexplored. The oracle independently
showed that state is truly infeasible, so firing would have found nothing.

The two arms are therefore the same code path on this case, and the 21.00
versus 20.00 mean is run-to-run variance, not an effect. It should not be
quoted as one.

## Correction: c000-k1 determinism was a property of the load

The Task C baseline reported c000-k1 as bit-identical across repeats. That was
measured at `--parallel 2`. At `--parallel 3` the same arm produces placed 18,
19, 21, 21, 21 with fill from 11.7277 to 17.4820. The determinism belonged to
the load, not to the case. c001-k1, by contrast, stayed exactly deterministic
under both loads.

Practical consequence: single-repeat differences on c000-k1 carry no
information, and any Task C comparison has to fix its parallelism across arms.

## The Task B regression guard is void at this parallelism

The development suite was run once per arm at `--parallel 3` and the base arm
does not reproduce the committed guard: b000-k40 placed 11 against a baseline
of 21, b001-k20 12 against 18, b001-k30 12 against 17. Under that much
contention the arm comparison measures the scheduler, so the +9 placed the
raw numbers show for the fallback is not reported as a result. The guard is
being re-run serially.

## Status

Not adopted. `ANCHOR_FALLBACK_ENABLED` stays off. What is established is a
mechanism confirmed end to end on one case -- oracle predicts the state, the
static probe predicts the discovery time, the physical run reproduces both and
gains placements -- and what is missing is the regression evidence on Task B
and any second Task C case of the generator-blindness class.
