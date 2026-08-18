# Generation or retention: ambiguous, and the ambiguity bounds the fix

Protocol: `reports/hazard/soft-generation-protocol.md`, whose three
measurements and reading thresholds were fixed before the wave.
Numbers: `reports/hazard/soft-stack/generation.{json,md}`. Data: 14
episodes, 7 development configs x 2 replicates, shipped defaults plus
`NEDO_CANDIDATE_AUDIT` and `NEDO_POSE_SNAPSHOT`, 14/14 complete, zero
harness failures. 293 decisions, mean 311 accepted candidates on the
decisions of interest.

## Result

- decisions where the played placement covers a soft item:
  **48 of 293 (16.4%)**
- **G1** some accepted candidate covers fewer: **25/48 = 52.1%**
- **G2** some accepted candidate covers none: **19/48 = 39.6%**
- **G3** clean available for the SAME item: 10; for ANOTHER item: 13

Preregistered reading: `G2 >= 0.5` -> retention, `G2 < 0.1` ->
generation, otherwise ambiguous. 39.6% is **ambiguous**, so per the
protocol **no arm is licensed** and the numbers and the split are the
finding. The thresholds are not moved to reach a verdict.

## What the ambiguity actually says

It is not a shrug. Both readings are partly true, and the split bounds
what any retention fix could be worth.

**The generator is not empty.** On 40% of violating decisions a
completely clean placement was accepted and then dropped, and on 52% a
strictly better one was. So "the agent cannot avoid covering soft
items" is false as a general statement.

**But it is empty on the majority.** On 29 of 48 violating decisions
NOT ONE of ~311 accepted candidates avoids the soft coverage. A perfect
retention rule -- one that always kept a clean candidate when one
existed -- would still leave 60% of the soft coverage in place, because
in those states no accepted placement avoids it.

**The ceiling, stated as arithmetic rather than as a hope.** 19 of 293
decisions could have been made clean by retention alone: **6.5% of all
decisions**. That is the upper bound on a retention change before any
score cost is paid, and the real value is lower because taking those
candidates costs score that the protocol deliberately did not measure.

The severity data narrows it further. Chosen placements cover 1 soft
item on 31 decisions, 2 on 15, 4 on 2; the best accepted alternative is
still 1 on 26 decisions. So most of the reachable improvement is one
violation, not many.

## Where a retention fix would have to reach

The G3 split is close to even: 10 same-item, 13 another-item. A pose
diversity constraint inside the chosen item reaches at most 10 of 48;
reaching the other 13 requires the retained set to span items, which is
the item-coverage machinery whose widenings (`item-cap 16`,
`late cap 20`, `late narrow pool cap 16`) all failed fresh-permutation
confirmation. Roughly half the reachable value sits behind a mechanism
with three recorded failures.

## Reading this against the score

`soft_item_score` tracks `num_placed_items` at r = 0.988 across five
submissions (`reports/official/placed-regression.md`). That is an
across-agent relation and says nothing about within-state action
effects, which is why it did not license abandoning this line -- but it
does mean a change that fixes 6.5% of decisions while costing any
placed is very unlikely to show up as a soft gain. Any arm here has to
carry placed as its primary gate, not soft.

## Verdict

No arm is licensed. The soft axis is now understood end to end:

1. the predicate the agent optimized was inert (0.19 violations per
   episode, zero on 34 of 42 boards);
2. fixing the predicate gave selection nothing to act on (R2 = 0/273,
   robust to every variant available);
3. the clean placement exists in 40% of violating states and is
   unreachable in the other 60%, capping a perfect retention fix at
   6.5% of decisions, half of it behind machinery that has failed three
   confirmations.

That is a bounded, measured answer to "when does soft get fixed": not
by any of the three interventions this line could reach, and the reason
is quantified rather than guessed. Anything further has to come from
placing more items, which is what every component of the official score
is actually made of.
