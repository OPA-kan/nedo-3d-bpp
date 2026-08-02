# Post-fallback fatal state: not a dead end

> **Correction (same day).** This file originally called the state a
> *coverage* gap on the strength of `units_completed` 4 of 12. That counter
> is units EXHAUSTED, not units visited; `units_started` was 24, meaning every
> unit was visited by both search calls. The state is a depth-within-unit
> failure, not a coverage failure, and the conclusion drawn below against
> `LIVE_SEARCH_INTERLEAVE` is wrong -- it is the indicated tool. See
> `reports/task-c/anchor-fallback/depth-sweep.md` and evidence
> `task-c-endgame-is-anchor-order-not-unit-coverage`. Everything about the
> oracle counts themselves stands.

Date: 2026-08-02. `measure_anchor_recall.py` with `ANCHOR_FALLBACK_ENABLED=1`,
c001-k1, steps 18 and 19, exhaustive both generators, live settle validation.

The question was whether the anchor fallback had done its job and pushed the
episode into a genuinely stuck state, or whether it had merely moved the
episode to the next state the search cannot see. It is the second.

## The three classified fatal states

| state | settled (oracle) | of which support_plane | release | class |
|---|---:|---:|---:|---|
| c000-k1:21 | 0 | 0 | 0 | **I. true dead end** |
| c001-k1:18 | 6 | **0** | 54 | **IV. generator blindness** |
| c001-k1:19 | **42** | **4** | 0 | **III. reachable, not reached** |

All counts are physically safe under live settle, and both generators ran to
completion at every state.

## Step 19 is not blindness

At the state the fallback delivered the episode into, the oracle finds 42
physically safe settled placements, and **4 of them lie in the shipped
support_plane space**. The anytime search accepted none of them
(`geometric_recall` 0.0) with `units_completed` 4 of 12 and the deadline
reached.

So the primary generator can reach a safe placement here. It ran out of time
before it did. This is the depth/budget class, and it is the first fatal state
of that kind observed in Task C -- step 18 was the opposite, a space that
contains nothing at any budget.

**Candidate generation is therefore not finished.** The board value cannot be
the next step on the strength of this chain: the episode did not reach a state
whose options are genuinely exhausted, it reached one whose options the search
did not have time to enumerate.

## The release-first ordering is a one-state answer

Step 18 has 54 release candidates and 6 settled; step 19 has **0 release and
42 settled**. The fallback orders release units first, which is what made it
work at step 18 and is exactly wrong at step 19 -- it would spend the whole
remaining budget sweeping an empty release space.

The ordering was chosen from one state's measurement and generalised without
evidence. It should be driven by the state, not fixed: a cheap signal for
which kind is worth sweeping first has to come before any further tuning of
the ladder.

## Scope

The oracle replay followed the release-at-18 trajectory and therefore ended at
step 19, so the other terminal observed in the ablation -- step 20, reached
when the fallback returns a settled candidate at 18 -- is **not** classified
here. Two of the three states are from one case. Physical safety is
per-candidate live settle at the pre-action state and does not establish that
the episode would have survived further.

## Consequence for the parallel branch

The step 19 diagnosis is a search-allocation failure: 4 reachable safe
candidates, 4 of 12 units visited, deadline hit. `ANCHOR_FIRST_PASS_ATTEMPTS`
is 64 on this trunk and the branch
`claude/stride-endgame-saturation-test-gqssix` ships it at 256 with the commit
message "The fallback is search allocation, not the stacking
over-constraint". That branch is addressing exactly this class. Re-baselining
Task C against that allocation should come before any further work on the
fallback ladder, because the ladder is being tuned against a budget that is
about to change.
