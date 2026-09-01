# The learned policy is 2.7x worse than an actor already in this repository

Date: 2026-09-01. 200 cells, four arms, 800 episodes, **0 failures**.
Raw: `reports/arena/arena-reference-200-20260901.json`.

## The board

| arm | mean fill | mean placed |
|---|---|---|
| `current-agent` — hand-coded, generates its own moves | **28.07** | 28.66 |
| `rule-alpha` — hand-coded, generates its own moves | **23.11** | 21.55 |
| `champ` — the shipped learned champion | 10.37 | 10.83 |
| `awr` — today's advantage distillation | 10.32 | 11.04 |

Paired against the champion over all 200 cells:

| arm | mean difference | 95% CI | W–L–T | t |
|---|---|---|---|---|
| `current-agent` | **+17.70** | [+16.64, +18.71] | 191–8–1 | 33.8 |
| `rule-alpha` | **+12.74** | [+11.40, +14.01] | 175–25–0 | 19.2 |
| `awr` | −0.05 | [−0.31, +0.21] | 66–80–54 | −0.4 |

## Read those two rows together

The difference the season has spent nine cups chasing is **0.05 fill
points, with a ±0.26 interval**. The gap to an actor that has been in
the repository the whole time is **17.70**.

Thirty-four times. Every league verdict, every distillation, every
promotion decision has been a comparison between policies that all sit
in the same narrow band, far below the baseline. The band is real and
now precisely measured; so is the fact that nothing in it matters.

It also confirms the earlier Cup-corpus scoreboard was not a small-n
artefact: over the 18 cells every horse ran, the champion was fifth of
six at 10.00 against current-agent's 29.05, 0 wins to 18. At 200 cells
the same gap survives with an interval that never approaches zero.

## The cause is the candidate space, not the learner

`placed` is the tell: 10.83 against 28.66. The learned policy is not
ranking badly — **it is never offered most of the board**. It places a
third of the items.

Cup 008 measured this directly: rule-alpha's own executed action was
absent from the generic provider's candidate set on **89 of 89** boards.
A ranker over `C_generic` can only choose among moves that cap out
around fill 10. The hand-coded actors are not restricted to that set;
they generate their own placements, and reach 22–29.

So the binding constraint is none of the things this session
investigated in turn — not the loss function (advantage weighting: −0.05
±0.26), not policy iteration (the closed loop moved 3 verdicts in 20
forks for no net change), not the value function (a good board ranker
whose bootstrap term was 24x the gap it had to resolve), and not the
absence of a fast environment.

## What the published work does differently

Read against `alexfrom0815/Online-3D-BPP-PCT` (ICLR 2022), one
structural difference explains the rest.

Their action space is **EMS corner placements** — for every maximal
empty space, every orientation, its four corners
(`pct_envs/PctDiscrete0/space.py::EMSPoint`). That is the classical
combinatorial representation, chosen precisely so good solutions are not
excluded, and the scheme is a first-class flag they studied
(`LNES` ∈ EMS / EV / EP / CP / FC, EMS recommended).

And **their heuristic baselines pick from that same set**
(`heuristic.py` runs on the same env). Learned policy and baselines play
the same game, so "the learned policy wins" is a statement about
ranking.

In our league they do not play the same game. `current-agent` and
`rule-alpha` generate their own moves; the learned head is confined to
`C_generic`. The comparison was never fair, and the learner's ceiling
was set by its generator.

## What follows

Copying EMS is not the answer either: our containers are chamfered, have
shelves and dedicated priority bays, our items have soft and prioritised
classes, and wedge formation is domain knowledge the hand-coded actors
already encode. What transfers is the *property* — a candidate
generator that does not exclude the good solutions — not the
construction.

The next measurement is therefore cheap and already tooled:

1. Learn a ranker over `C_generic ∪ C_rule-alpha` (the union exists:
   `--union-rule-alpha`, support misses 100% → 0% on Cup 009's cells)
   and put it in the arena against **28.07**, not against another
   learned head.
2. Whatever the union does not close is the specification for a real
   candidate generator, in our geometry, with the archetype vocabulary
   (back / back-shelf / wedge-forming) the hand-coded actors use.

Only step 1 needs running. It answers, for the first time with a
reference on the board, whether a learned ranker over an adequate
candidate set can beat the hand-coded actor — which is also the first
question in this project whose answer could not be reached by imitation
of any single expert.

## Reproduction

    python scripts/evaluate_policy_arena.py \
      --arm champ=reports/cup/model \
      --arm awr=reports/value/advantage-policy-v1 \
      --arm agent=policy:current-agent \
      --arm rule-alpha=policy:rule-alpha \
      --baseline champ --streams 25 --workers 4 \
      --work-dir <work> --report <work>/arena-reference-200.json
