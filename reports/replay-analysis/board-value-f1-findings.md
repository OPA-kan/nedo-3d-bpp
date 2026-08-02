# F1 findings: the board value discriminates, and does not yet predict

Date: 2026-08-02. Data: `board-value-f1.{md,json}`, 43 replay snapshots
(final_holdout skipped), stride 64, phases 1, seven-type prior.

F1 asked one question: do `R_c(s)` and `H(s)` saturate the way `A(s)` does?
It is a cheap-death gate, not an adoption test.

## Gate result: passed

**`A(s)` is saturated.** 42 of 43 snapshots have all seven baggage types
individually placeable; the single exception is `b001-k20:15` at 4. A cannot
discriminate, which is the same failure mode that made the 1-ply pool
feasibility signal useless (`three-modes-degenerate-run30340049061`,
`lookahead-modes-degenerate-rich-search`). The theory's decision not to build
on A is therefore confirmed rather than assumed.

**`R_c(s)` and `H(s)` are not saturated.** The Hall deficiency over
geometry-derived support resources spreads across its whole range and is not
concentrated:

| deficiency | 0 | 2 | 3 | 4 | 5 | 6 | 7 |
|---|---:|---:|---:|---:|---:|---:|---:|
| snapshots | 2 | 2 | 6 | 5 | 10 | 7 | 11 |

Distinct values per quantity: `hall_deficiency_settled` 7,
`r_settled_mean` 16, `phi_log_settled` 24, `hall_ratio_any` 14. So the
class-vector and the class-competition structure carry variation exactly where
the collapsed scalar does not. This is the part Stage A never measured: it
reduced every class to one `combined_simultaneous_count`.

## What F1 did not establish, and the raw direction

No predictive relationship. Every Spearman against steps-to-terminal is weak
and the signs do not line up with the theory:

| quantity | rho vs steps-to-terminal |
|---|---:|
| `r_settled_zero_classes` | 0.302 |
| `r_settled_mean` | -0.227 |
| `phi_log_settled` | -0.209 |
| `hall_deficiency_settled` | 0.192 |

Grouped, the raw direction is mildly against the theory: snapshots that are
about to end look *healthier*, not worse.

| group | n | Hall deficiency | Phi | R settled mean |
|---|---:|---:|---:|---:|
| terminal (to-go 0) | 21 | 4.71 | 4.82 | 1.26 |
| non-terminal | 22 | 5.09 | 3.17 | 0.84 |

Individual counterexamples are stark in both directions. `b001-k20:10` is the
healthiest board in the set (deficiency 0, ratio 1.286) and had 5 steps left;
`b000-k20:10` has deficiency 7 and also had 5 steps left.

**This data cannot settle the question either way**, for three reasons that
were all knowable in advance and one that was not:

1. These are Task B episodes (pools 10-40). Task C is pool 1.
2. The replay dataset deliberately over-samples near-terminal states: 21 of 43
   rows have to-go 0. A correlation against to-go on a sample selected by
   to-go is a selection artifact.
3. Steps-to-terminal is the label that already failed in Stage A, and the
   theory itself explains why: episodes end by physics failure, not by
   capacity exhaustion (`stage-a-calibrated-negative`). A board can be in
   perfect option-structure health at the instant a topple ends the episode.
4. Instrument caveat found here: 21 of 43 rows hit the 400-anchor subsample
   cap, so `R` is a truncated bound on half the sample. Truncation is recorded
   per row and lowers R, so it cannot manufacture the non-saturation result,
   but it does compress the upper range.

## Consequence for F2

The Task C baseline measured on the same day changes what the label should
be. All four Task C episodes end on the fixed-coordinate fallback with
`internal_outcome = no_safe_action` and zero accepted candidates
(`task-c-baseline-fallback-is-the-only-death`). That is a **per-step, directly
observable event**, and it is exactly the event the board value claims to
predict: a state whose options have collapsed.

So F2 should drop steps-to-terminal and ask, on Task C episodes:

    does the next arriving item get an accepted candidate at this state?

with the board value computed on the state *before* the arrival. That label is
not confounded by the near-terminal over-sampling, does not require the
episode to end for a reason the theory owns, and is measured on the task the
theory is about. The prediction is falsifiable in the strong direction: if
`Phi` and `H` do not separate the `no_safe_action` steps from the rest, the
board value does not describe Task C's failure and should not enter the
ranking.
