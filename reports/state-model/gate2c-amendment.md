# Gate 2c amendment: the swap pool must not be score-selected

Committed after the Gate 2b wave closed `inert_arm_closed`
(run 31954296967) and before any Gate 2c episode result is opened.
`gate2-rerank-protocol.md` and `gate2b-amendment.md` stay frozen; this
amendment replaces exactly one structural element — where the swap
alternatives come from — and records why.

## What the 2b wave measured

63/63 episodes, negative control within every config floor, 78
triggers across the 21 enforce episodes — and still zero swaps. The
absolute score-loss bound fixed the pricing and the arm stayed inert.

## Why (top-K restriction audit, committed corpus)

`pool_restriction_sweep` in `scripts/audit_safety_rescuability.py`,
same 7764-row / 189-board corpus, same amended rule, varying only the
pool the rule may search (rescued-safely counts over the 27
unsafe-incumbent trigger boards):

| pool | rescued |
|---|---|
| score-ordered top 3 (= the live retained top-K) | **0** |
| score-ordered top 8 | 3 |
| score-ordered top 16 | 10 |
| full candidate set | **18** |

The live instrument was structurally incapable of rescuing: at danger
boards, safety and immediate score are strongly anti-correlated, so
the safe alternatives sit deep in the score ordering that the retained
top-K is built from. Both inert waves are exactly reproduced by the
top-3 row. Pricing (2b) and pool selection (2c) were two independent
blocks; perception was never the problem (19/20 of the full-set picks
are physically safe).

## The amended element

The swap pool becomes **every legal candidate the search materializes
in the step**, collected by a bounded observer
(`SAFETY_RERANK_POOL_CAP` 4096) on the same hook the cross-step and
rollout collectors already use. Cost discipline:

- Collection is one list append per materialized candidate, every step.
- Logits over the pool are computed **only at triggered steps**
  (roughly four per episode in both waves); untriggered steps pay one
  incumbent forward, as before.
- The diagnostics record keeps only the top
  `SAFETY_RERANK_RECORDED_CANDIDATES` (12) pool entries by logit, plus
  a `pool_size` field, so traces stay bounded.
- Shadow mode runs the identical collection and scoring, so the
  physical negative control prices the observer and the triggered-step
  forwards.

Trigger (2.0), escape margin (2.0), absolute score-loss bound (1.0),
never-refuse, the seam, the arms, and all five episode gates are
unchanged. Offline expectation under the full pool: 18/27 fatal-choice
boards rescuable with one bad pick. The Gate 2c wave is the same
matrix; Gate 3 fresh-permutation confirmation still stands before any
default flips. No retuning of any constant on any of these streams.
