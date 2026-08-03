# Step-4 diff: no proximate mechanism, case dropped

The one improvement case that survived repeats, dissected against
predictions registered before the diff was read.

- winner (lowest Q, +0.522): 26 steps, 25 placed, fill 22.349
- loser (highest Q, +0.761): 18 steps, 17 placed, fill 21.896

## Scoring the predictions

| | predicted | outcome |
| --- | --- | --- |
| A acceptance breadth | to FAIL | **not measurable** - instrument defect below |
| R alternativity | untested | **does not separate** |
| H repairability | to HOLD | **direction right, mechanism wrong** |

## H: the loser died of a topple, 13 steps after the branch

The losing branch ends at step 17 with a settle angle of **88.4 deg** and
a displacement of **1.061 m**. The winner's worst before step 22 is 17.3
deg / 0.214 m, and it runs to step 26.

So a physical death is what happened, as predicted. But the predicted
*mechanism* - irremovable debris followed by an inability to recover - did
not occur: the topple was immediately terminal, so there was no recovery
phase at all.

More importantly, **the branch is at step 4 and the death is at step 17**.
By then the two trajectories are in entirely different states. This diff
does not support 'the step-4 choice caused the step-17 topple'.

## R: the branches are indistinguishable where it would have to show

The rule set before reading was that only a difference already present
just after the branch counts, because a later difference is a consequence
rather than a cause. Immediately after the branch:

| step | winner components | loser components |
| ---: | ---: | ---: |
| 5 | 5 | 5 |
| 6 | 5 | 5 |
| 7 | 6 | 5 |

A difference of one component, and the ordering reverses later - at steps
11 and 12 the **loser** has more (7, 8 against 6, 6). `largest_support_area`
is 2.9000 in both branches at every step, because it is the container
floor and always the largest; that field measured nothing.

## A: an instrument defect, not a result

`classes_with_a_settled_option` swings between 0/10 and 10/10 on adjacent
steps where the state barely changes. The probe used `stride=16, limit=1`,
so it recorded 'this sparse probe found nothing' as 'no class can be
placed'. The column is unreadable and no conclusion is drawn from it.

## Verdict

The rule registered beforehand was that a case with no surviving
prediction gets dropped rather than explained. Nothing survives, so the
case is dropped as a source of a board functional. What it yielded is a
restatement of the known death channel, not a new state quantity.

One negative finding is worth keeping: **whatever the step-4 choice did, it
is not visible within three steps in support components, largest support
area, or class acceptance.** The difference is either in a quantity not
measured here, or it is not a state property at all but accumulated
trajectory divergence. Given that sigma_branch was measured large - the
same branch replayed moves placed by up to 4 - the second explanation is
not remote, and an 8-placement gap 13 steps downstream may be substantially
divergence rather than consequence.
