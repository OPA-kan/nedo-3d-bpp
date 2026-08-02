# Instrument validity: sigma_branch is the same size as the effects

Two branch states (steps 4 and 6), 3 siblings each, **each forced branch
re-run 3 times**. This measures the error term that actually applies to a
branch difference: the spread of the terminal result when the same forced
action is replayed from the same parent state.

The permutation sd used earlier as a threshold was a different variance
axis - variation across arrival orders of whole episodes - and using it to
filter branch differences was invalid, not merely imprecise.

## The measurement

| step | sibling | Q | placed per run | fill per run | identical |
| ---: | ---: | ---: | --- | --- | --- |
| 4 | 0 (control) | +0.761 | [21, 17, 17] | [28.18, 21.9, 21.9] | **no** |
| 4 | 1 | +0.611 | [12, 12, 12] | [13.33, 13.33, 13.33] | yes |
| 4 | 2 | +0.522 | [25, 26, 25] | [26.02, 24.5, 26.02] | **no** |
| 6 | 0 (control) | +0.611 | [21, 21, 17] | [13.04, 13.04, 21.9] | **no** |
| 6 | 1 | +0.528 | [15, 15, 15] | [18.47, 14.27, 18.47] | **no** |
| 6 | 2 | +0.401 | [19, 19, 19] | [17.73, 17.73, 17.73] | yes |

Re-running the same branch moves placed by up to **4** and fill by up to
**8.9**. That is the same order as the differences being interpreted, so a
single-run branch label carries little information on its own.

`harness_perturbs_reference` is **false**: the capturing and capture-free
references agree within this run, so the deep-copy capture is not the
source. The nondeterminism is deeper than this harness.

## One of the two case studies is dead

| | earlier single run | here, mean of 3 |
| --- | --- | --- |
| step 4, control -> lowest-Q | 14 -> 24 (regret 10) | 18.3 -> 25.3 (**regret 7, direction holds**) |
| step 6, control -> lowest-Q | 14 -> 19 (regret 5) | 19.7 -> 19.0 (**regret 0, reversed**) |

At step 6 the state-level outcome is now `q_argmax_rank_by_outcome = 1` -
the highest-Q branch finishes best - and terminal regret is 0. So the two
large-effect case studies are one. Step 4 survives directionally, but its
own control moved from 14 to 17-21 between runs.

## An instrument defect, recorded as such

`forced_action_accepted` is false on every branch. Episodes run 17 to 26
steps, so the actions were plainly not rejected; the `info` key being read
is wrong. This is a broken field, not a finding.

## What this makes the next question

Averaging repeats shrinks sigma_branch by 1/sqrt(n) at 3-5x the cost, which
only packs the noise down. Finding the *cause* is worth more. Three
suspects, in order of likelihood:

1. the deadline-limited search reacting to wall-clock load, so the same
   state reaches different candidates on different runs;
2. PyBullet internal state - `env.reset(seed=42)` may not seed everything;
3. allocation or GC timing.

The diagnosis is cheap: replay one branch three times, persist the chosen
action per step, and find the first step where the sequences diverge. If
that step's search hit its deadline, suspect 1 is separated from 2 and 3.
If it is 1, a deterministic mode with a large policy timeout would drive
sigma_branch toward zero - a different condition from shipping, but
'does Q order actions correctly' is not a question about the shipping time
budget, so measuring it separately is legitimate.
