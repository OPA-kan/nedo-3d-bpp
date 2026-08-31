# The bootstrap improves the board ranking and not the verdict

Date: 2026-08-31. Measured, **not adopted**.
Follows `reports/value/board-value-20260831.md`.

## What was built and why it looked right

The teacher books its rollout's tail as zero, and that zero is 2-4x
wrong (`reports/candidate-support/rollout-ceiling-20260830.md`). A
fitted V_theta ranks boards better than the ten-step rollout it would
replace -- Spearman +0.586 / +0.594 / +0.658 against +0.365 / +0.477 /
+0.399 -- so composing

    V(s_t) ~= measured prefix delta + V_theta(s_{t+n})

should give the dominance rule a better-informed terminal.

## It does not

Same board, same candidates, scored three ways and compared against
rule-alpha's own continuation as the higher-ceiling judge. Six Cup 009
cells, steps 4 and 8, three candidates each, 27 pairs of which the
reference decides 21:

| | agrees with the reference |
|---|---|
| incumbent (tail = 0) | 13 / 21 = **61.9%** |
| bootstrapped (tail = V_theta) | 14 / 21 = **66.7%** |

**One pair.** Of the five verdicts the bootstrap changed, three moved
toward the reference and two away -- a coin flip at this sample size.

The reason is a scale mismatch, and it is stark:

| | fill points |
|---|---|
| mean bootstrap term added to each side | **17.371** |
| mean measured gap between the candidates | **0.729** |

**The estimate is 24x the signal it is added to.** Once V_theta's own
difference between two boards exceeds their measured difference, V_theta
decides the verdict -- and at Spearman ~0.6 that decision is not much
better than the one it replaced.

## The distinction that was missed

V_theta is good at ranking **different boards**. A dominance verdict
ranks **two boards one move apart**, whose measured difference is 0.729
fill. Those are different resolutions, and a model validated on the
first does not thereby earn the second. The board-value report's numbers
stand; this report is about what they do not license.

## Kept, with the switch off

`--bootstrap-value-dir` stays, defaulting off, with this result recorded
so the composition is not rebuilt from scratch by someone reading only
the encouraging half. `terminal_bootstrapped` marks any row that used
one.

Where V_theta plausibly does belong: allocating search effort -- which
candidates to roll out deeply -- where being right 60% of the time
about which board is more promising still pays, and no verdict rests on
it. Untested.

## Three defects the smoke run caught that the unit tests did not

Recorded because all three are silent failures.

**The bootstrap never fired on the case it was built for.** The
condition read `not genuine`, but `no_retained_candidate` -- the
generator running dry, 96.3% of Cup 009's rollouts, exactly the case the
zero is wrong for -- is *in* `GENUINE_TERMINATIONS`. Two different
questions were being answered by one set: "may the dominance rule read
this row" and "is the remaining value genuinely zero". The second is now
`ZERO_REMAINING_TERMINATIONS = {"stream_exhausted"}`, which is the only
ending where nothing is left to book.

**`compose_leaf_value` nulls the heads it is not given.** The first
implementation supplied only `fill_return` and this file's own docstring
claimed the others would compose as "no further violations". They do
not: a missing suffix sets its component to `None`, a None head fails
`_oriented`, the candidate leaves `terminal_eligible_candidates`, and
**every verdict vanishes** -- strict pairs went 3 to 0 on the smoke cell.
That reads as "the bootstrap made everything incomparable", which would
have been the wrong conclusion drawn from a real defect. All heads are
now emitted explicitly, zeros included.

**A None-guard was missed on one added line**, crashing the search where
every neighbouring field already handled it.

## Reproduction

    python scripts/probe_bootstrap_agreement.py \
      --config-dir <cells> --cases <names> \
      --value-dir reports/value/board-value-v1 \
      --steps 4 8 --candidates 3 --output agreement.json

Compared on fill alone: the bootstrap touches only `fill_gain`, and the
four-head partial order answers "incomparable" often enough to dilute
the comparison being made.
