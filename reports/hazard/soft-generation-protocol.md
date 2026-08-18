# Is the soft-clean placement generated, or only unretained?

Short preregistration, written before the wave. Follows directly from
`stack-aware-soft-tiebreak-has-no-reach-in-selection`, which located the
lever outside selection and deliberately stopped there.

## The question, and why it is the only one worth asking next

Stage 1 measured that on 64 of 273 decisions the agent places something
over a soft item while EVERY retained alternative does the same. Two
readings remain and they call for different work:

- **Retention.** Soft-clean candidates are generated and accepted, and
  then dropped because retention keeps the top K by score and the top
  poses of one item are near-duplicates. The fix is retention
  diversity: a bounded, local change.
- **Generation.** No soft-clean candidate is produced at all in those
  states. Then retention diversity is empty and the work is in the
  anchor/candidate generator, which is a much larger undertaking with
  its own closed negatives.

Nothing built so far distinguishes them.

## Instrument: existing knobs only

`NEDO_CANDIDATE_AUDIT=1` already records every ACCEPTED candidate's
`item_index`, `orientation`, `center`, `size` and `kind` -- the whole
pre-retention set. `NEDO_POSE_SNAPSHOT=1` already records the packed
items' poses and attribute flags at every step. Both are registered
diagnostics (`semantic: false`).

The stack-aware violation count is therefore computable OFFLINE for
every accepted candidate, from data these two knobs already emit.
**No agent change, no new knob, no hot-path work**, which matters
because computing attribute violations inside the candidate loop would
perturb the deadline-bound trajectory it is trying to measure -- the
failure mode `docs/STRUCTURED_SELECTOR_EXPERIMENT.md` already recorded.

Known and accepted limitation: the audit's own recording cost changes
the trajectory, so this wave's episodes are not the same episodes as an
unaudited run. That is acceptable here and would not be for an arm,
because the question is a property of a board state and its accepted
candidate set -- "does a soft-clean candidate exist here" -- not of a
particular trajectory. It also means **nothing measured here may be
compared to another wave's placed or fill.**

The audit does not carry the candidate's score, so this wave answers
existence only. The cost half -- what score a soft-clean candidate
gives up -- is a separate question and is NOT smuggled in here.

## Data

7 development configs x 2 replicates, shipped defaults plus the two
diagnostic knobs.

## Measurement, fixed now

Over decisions where the CHOSEN placement has at least one stack-aware
soft violation:

- **G1** the fraction where at least one accepted candidate for the
  same step has strictly fewer stack-aware soft violations;
- **G2** the fraction where at least one accepted candidate has ZERO;
- **G3** for those, whether the soft-clean candidates are for the same
  item as the chosen one or a different item -- a same-item alternative
  is reachable by pose diversity alone, a different-item one needs the
  retained set to span items.

## Reading, fixed now

- **G2 >= 0.5** -> the placements exist and are being dropped. The
  lever is retention diversity, and its size is bounded by G1/G2. A
  retention arm becomes preregisterable, inheriting `release attribute
  hard reject` (closed on placed cost) and the item-cap widenings that
  failed fresh permutations -- so it must be a diversity constraint at
  fixed K, not a wider K.
- **G2 < 0.1** -> the generator does not produce soft-clean placements
  in these states. Retention diversity is empty; say so and stop, and
  do not open the generator on the strength of this alone.
- in between -> report both numbers and the G3 split; no arm is
  licensed by an ambiguous result.

No threshold here may move after the numbers exist.
