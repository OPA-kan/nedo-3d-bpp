# Task C search ceiling: how far is the real wall?

Date: 2026-08-02. `scripts/measure_search_ceiling.py`, one chain per
(case, rescue policy), serial. Each chain runs the episode normally, hands it a
physically safe oracle placement whenever it would end, and stops when the
oracle itself returns nothing over both anchor generators with unlimited time.

These are upper bounds. Both policies use the oracle's physical validation of
a candidate *before* committing to it, which no agent has. They are ceilings,
not scores.

## Result

| case | items | shipped | ceiling (search only) | ceiling (search + picks) | ends at |
|---|---:|---:|---:|---:|---|
| c001-k1 | 42 | 18 | **20** | 20 | true dead end, step 20 |
| c000-k1 | 41 | 18-20 | 18 | **22** | true dead end, step 22 |

Every chain terminates on a **true dead end**: the oracle enumerated the whole
anchor space of both generators and found zero physically safe placements. Not
a budget, not a cap -- the instrument refuses to declare a dead end from a
truncated enumeration.

## The two cases fail in different halves of the agent

**c001-k1 loses to search.** One rescue, at step 18, the generator-blindness
state already classified. Its `search` and `all` chains are *identical*, which
means the case has no physics-failure deaths at all: everything it loses, it
loses by not finding a candidate. Search is worth **+2** here, and the rescued
candidate was rank 0 of 60 -- the agent's own ranker would have picked it
first if the search had produced it.

**c000-k1 loses to picks.** Its `search` chain rescues **zero** times and
stops immediately: the death is the agent's chosen action failing physically,
which that policy does not rescue. The `all` chain rescues twice, both
physics failures, and reaches 22. Picks are worth **+4** here, search worth
nothing.

So the two levers are worth 2 and 4 placements, on cases that hold 42 and 41
items.

## The ranking is badly wrong at the endgame

The rescue records where in the agent's own ranking the first physically safe
candidate sat:

| state | oracle candidates | rank of first safe |
|---|---:|---:|
| c001-k1 step 18 | 60 | **0** |
| c000-k1 step 20 | 988 | **186** |
| c000-k1 step 21 | 384 | 16 |

At c000-k1 step 20 the top **185** candidates by the shipped score -- which
already carries `-1.0 P_rot -0.5 P_slide` -- are all physically unsafe. The
risk model is not catching that region. This is a separate finding from the
ceiling and worth its own investigation; it is one state, and the ranking of
unselected candidates is not something the existing risk evidence covers.

## What this says about where the remaining headroom is

Perfect search plus perfect picks reaches 20 of 42 and 22 of 41 items, and
then the board has genuinely no safe placement left. Roughly half of each
stream is unplaceable **from the trajectory this policy builds**.

That is the argument for the board value, stated precisely: the ceiling is low
*because* the board is bad, and a low ceiling is exactly what a board-value
term is supposed to raise. Search and ranking fixes are each worth a couple of
placements against a gap of about twenty.

It also corrects my earlier reading. The anchor fallback moved c001-k1's death
from step 18 to step 19, and I took one displacement as weak evidence that
search was still the binding constraint. Followed to the end, the chain moves
once and then hits a real wall. One displacement was not the start of a
sequence.

## Scope

One chain per cell. c000-k1's trajectory is timing sensitive on this box, so
its chain is not reproducible run to run and its two policies ran on different
trajectories -- the +4 is the gap within the `all` chain, not a difference
between the two rows. The ceiling is defined along the trajectory the current
policy builds; a policy that built a better board would have a different, and
by this argument higher, ceiling. That is the claim to test, not one this
measurement establishes.
