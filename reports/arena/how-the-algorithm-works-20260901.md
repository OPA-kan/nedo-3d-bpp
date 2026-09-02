# What the algorithm actually is, and what 2026-09-01 changed

A standing description of the live decision loop and the training loop
around it, written after a day of arena measurements moved the
understanding of where the binding constraint sits. Every claim below
cites the file it was read from or the measurement that produced it.

## 1. The live decision loop

`scripts/run_terminal_rollout_policy.py::run_episode`, one step:

1. **Observe.** `policy_observation(env, raw)` → depth map, container
   list (with `center`, chamfer `cut_x`/`cut_y`, shelf and priority
   flags), visible pool (`look_ahead: 10`).
2. **Propose.** `build_candidate_provider(...)(env, observation, limit)`
   — see §2, this is the crux.
3. **Screen.** For the teacher paths, `build_exact_physical_legal_filter`
   replays each proposal in a fresh simulator and keeps the ones the
   simulator accepts. Physics decides safety; nothing else does.
4. **Score.** `choose_root_candidate(...)` with the policy's rule. For
   `--policy learned`, `LearnedAllocatorPolicy.score_candidates` returns
   `sigmoid(score_j − score_incumbent)` per candidate with the
   incumbent floored at `switch_threshold`, and the argmax is executed.
5. **Execute.** `env.step(action)`; PyBullet settles it and returns
   `is_included / is_valid / is_placed_safe`.

Everything the season calls "the policy" lives in step 4.

## 2. What the candidate provider actually offers

`scripts/build_counterfactual_graph.py::build_candidate_provider`. Two
lines decide the shape of the whole problem:

```python
retain_item_best(...)                      # best-scoring placement PER ITEM
decisions = (settled + release)[: int(limit)]      # limit = --top-k = 3
```

`retain_item_best` keeps, for each visible item, **one** placement — the
highest-scoring one according to the hand-coded agent's own
`PlacementCore.top_candidates`. The survivors are sorted by that same
score and cut to `limit`.

So the set handed to the learned ranker is **at most three entries, each
one a different item, each already positioned by the hand-coded
scorer**. Measured on arena cells: 2.86–3.00 candidates per state.

**The learned policy chooses which item goes next. It has never chosen
where anything goes.** Position, orientation and container are decided
inside `PlacementCore` before the ranker sees anything.

## 3. The training loop

Nine Research Cups, each: six horses run six cells; every diversity
actor forks its own action against the champion's at each disagreement;
a fork that reaches two genuine terminals and a strict 4-head dominance
verdict becomes one preference pair; pairs are distilled into the next
champion ensemble.

Three things are worth stating plainly because they were not obvious
from inside the loop:

* Every cup ran `expansions=0, max_depth=1, allocation="frontier"` —
  **no tree search at all**. The expansion loop, both allocation rules
  and the value-leaf path are implemented and tested; nothing has used
  them.
* The distilled champion is deployed as a **policy head** (its argmax is
  executed), not as the rollout allocator its training target
  (`terminal_oracle_changes_incumbent_action` — "would reading this
  deeply change my choice?") describes.
* The rollout continuation took provider rank-0 from Cup 001 onward, so
  the improved policy never became the next rollout policy.

## 4. What the arena measured

`scripts/evaluate_policy_arena.py`, 200 cells (8 scenarios × 25 streams
from the arena prime band ≥ 809), paired, 0 failures.

| arm | mean fill | mean placed |
|---|---|---|
| `current-agent` (hand-coded) | **28.07** | 28.66 |
| `rule-alpha` (hand-coded) | 23.11 | 21.55 |
| `champ` (shipped learned champion) | 10.37 | 10.83 |
| `awr` (advantage distillation) | 10.32 | 11.04 |

`current-agent` − `champ` = **+17.70**, CI [+16.64, +18.71], 191–8–1.

And at 56 cells, the same champion with a wider candidate set:

| arm | mean fill |
|---|---|
| `champ-union` = champ + `--union-rule-alpha` | **24.50** |
| `champ` | 10.09 |

**+14.40**, CI [+12.95, +15.84], **55–1–0**. Same weights, same
features, no retraining. Only the candidate set changed.

## 5. What that rules out

Each of these was investigated on 2026-08-31/09-01 and measured as not
the constraint:

| suspected cause | verdict |
|---|---|
| the loss is a dominance verdict, not a return | advantage distillation: −0.05, CI [−0.31, +0.21] |
| policy iteration never closed | closed it: 3 verdicts moved in 20 forks, net 0 |
| the rollout tail is booked as zero | learned bootstrap: tail term 17.371 vs candidate gap 0.729 |
| no fast environment to do RL in | built one; its candidates are 112/112 legal but it models no stability |
| six cells cannot resolve anything | **true** — the arena fixed it, MDE 5.30 → 0.38 |
| the candidate space is the ceiling | **true** — +14.40 from the union alone |

## 6. Where the learner does and does not add value

`champ-union` − `rule-alpha` over 56 cells is **+2.31, CI [−0.14,
+4.84]** — the ranker does *not* beat the expert whose moves it borrows.
But the per-scenario signs are not random:

| two containers | | one container | |
|---|---|---|---|
| dual-empty | +7.94 | single-empty-noshelf | −1.76 |
| dual-preloaded-dedicated | +6.55 | single-preloaded | −2.25 |
| dual-shelf-mixed | +5.73 | single-empty-shelf | −4.01 |
| dual-dedicated-priority | +3.52 | | |
| dual-full-stream | +2.76 | | |

Five positive, three negative, split exactly on container count;
probability (1/2)^8 ≈ 0.4% under a null.

This is consistent with §2. rule-alpha's archetype ladder is a
within-container placement heuristic with no allocation rule. The
learned ranker picks *which item next*, which is also what decides
*which container gets filled* when there are two — so it contributes
where allocation exists and contributes nothing where the only question
is placement, which it never decides.

## 7. The architecture this implies

Not one policy, but a **portfolio with a learned selector**:

    C(s) = C_generic(s) ∪ C_rule-alpha(s) ∪ C_current-agent(s) ∪ ...
    a(s) = argmax_{c ∈ C(s)} score_θ(s, c)

Each expert contributes the moves it is good at; the learner routes
between them by scoring, with no hand-written routing table. Today's
per-scenario table is the routing this would have to learn, and it
already exists as data rather than as a rule someone wrote.

Implemented for this:

* `--union-rule-alpha` — rule-alpha's Layer 1 proposal family
  (measured: support misses 100% → 0%, Cup 009).
* `--union-expert current-agent|rule-alpha` (new) — run an exact actor
  as an **advisor**: its move is unioned into the candidate set every
  step and it never executes. Per-advisor counters record
  `asked / declined / added / already_present`, so "the advisor fired"
  is checkable before any result is read.
* `--arm NAME=<model>,union,expert-agent` in the arena composes them.

## 8. Open, in priority order

1. **Does `C_current-agent` close the remaining 4.33?** The advisor
   flag exists; the arena run is the measurement. `added` vs
   `already_present` also answers a question never asked: how often the
   generic provider already had current-agent's move. If it usually did,
   the gap is the ranker's, not the candidate set's, and §2 needs
   revising.
2. **Retrain on unioned candidate sets.** Today's `champ-union` is a
   ranker that never saw a rule-alpha candidate during training. Cup
   4/6/7/8 episodes carry no unioned sets, so this needs a corpus
   generated with the union on.
3. **The single-container loss.** The one place a learned ranker is
   strictly worse than the heuristic it draws from, and therefore the
   cleanest place to find out what it gets wrong.
4. **Placement, not just item order.** §2 says the learner has never
   chosen where. Whether it should is a design question this project has
   not yet put to a measurement.
