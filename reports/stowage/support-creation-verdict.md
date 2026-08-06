# Support area can only shrink, and that is why the boards become towers

The section reading proposed judging a placement by the connected support
surface it leaves rather than the volume it fills, with the specific claim
that a void is not automatically bad -- bridging two towers buys a large
face on top at the cost of a void beneath, while raising a tower buys
nothing. Measured, the negative half of that is real and the positive half
is not available to this agent.

## Bridging requires a 6 mm coincidence

Two tops merge into one connected face only when they sit within
`CONTACT_TOLERANCE` = 6 mm of each other. Across five packed containers:

```
                         plain items   top pairs within 6 mm   level groups
c000-k1          c0            9            0 / 36                  0
dual-full-stream c0           18            3 / 153                 3
dual-shelf-mixed c0           12            4 / 66                  4
001              c0           16            6 / 120                 2
```

Zero to five percent, and every group is a pair or a triple. It happens, but
as a coincidence of cargo heights, not as something a policy chooses. Item
heights run 0.20 to 0.68 m in arbitrary combinations, so a new top lands
level with an existing one about that often.

At step 5 of `c000-k1`, of the 400 legal candidates the deadline-free oracle
enumerates, **none** increases the largest connected face above the floor.
The distribution is `min -0.101, median +0.000, max +0.000`.

## So the elevated support surface is monotonically non-increasing

Every placement either leaves the elevated faces alone or roofs part of one.
Nothing grows them. The board's largest connected face above the floor at
step 5 is 0.382 m2 -- smaller than the 0.2925 m2 footprint of the item being
placed, and it only goes down from there.

That is the mechanism behind the towers the drawings show, and it closes the
loop with the reachability census: at termination three of four containers
have zero columns where anything would stand. Support exhaustion is not bad
luck, it is the fixed point of a process where support can only be spent.

## What survives as a usable signal

The positive half does not exist, so "reward bridging" is not implementable.
The negative half does: `dA_largest` ranges 0 to -0.101 per placement at that
step, so **penalising the roofing of elevated faces is expressible**, and it
is a far weaker claim than the one the reading proposed.

Not built into a knob here. Two knobs measured today on this branch both
lost placements against their noise floor, and a roofing penalty has the
same shape as both of them -- it discourages the placements that are
currently available without creating better ones. It should be run only as a
deliberate choice, not as momentum.

## Three implementations of this metric were wrong before this one

Recorded because each failed a check that the next one added:

1. **Add the candidate's top, subtract nothing.** Every plain placement
   scored positive, 100% of candidates "added support". A tower and a bridge
   were indistinguishable, which is the one thing the metric exists for.
2. **Drop any surface the candidate overlaps.** The floor spans the
   container and sits below every candidate, so each one deleted 2.9 m2 at a
   stroke -- dA came out at -2.6 to -4.0 m2 on a board holding 4.4 m2 total.
3. **Largest component globally.** The floor is always the largest, so
   `dA_largest` was 0.000 everywhere by construction. The reading asked for
   per height band and it was collapsed to a global maximum.

The rasterised version conserves total area (`dA_total` = +/-0.000), which
is the sanity check the first two would have failed and neither had.
