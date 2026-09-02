# A portfolio reaches the hand-coded actor, and produces no new move

Date: 2026-09-01. 56 cells, five arms, 0 failures.
Raw: `reports/arena/arena-advisor-56-20260901.json`.

## The ladder

Each rung adds one expert's proposals to the candidate set. The ranker,
its weights and its features are identical throughout; only the menu
changes.

| arm | candidate set | mean fill | mean placed |
|---|---|---|---|
| `champ-all` | generic ∪ rule-alpha ∪ current-agent | **30.65** | 30.93 |
| `agent` | current-agent generates its own | 28.83 | 29.23 |
| `champ-union` | generic ∪ rule-alpha | 24.50 | 23.86 |
| `rule-alpha` | rule-alpha generates its own | 22.19 | 20.16 |
| `champ` | generic | 10.09 | 10.61 |

| paired | mean | 95% CI | W–L–T | sign p |
|---|---|---|---|---|
| `champ-union` − `champ` | **+14.40** | [+12.95, +15.84] | 55–1–0 | 1.6e-15 |
| `champ-all` − `champ-union` | **+6.15** | [+4.79, +7.54] | 50–6–0 | 1.0e-09 |
| `champ-all` − `rule-alpha` | **+8.46** | [+6.03, +10.98] | 43–13–0 | 7.3e-05 |
| `champ-all` − `agent` | +1.82 | [+0.06, +3.70] | 31–24–1 | **0.42** |

## Correction

At 37 completed cells this comparison read +2.31 with a CI that clearly
excluded zero, and was reported here as the learned ranker beating the
best hand-coded actor. **That is withdrawn.** At 56 cells the interval's
lower bound is +0.06 and the sign test is 31–24, p = 0.42. A bootstrap
interval and a sign test disagreeing is itself the signal: the mean is
carried by a few wide cells, not by a broad edge.

Per scenario against `agent`:

| scenario | difference |
|---|---|
| dual-dedicated-priority | **+10.50** |
| dual-full-stream | +3.84 |
| single-empty-shelf | +3.35 |
| dual-empty | +0.66 |
| single-preloaded | +0.57 |
| dual-shelf-mixed | −0.29 |
| dual-preloaded-dedicated | −1.15 |
| single-empty-noshelf | −2.91 |

Drop `dual-dedicated-priority` and the remaining seven average +0.58.
The honest verdict is **level with the hand-coded actor**, possibly a
little ahead, not established as ahead.

What *is* established, at p < 1e-9, is the ladder: the candidate set is
worth +14.40 and then +6.15, with the same frozen weights.

## What the winning arm actually is

`add_exact_agent_candidate` gives a unioned expert move
`selection.rank = -1`, and `_rank_key` sorts on that rank — so the
expert's move becomes the **incumbent**, and the preference head's 0.5
floor keeps it unless an alternate clearly beats it.

    advisor asked 1738 · added 1362 (78%) · already present 376 · declined 0
    ranker overrode the incumbent on 304 of 1697 decisions (18%)
    executed: current-agent 1125 (66%) · other 572 (34%)

So `champ-all` is precisely: **run current-agent, and override it 18% of
the time.** The +1.82 is the measured net value of those overrides.

The 78% is the current-agent counterpart of the Cup 008 measurement for
rule-alpha (89/89): current-agent's chosen move is absent from the
generic provider's candidate set on 78% of decisions.

## Why no new move appears

Of 1697 executed actions, **zero** are moves no human-authored generator
proposed. Every one traces to `PlacementCore`'s per-item best,
rule-alpha's archetype ladder, or current-agent's own solver. The
learner's entire contribution is *which* authored move to take.

Read against `Online-3D-BPP-PCT`, this is not a shortfall of the
learning half. We now have the same loss (advantage-weighted regression,
measured), a value function, a closed policy-iteration loop, and a
tested tree search. What we do not have is their **generator**. EMS
enumerates the four corners of every maximal empty space — candidates
produced because a region is *empty*, not because a heuristic judged it
good. That is the only place in their pipeline where a move no one
thought of can enter, and it is the one part not copied here.

The second prerequisite is also missing: their novelty is found by
millions of steps in an analytic environment. The champion was distilled
from ~1500 logged decisions in PyBullet. Even given EMS candidates, a
preference no heuristic encodes is not learnable from that.

So recombination is exactly what the architecture can produce, and it
produced it: +14.40 and +6.15 up the ladder, landing level with the best
hand-coded actor while executing its move two thirds of the time.

## Caveat on the cap

`--max-steps 40` binds unevenly: `champ-all` 30% of episodes, `agent`
26%, `rule-alpha` 4%, `champ-union` and `champ` 0%. The two top arms are
therefore both truncated and their fills are lower bounds; the
`champ-all` vs `agent` comparison is roughly fairly biased, while the
ladder rungs are conservative.

## Next

1. **A mechanical candidate generator for our geometry.** EMS's
   property, not its construction: chamfered containers, shelves,
   dedicated priority bays, soft items. This is the only route to a move
   nobody authored.
2. **Retrain on unioned candidate sets.** Every arm above uses a ranker
   that never saw a rule-alpha or current-agent candidate in training.
3. **`dual-dedicated-priority` (+10.50).** Whatever the overrides are
   doing there, they are doing ten times more of it than anywhere else,
   and priority routing is the one axis the archetype ladder does not
   encode.
