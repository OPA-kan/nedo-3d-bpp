# Retraction: the agent was not taking dominated poses

`reports/hazard/dominated-choices.md` reported that at 10 of 17 steps of
`c000-k1` a legal alternative existed that was strictly safer AND strictly
higher scoring than the pose taken, and that 112 alternatives outranked the
fatal one. **That is wrong.** Measured against the agent's own candidate
model, at the fatal step:

```
chosen pose        adjusted -1.5287   (Q -1.1806, P_rot 0.2773)
best in oracle     adjusted -1.5301   found_by_anytime = True
oracle poses beating the chosen pose:  0 of 950
reachability regret (best oracle - best found):  +0.0000
ranking regret      (best found  - chosen)    :  -0.0014
```

The agent took the argmax. Out of 950 legal release candidates enumerated
without a deadline by `scripts/measure_anchor_recall.py`, none scored better
than the pose it committed to, and the search had the best of them in hand.

## Why the first measurement was wrong

The alternatives in the retracted report came from a 5 cm grid whose drop
height was read off `AfterstateBoard`'s heightmap. That heightmap is a
5 cm lattice, so a pose's `z` can be off by most of a cell -- and
`Ranker.score` carries `- 0.18 * z * mass` with masses up to 12 kg, which
turns a 1 cm error in `z` into 0.1 of score. The gaps being called
"domination" were 0.1 wide.

The retracted report even carried the caveat that the grid might propose
poses the generator cannot, and called that an open question. It was not
open: `measure_anchor_recall.py` already enumerates from the agent's own
contract and marks each candidate `found_by_anytime`. Reaching for the
existing oracle instead of building a grid would have avoided the whole
claim.

A second error compounded it. The first re-check today passed
`item = {"mass": 1.0}` into `Ranker.score` instead of the real item, which
put the chosen pose at `Q +0.5083` against a true `-1.1806` -- a 1.69 swing
from mass alone, and briefly made the chosen pose look unbeatable for the
wrong reason. Both numbers are in this file because the corrected one is
only meaningful next to what it corrects.

## What the step actually was

Every legal pose was bad. The best available had `P_rot 0.2775` against the
chosen `0.2773` -- indistinguishable. There was no safer option to take, no
better-scoring option to find, and the settled oracle was empty (0 candidates
from both the Cartesian and support-plane generators). The episode ended
because the board offered nothing but marginal releases, which is the
`safe_release_only` failure class `docs/ANCHOR_RECALL_ORACLE.md` already
names.

## What survives

- The geometric findings stand: 62.9% of free-and-fits poses at a terminal
  board are corridor-blocked, neighbour gaps run 47-178 mm against a forced
  26 mm, and the under-shelf volume takes 6 items under deliberate filling.
  None of those depend on scoring.
- Release recall at this step is **312 of 950, 32.8%**. The search reaches a
  third of its own enumerable candidate set inside the deadline. That is a
  real number and it is not what the retracted report claimed -- low recall
  with zero regret means the poses it misses are ones it did not need.

## Method note, carried forward

Heightmap drop heights must not be used to SCORE a pose. They are fine for
asking whether space exists; they are not fine for anything multiplied by
`z`, which at these masses is most of the score's dynamic range.
