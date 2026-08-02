# Branch labels: the immediate score is anti-correlated with the outcome

One episode (`b000-k20`), 6 branch points, 3 siblings each, every branch run
to completion with the shipped policy free after the forced step.

## Headline, and it is suggestive rather than established

| relation | agree | disagree | tie | concordance | two-sided p |
| --- | ---: | ---: | ---: | ---: | ---: |
| higher Q -> better final placed | 4 | 11 | 1 | **0.267** | 0.1185 |
| higher Q -> better final fill | 4 | 11 | 1 | **0.267** | 0.1185 |
| higher placed volume -> better final placed | 5 | 8 | 3 | 0.385 | 0.5811 |

Chance is 0.500. The immediate score ranks siblings **backwards** relative
to how the episode actually finishes, and in 5 of 6 branch points the
lowest-Q sibling gave the best final placed and fill. At step 4 the
lowest-Q sibling reached 24 placed against the control's 14.

**The obvious confound does not explain it.** `Ranker.score` contains
`12.0 * volume`, so low Q correlates with small items, and placing small
items first trivially raises a later count. But placed volume predicts the
outcome barely better than chance (0.385, p = 0.58), and the direction is
wrong for the story: at step 8 the winning sibling (18 placed, fill 22.13)
placed the **largest** available item at the **lowest** Q.

## What this is not

n = 15 decided pairs on one episode of one configuration. p = 0.1185 is not
significance. Against the measured noise floor (placed sd 2.3), differences
like 14 vs 15 are noise; 14 vs 24 is not. Read this as one well-controlled
observation that the shipped utility may be actively mis-ordering, not as a
measurement that it does.

## Validity problems, all of which bound the result

1. **One branch had a broken prefix** (step 14, sibling 1) and is excluded
   from every number above.
2. **One control did not reproduce the reference** (step 8). That state's
   labels are suspect, and it is one of the steps carrying the effect.
3. **The reference is not stable across runs of this harness.** The smoke
   run gave 16 steps / fill 17.795 for the same config; this run gave 15 /
   16.477. The plausible cause is this driver's own capture: deep-copying
   the observation at 6 steps instead of 1 perturbs a deadline-limited
   search. Note the earlier bit-identical 3-repeat result was on a
   different harness (subprocess `run_test.py`), so it does not vouch for
   this one.
4. **Step 12 had no control at all** - the action the live policy chose was
   outside the offline-reconstructed sibling set. The sibling set does not
   always contain what the policy does.

## The fix for 3, before this is re-run

Branch runs capture nothing, so they are unperturbed; only the reference
captures. So the controls are being compared against a *perturbed*
reference. Run a third capture-free reference and compare controls to that
instead. Cheap, and it removes the one validity failure that is this
harness's own doing rather than the environment's.

## Why this matters more than another state descriptor

Today's negatives all concerned candidate *quantity* - option counts, risk
weighting, scan coverage. This is the first measurement aimed at the
*ordering*, and it points at the utility itself. If it holds up, no amount
of better candidate generation helps, because the thing choosing among the
candidates prefers the worse one.
