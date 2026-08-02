# Interleave on Task C: rejected

Date: 2026-08-02. Same box, `--parallel 3`, 3 repeats per cell, arms `base`,
`live_interleave4`, `live_interleave8` (base plus one variable).

The correction to the coverage misreading promoted `LIVE_SEARCH_INTERLEAVE` to
the indicated tool: c001-k1 step 19 visits all twelve units but scans none far
enough into its anchor order, and interleave spreads a deadline-limited visit
across the grid instead of taking its prefix. It loses.

| case | arm | placed | fill | terminal source |
|---|---|---|---:|---|
| c000-k1 | base | 20, 21, 21 | 17.033 | mixed |
| c000-k1 | live_interleave4 | **17, 17, 17** | **10.905** | placement_core |
| c000-k1 | live_interleave8 | **17, 17, 17** | **10.905** | placement_core |
| c001-k1 | base | 18, 18, 18 | 23.560 | fixed fallback 3/3 |
| c001-k1 | live_interleave4 | 18, 18, 18 | 23.560 | fixed fallback 3/3 |
| c001-k1 | live_interleave8 | 18, 18, 18 | 22.256 | fixed fallback 3/3 |

c000-k1 regresses by 3.67 placed and 6.13 fill, identically at both interleave
values and deterministically across repeats. c001-k1 does not move at all,
which is what the blindness class predicts: reordering a space that contains
no solution cannot produce one.

## Why it loses, and what that rules out

The scan order is not arbitrary. Support-plane components are ordered
floor-first, then by area, depth and low height
(`order_support_plane_components`), and the cartesian grid is walked in a
deterministic priority order. The prefix is the *quality prior*: the early
anchors are the ones the design believes in.

Interleaving destroys that prior uniformly. A deadline-limited visit then sees
a spread of mediocre anchors instead of the best ones, at every step of every
episode -- and only one step per episode is the fatal one. The trade buys the
tail and pays with the body.

So the prefix bias that starves step 19 is the same mechanism that makes every
other step work. A **global** reordering cannot separate them, and both
directions of the global knob are now measured: deeper per unit
(`depth-sweep.md`) is inert or chaotic, reordered within unit is a clear loss.

## What is left for step 19

Within the current budget and scan design, the four safe support_plane
candidates at c001-k1 step 19 are not reachable by reordering and not by
depth. The remaining options, none of them tested:

1. Make an attempt cheaper, so the same wall clock buys more of the same
   ordered scan.
2. Condition the ordering on state, so the spread only applies once the normal
   order has already failed. Note that the anchor fallback has exactly this
   shape but cannot be reused directly: it fires only when the primary search
   *exhausts*, and step 19 ends by *deadline* with no budget left to spend.
3. Stop attacking step 19 from candidate generation and attack it from
   prevention -- the board value, which is about not arriving in that state.

Option 2's obstacle is worth stating plainly: at step 19 the budget is fully
consumed and nothing was found, so any state-conditional rescue needs time it
does not have. That makes option 1 a precondition for option 2 rather than an
alternative to it.

## Status

`LIVE_SEARCH_INTERLEAVE` stays at its default of 1. This is the second
Task C intervention in a row that was well-motivated statically and lost on
physics, after the shallower-first-pass hypothesis. Both were argued from a
correct reading of the state and both were wrong about what the fix would
cost elsewhere.
