# Gate 2b amendment: absolute score-loss bound

Committed after the Gate 2 development wave closed `inert_arm_closed`
(run 31953466842) and before any Gate 2b episode result is opened. The
original protocol (`gate2-rerank-protocol.md`) stays frozen as written;
this amendment replaces exactly one clause and records why.

## What the wave measured

63/63 episodes completed. The negative control passed on every config
(instrument clean), the trigger fired 85 times across the 21 enforce
episodes at the expected danger states — and the swap fired **zero**
times. The rule as shipped could not act.

## Why (offline rescuability audit, committed corpus)

`scripts/audit_safety_rescuability.py` over the 7764-row / 189-board
state-model corpus, replaying the exact rule against ground-truth
settle outcomes (`reports/state-model/rescuability-audit.json`):

- 54 boards trigger (highest-Q candidate below logit 2). The incumbent
  is physically unsafe at 27 of them.
- An escape-eligible alternative (logit >= max(2, incumbent+2)) exists
  at 34 of the 54 — and at 20 of the 27 unsafe-incumbent boards, where
  **19 of the 20 picks are physically safe**.
- The shipped **relative** Q-conservation bound (15% of |score|)
  rescues **0 of 27**: danger states have incumbent scores near zero
  (typically -0.02 to -2), so a relative budget vanishes exactly where
  the model has something to offer. This is a pricing failure, not a
  perception failure and not a candidate-set failure.

## The amended clause

Q-conservation becomes **absolute**: an alternative may give up at most
**1.0 units of immediate score** (`SAFETY_RERANK_MAX_SCORE_LOSS_ABS`).
From the committed sweep:

| bound | rescued (of 27) | unsafe picks | needless swaps | mean cost |
|---|---|---|---|---|
| relative 15% | 0 | 0 | 2 | 0.10 |
| 0.5 | 15 | 1 | 9 | 0.24 |
| **1.0** | **18** | **1** | **11** | **0.34** |
| 1.5 | 19 | 1 | 12 | 0.58 |
| none | 19 | 1 | 14 | 1.15 |

1.0 sits at the knee: returns above it are one board per half unit of
extra budget while the needless-swap cost keeps climbing. A death
forfeits every remaining placement, so one unit of immediate score is
cheap insurance where P(survive) is coin-flip.

Trigger (2.0), escape margin (2.0), never-refuse, the seam, the arms,
and all five episode gates are unchanged. This constant is fitted
offline on the committed corpus — the repo's licensed pattern — and the
Gate 2b episode wave plus the Gate 3 fresh-permutation confirmation
remain untouched fresh evidence. No further retuning of any constant
on any of these streams.

## Connection to the hazard-pricing entry gate

HANDOFF task 3 requires, before designing any lambda form: "show that
at fatal steps a materially lower-P accepted alternative existed."
The audit is that evidence at corpus scale: 20 of 27 fatal-choice
boards had a high-logit alternative and 19 were physically safe. The
absolute bound is the first, simplest hazard price (a flat one); if
Gate 2b passes, a state-dependent price is the successor experiment,
not a retune of this one.
