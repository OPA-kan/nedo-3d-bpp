# The hand-coded actors end 70–97% of their episodes by self-termination

Date: 2026-09-01. Found while investigating why `dual-dedicated-priority`
showed the largest portfolio gain (+10.50). It is not what the
investigation was looking for and it matters more.

## The measurement

200 arena cells per actor, terminations as recorded:

| actor | `selected_action_failure` | `declined` | ran to `max_steps` | `stream_exhausted` |
|---|---|---|---|---|
| `current-agent` | **141 (70.5%)** | — | 52 | 7 |
| `rule-alpha` | 72 | **121** | 7 | 0 |

`rule-alpha` ends 193 of 200 (96.5%) by declining or by an unsafe move.
`current-agent` reaches the end of the item stream **7 times out of 200**.

By scenario, `current-agent`'s self-termination rate:

| scenario | rate |
|---|---|
| single-empty-noshelf | **100%** |
| single-empty-shelf | **100%** |
| single-preloaded | **100%** |
| dual-full-stream | 72% |
| dual-preloaded-dedicated | 72% |
| dual-dedicated-priority | 44% |
| dual-empty | 40% |
| dual-shelf-mixed | 36% |

**Their published fills are not their packing ability. They are where
they broke.**

## This is the official rule, not an arena artefact

`_safe` requires `is_included ∧ is_valid ∧ is_placed_safe`, which is the
same conjunction `docs/COMPETITION_RULES.md` §85 states. And every
official status recorded in `docs/OFFICIAL_SCORE_LOG.md` reads:

    "status": "Stopped in the middle.
       Did not satisfy {'is_placed_safe', 'is_valid', 'is_included'}"

Five submissions, five stops. The arena is reproducing a failure the
official evaluation has been reporting all along.

## The learned arms never do this

Terminations for `champ-all` over 56 cells: `no_safe_retained_candidate`
41, `max_steps` 14, `stream_exhausted` 1. **`selected_action_failure`:
zero.**

The mechanism is not intelligence. `choose_root_candidate` builds its
ranking from `safe_ids` — candidates an independently replayed simulator
accepted — so a learned policy can only ever execute a screened move. An
exact-actor policy executes its own command unscreened.

That is a confound in yesterday's comparison and it cuts the other way
from the usual worry: `champ-all` − `agent` = +1.82 is partly the screen,
not the ranker. It is also the most useful thing found today, because
the screen is separable from any learning.

## What it implies

The obvious change is to put the screen in front of the shipped actor:
propose, verify physically, and fall back to the next candidate when the
first is rejected — which is exactly what the portfolio arm does and
why it never dies.

The catch is the budget. The screen is a fresh-environment replay per
candidate, on the order of a second, and the official run reports
`time_results.policy` in single-digit seconds against an 8 s/action SLA.
So the question is not whether screening helps — the arena answers that
— but which cheap subset of the safety check can be afforded live.
`scripts/fast_afterstate_env.py` already computes the release contract
without physics, and today's measurement of it is directly relevant:
its candidates were **112/112** physically legal on boards a real run
visits, while it models no stability at all. The part it gets right is
the part that is cheap.

## Correction to today's reading

The `dual-dedicated-priority` +10.50 was reported as the overrides
"doing ten times more of something" there. That is wrong. On five of
seven cells `current-agent` died at step 17–26 with
`selected_action_failure` while the portfolio ran to 37–40 placements.
The gap is the actor's early deaths.

Nor did the portfolio "survive the fatal move": on `champ-all`'s own
trajectory the agent's proposed move was physically unsafe on only 1.6%
of decisions, and 0% on this scenario. The portfolio's early overrides
lead somewhere else, and the state where the actor jams is never
reached. Avoided and never-visited are not the same claim, and this data
cannot separate them.

## Full decomposition of the portfolio's 1697 decisions

| what happened | share |
|---|---|
| current-agent's move was safe and was followed | 66.3% |
| its move was already in the generic candidate set | 22.2% |
| its move was safe and the ranker overrode it | 9.9% |
| its move was physically unsafe | 1.6% |
