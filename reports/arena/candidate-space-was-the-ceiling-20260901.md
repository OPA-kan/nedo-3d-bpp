# The candidate space was the ceiling: same ranker, +14.40 fill

Date: 2026-09-01. 56 cells, four arms, 0 failures.
Raw: `reports/arena/arena-union-56-20260901.json`.

## The experiment

One arm only differs by a flag. `champ` and `champ-union` are the
**same frozen ensemble**, same weights, same features. `champ-union`
gets `--union-rule-alpha`: `C(s) = C_generic(s) ∪ C_rule-alpha(s)`.
No retraining, so nothing about the learner changes — only what it is
allowed to choose from.

The union demonstrably fired: candidates per state 2.86 → 5.89, 140
unioned candidates added on a single cell, episodes 14 → 35 steps.

| arm | mean fill | mean placed |
|---|---|---|
| `current-agent` (hand-coded) | **28.83** | 29.23 |
| **`champ-union`** | **24.50** | 23.86 |
| `rule-alpha` (hand-coded) | 22.19 | 20.16 |
| `champ` | 10.09 | 10.61 |

| paired | mean | 95% CI | W–L–T | sign p |
|---|---|---|---|---|
| `champ-union` − `champ` | **+14.40** | [+12.95, +15.84] | **55–1–0** | — |
| `champ-union` − `rule-alpha` | +2.31 | **[−0.14, +4.84]** | 33–23–0 | 0.23 |
| `champ-union` − `agent` | **−4.33** | [−6.62, −2.06] | 16–39–1 | 0.003 |
| `agent` − `rule-alpha` | +6.64 | [+3.97, +9.39] | 42–14–0 | 0.0002 |

## What this settles

**The learner was never the problem.** The identical ranker goes from
10.09 to 24.50 — from level with three trivial rule studs to above
`rule-alpha` — purely by being offered a wider set of moves. 55 wins to
1 loss. Nine cups of distillation were optimising a ranking over a
candidate family that caps out around fill 10.

Every negative result this session produced sits under that ceiling and
is now explained rather than merely recorded: the advantage-weighted
distillation (−0.05, CI ±0.26), the closed policy-iteration loop (3
verdicts moved in 20 forks), the learned bootstrap (24x scale
mismatch). They were all comparisons between rankings of the same
inadequate set.

## What it does NOT settle

**The learned ranker does not beat the expert whose moves it borrows.**
+2.31 over `rule-alpha` with an interval that contains zero, 33–23. And
it is significantly below `current-agent`, by 4.33.

So "the learner adds value on top of the expert" is **not** demonstrated
in aggregate. Claiming it from the 2-cell smoke test (+17.92, which read
as 27.31 against `rule-alpha`'s 23.11) would have been wrong: at 56
cells the same arm is 24.50. Small n overstated it again, as it did this
morning with the six-cell distillation comparison.

## Where it does add value, and it is not random

`champ-union` − `rule-alpha`, per scenario:

| scenario | difference |
|---|---|
| dual-empty | **+7.94** |
| dual-preloaded-dedicated | **+6.55** |
| dual-shelf-mixed | **+5.73** |
| dual-dedicated-priority | **+3.52** |
| dual-full-stream | **+2.76** |
| single-empty-noshelf | −1.76 |
| single-preloaded | −2.25 |
| single-empty-shelf | −4.01 |

**Every two-container scenario positive, every one-container scenario
negative.** Under a null of no structure that sign pattern has
probability (1/2)^8 ≈ 0.4%.

The reading follows the mechanism: rule-alpha's archetype ladder is a
*within-container* placement heuristic and carries no allocation rule.
Where there are two containers, choosing which one to fill is a decision
its ladder does not make and the learned ranker does. Where there is one
container there is no allocation to get right, and the ranker is left
trying to beat rule-alpha's own ordering at rule-alpha's own game --
which it loses on all three.

Seven cells per scenario is small and the per-scenario magnitudes should
not be quoted; the *sign pattern* is the finding.

## Next

1. **Union `C_current-agent` too.** `current-agent` is still 4.33 above,
   and the machinery to union an exact actor's move already exists
   (`add_exact_agent_candidate` / `find_exact_agent_candidate`). The
   target is `C_generic ∪ C_rule-alpha ∪ C_current-agent`.
2. **Retrain on unioned candidate sets.** Today's arm is a ranker that
   has *never seen* a rule-alpha candidate in training, choosing among
   them at inference. Cup 4/6/7/8 episodes carry no unioned sets, so
   this needs a corpus generated with the union on.
3. **The single-container loss is the specific defect to chase.** It is
   where a learned ranker is strictly worse than the heuristic it draws
   from, so it is the cleanest place to find out what the ranker is
   getting wrong.

## Reproduction

    python scripts/evaluate_policy_arena.py \
      --arm champ=reports/cup/model \
      --arm champ-union=reports/cup/model,union \
      --arm agent=policy:current-agent \
      --arm rule-alpha=policy:rule-alpha \
      --baseline champ --streams 7 --workers 4 \
      --work-dir <work> --report <work>/arena-union-56.json
