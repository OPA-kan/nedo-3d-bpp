# The teacher was scoring boards as full while 60% of them was free

Date: 2026-08-30. Branch `work/terminal-rollout-oracle`.
Follows `reports/candidate-support/rule-alpha-union-20260830.md`.

## What the rollout calls a terminal

`_terminal_rollout` values a board by forcing a candidate and then
continuing with frozen rank-0 over the generic provider's candidates.
Across the 108 terminal rollouts inside Cup 009's mining forks on
`dual-empty-permute-000-613`:

| termination | count | share |
|---|---|---|
| `no_retained_candidate` | 104 | **96.3%** |
| `no_safe_retained_candidate` | 4 | 3.7% |
| `stream_exhausted` | **0** | **0%** |

**Not one rollout ended by running out of items.** Every one ended
because the provider had nothing left to propose. And

    GENUINE_TERMINATIONS = {
        "stream_exhausted", "no_retained_candidate",
        "no_safe_retained_candidate",
    }

counts that as a finished board.

## So the teacher is not Monte Carlo

Stopping when the generator runs dry is not a Monte Carlo return to the
episode's terminal. It is an n-step estimate whose bootstrap term is
pinned to zero:

    V(s_t) ~= sum_{k<n} gamma^k r_{t+k} + gamma^n * V(s_{t+n}),
    with n ~ 9-11 and V(s_{t+n}) := 0

The zero is wrong, and by how much is measurable. On three cells, the
rank-0 continuation against rule-alpha's own play from the same board:

| cell | rank-0 continuation | rule-alpha | ratio |
|---|---|---|---|
| dual-empty | 10 placed / **7.92** | 39 / 31.55 | **3.98x** |
| single-empty-noshelf | 9 / **12.21** | 16 / 26.01 | 2.13x |
| dual-shelf-mixed | 11 / **7.45** | 10 / 8.32 (failed) | 1.12x |

## Widening the continuation recovers three quarters of it

The candidate union built for the train/inference mismatch also delays
`no_retained_candidate`: a provider with more to propose runs out later.
Six cells, same seed, `--rule-alpha-union-limit 4`:

| cell | generic | unioned | rule-alpha reference |
|---|---|---|---|
| dual-empty | 10 / 7.92 | 12 / 9.34 | 39 / 31.55 |
| dual-preloaded-dedicated | 14 / 10.54 | 17 / 12.87 | 27 / 23.08 |
| **dual-shelf-mixed** | 11 / 7.45 | **32 / 25.68** | 11 / 8.32 |
| single-empty-noshelf | 9 / 12.21 | 15 / 22.95 | 16 / 26.01 |
| single-empty-shelf | 7 / 9.84 | **20 / 32.11** | 22 / 34.70 |
| single-preloaded | 4 / 9.77 | 10 / 20.01 | 11 / 20.17 |
| **mean** | **9.2 / 9.62** | **17.7 / 20.50** | **21.0 / 23.97** |

The continuation nearly doubles in length and the fill it books rises
from 40% of rule-alpha's to **85%** -- three quarters of the gap the
teacher could not see. Cells ending `no_retained_candidate` halve, 6/6
to 3/6.

**On dual-shelf-mixed the composite beats both of its parts**: rank-0
choosing from the union reaches 25.68 where rank-0 alone reaches 7.45
and rule-alpha alone reaches 8.32. Proposals from rule-alpha, selection
by the generic ranker. That is the improvement operator exceeding its
inputs, which is the property an iteration has to have -- though on this
cell rule-alpha also failed early, so part of the gap is a failure
avoided rather than a better board built.

## A reversal recorded, not quietly dropped

`reports/candidate-support/rule-alpha-union-20260830.md` deliberately did
NOT union this provider, on the argument that the teacher's lookahead
should not be given rule-alpha's flavour or the whole exercise becomes
imitation one level up. That argument was reasonable and the measurement
overrides it: the price of the narrow teacher was a 60% underestimate of
board capacity on every verdict in nine cups, and the composite is
demonstrably not mere imitation, beating rule-alpha 3x on one cell.

## What this does not fix

The continuation still ends early. Unioned runs end
`selected_action_failure` on 3 of 6 cells -- a wider candidate set
includes physically riskier actions, and greedy rank-0 takes them. And
rule-alpha, the reference, is itself non-genuine on 4 of 6. **The
reference ceiling is not the true ceiling**; it is only a measurably
higher one than the incumbent.

## Consequence for the null results of 2026-08-30

Two experiments returned "no effect" earlier the same day, both measured
through this teacher:

- Stage 0 (mechanical perturbation of rule-alpha's action): 40 of 40
  comparisons `incomparable`, no wins and no losses.
- Archetype ladder swaps: most arms reached an identical terminal.

A perturbation that pays off at step 25 is invisible to a rollout that
stops at step 9. **Those nulls were measured with a broken instrument
and are not settled**; both should be re-run against the widened
continuation before being read as evidence that the rules are locally
optimal.

## Reproduction

    python scripts/probe_rollout_ceiling.py \
      --config-dir <cells> --cases <cell names> \
      --union-limit 4 --output <out>.json

Termination shares come from Cup 009's `cup-cell-*` artifacts, reading
`records[].mining.pair_rows[].terminal_termination`.
