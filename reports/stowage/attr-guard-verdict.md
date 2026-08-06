# The attribute guard: refuted on placed, and it prices a trade nothing local can settle

`RELEASE_ATTRIBUTE_GUARD` refuses release poses whose settled proxy rests on
a protected top. It was the first candidate this session with a mechanism
behind it rather than a hypothesis: at the board `c000-k1` dies on, all 950
legal release candidates rest on soft or priority cargo, none clears
`MIN_SUPPORT_RATIO`, and the one the agent takes topples.

Four scenarios, four arms, three repeats, serial. `base_null` carries the
noise floor.

## It loses placements, in every scenario

```
placed (mean)          base   base_null   priority     all
m-dual-full-stream     38.0   31.3        35.0        27.0
m-dual-shelf-mixed     40.3   40.0        28.7        37.0
m-single-empty-noshelf 24.0   22.3        17.0        16.0
m-single-empty-shelf   20.0   20.0        17.3        14.7
```

Against each run's own floor, `placed` clears downward in three of four
scenarios for both arms:

```
scenario                control   floor   attr_guard_priority   attr_guard_all
m-dual-shelf-mixed       40.167   1.000   -11.500  CLEARS       -3.167  CLEARS
m-single-empty-noshelf   23.167   5.000    -6.167  CLEARS       -7.167  CLEARS
m-single-empty-shelf     20.000   0.000    -2.667  CLEARS       -5.333  CLEARS
m-dual-full-stream       34.667  10.000    +0.333  within       -7.667  within
```

`dual-full-stream` is "within" only because its floor is 10 placements wide.
It is not evidence for the guard.

> **Deltas revised 2026-08-06 (audit).** As first published these were
> measured against `base_null` alone with `|base - base_null|` as the floor.
> The shipped rule pools `base` and `base_null` into one control, so the
> table is regenerated. No mark changes; the largest movement is
> `attr_guard_priority` on `dual-full-stream`, +3.667 to +0.333, which was
> "within" before and after. Regenerate with
> `python scripts/summarize_ablation.py --root reports/stowage/raw-attr-guard`.

This is the failure mode that was written down before the run: the guard
removes the last legal poses and ends episodes sooner. At the fatal board
every legal pose was on protected cargo, so a guard there leaves nothing.

**Not adopted.** `placed` is the only local measure whose official direction
is validated -- the gate model held across three submissions at 14x, 6.7x
and 7.6x amplification, once with the sign flipped -- and the guard moves it
the wrong way.

## But it does exactly what it was built to do on the other axis

```
priority_covered_by_other    base   base_null   priority    all
m-dual-full-stream            1.00   0.33        0.00       0.00
m-dual-shelf-mixed            0.67   0.67        0.00       0.00
m-single-empty-noshelf        1.00   1.00        0.00       0.00
m-single-empty-shelf          1.00   1.00        0.00       0.33
```

Priority items covered by a different-attribute item goes to zero in every
scenario, for both arms. That is the local proxy for `placement_score` --
the worst official component, 16.95 against a 100 scale in the best
submission.

So the guard is a clean trade: **fewer placements, no priority violations.**
And the local suite cannot price it, because `placed` and
`priority_covered_by_other` are the two sides and only one of them has a
validated official direction. The gate amplification argues the trade is bad
-- a 25% loss of placed on a 20-placement baseline would swamp any
placement_score gain -- but that is an argument, not a measurement.

## What this makes overdue

`docs/BLOCKED_WORK.md` section 0 has an unexecuted procedure for exactly
this: four official submissions with full six-component breakdowns, all four
configurations reconstructible from git plus `build_submission.py --set`.
Running them locally gives four points to check whether each local proxy
points the same way as its official component.

Every refutation this session was decided on `placed` alone. This is the
first arm where a proxy for a different component moved cleanly, in the
opposite direction, and the trade could not be settled. It will not be the
last.

## A defect in the summariser, fixed here

`summarize_zone_order.py` — since renamed `scripts/summarize_ablation.py`,
because it was never specific to zone order — hardcoded the arm names it
compared against the floor, so the first run of this experiment printed the
arm means and no verdict lines at all. It now compares every arm present
that is not one of the two controls.

The 2026-08-06 audit found the same defect one layer down: the arm
**allow-list** was still hardcoded, so an arm the summariser had not been
told about vanished from the table entirely rather than erroring. Arms are
now read off the data and only `base`/`base_null` are named in the source.
