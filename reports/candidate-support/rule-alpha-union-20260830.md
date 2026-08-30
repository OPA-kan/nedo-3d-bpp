# Unioning a rule-alpha proposal family into the inference candidate set

Date: 2026-08-30. Branch `work/terminal-rollout-oracle`, code `ad2a68a`.
Follows the candidate-support mismatch recorded in
`reports/league/diversity-cup-008.md`.

## The mismatch, restated

Cup 008 measured rule-alpha's own executed action absent from the
candidate provider's set on **89 of 89 boards**, and the current agent's
on 78%. During mining `add_exact_agent_candidate` unions the exact actor
command into the fork's roots, so a preference label gets written for a
move that at inference is not in the choice set at all:

    teacher plays outside the candidate set
      -> mining adds it as an exact candidate
      -> label says "this move wins"
      -> at inference the move is not in the choice set

This sits **upstream of the ranker**. No preference head, however good,
can execute an action outside its own choice set.

## What was built

`scripts/rule_alpha_proposals.py`. `RuleAlphaAgent.policy` walks the
visible pool in its own priority order and returns the *first* item
Layer 1 can place. `RuleAlphaProposer.propose` runs the same walk
without stopping, collecting one placement per pool item. The actor's
own action is therefore the family's head **by construction**, and the
rest are the moves rule-alpha would have made for the other items on
offer.

`rule_alpha/` is vendored file-by-file from an orphan branch (see the
vendor note in `reports/league/cup-ledger.md`), so nothing there is
edited: the proposer drives a plain `RuleAlphaAgent` from outside and
reuses its board-rebuild preamble through the agent's own helpers.
Duplicating that preamble would let the family drift from what the actor
actually does, and drift is the bug being fixed.

Three flags on `run_terminal_rollout_policy`, all default-off so
existing behaviour is unchanged: `--union-rule-alpha`,
`--rule-alpha-union-limit` (default 4), and `--no-exact-agent-candidate`
— the last runs an exact actor with no safety net, so it may execute
only a move the provider itself supplied.

### What was deliberately not unioned

`vector_search_root`'s internal provider, which feeds the rollout
continuation. That continuation is the *teacher's* lookahead; making it
rule-alpha-flavoured would bias the teacher toward rule-alpha-shaped
futures, which is the imitation trap rather than an escape from it. The
root candidate set — what the ranker actually selects from — is unioned.
Proposals are borrowed from rule-alpha; the value judgement stays with
search.

## Support measurement, 31 boards

`dual-empty`, stream `permute-000-607`, seed 42, serial and uncontended:

| | value |
|---|---|
| rule-alpha's action present in the generic set | **0 / 31** |
| present in the rule-alpha family | **31 / 31** |
| family head *is* the actor's action | **31 / 31** |
| mean candidates: generic / family / union | 2.71 / 9.94 / **12.65** |
| mean duplicates, generic ∩ family | **0.00** |

The zero overlap is the sharpest number here. On every one of 31 boards
the two generators proposed **completely disjoint** action sets. The
generic provider is not a superset that ranks rule-alpha's move low — it
cannot express that move at all.

## The three-arm A/B

Same cell, seed 42, `--policy rule-alpha`, mining against the frozen
champion, `--mine-fork-budget 12`, `--rule-alpha-union-limit 4`.

| | A: baseline | B: union, exact ON | C: union, exact OFF |
|---|---|---|---|
| steps / placed / fill | 31 / 31 / 25.459 | 31 / 31 / 25.459 | 31 / 31 / 25.459 |
| candidate support hits | **0 / 31** | **31 / 31** | **31 / 31** |
| base candidates (total) | — | 84 | 84 |
| union additions / duplicates | — | 124 / **0** | 124 / **0** |
| disagreements | 3 | **25** | **25** |
| forked / skipped on budget | 3 / 0 | 12 / **13** | 12 / **13** |
| strict pairs | 3 | **10** | **10** |
| actor - champion (strict) | **0 - 3** | **6 - 4** | **6 - 4** |
| fork step-equivalents | 132 | 184 | 184 |
| termination | rule_alpha_declined | rule_alpha_declined | rule_alpha_declined |

### B and C are bit-identical

Not approximately equal — **equal**. Same 31 executed actions, same
selected candidate id at every step, same fork outcomes. The reason is
visible in the ids:

| arm | selected candidate id at step 0 | recipe |
|---|---|---|
| A | `candidate-2fa1e1d2485911157c07` | kind `rule_alpha_policy` |
| B | `candidate-96067444caae44c3ce89` | kind `rule_alpha_proposal` |
| C | `candidate-96067444caae44c3ce89` | kind `rule_alpha_proposal` |

In A the executed candidate is the one `add_exact_agent_candidate`
injected, because nothing in the provider matched. In B the injection
found the command **already present** as a proposal and reused that id,
adding nothing — so with the union in place the exact-agent injection is
a provable no-op, which is exactly what C confirms by removing it and
changing no number at all.

**The teacher and inference now share one action space.** The
special-case that let mining see the teacher's answer is no longer
load-bearing.

### The union changed the verdicts, not the play

All three arms executed the identical episode, which is expected:
rule-alpha plays its own move by construction, and the union changes
what that move is *compared against*, not what it is. What changed is
the mining yield:

- disagreements 3 -> 25, because the champion now has rule-alpha-style
  moves to prefer and can actually differ from the actor;
- strict pairs 3 -> 10 on the same episode and the same physics;
- the head-to-head flipped from **0-3 against** the champion to **6-4
  for** the actor.

**Caveat: the 3 -> 10 understates it.** The fork budget was not binding
in A (3 of 3 forked) and is binding in B/C (12 of 25 forked, 13 dropped
as `fork_budget_exhausted`). At the observed strict rate among forked
pairs, 10/12 = 83%, forking all 25 would have yielded roughly 21 pairs.
The budget, not the candidate set, is now the constraint on yield from
this cell.

Two further cautions. This is **one cell, n=1**, on a non-genuine
episode (`rule_alpha_declined` at step 31, as in Cup 008 — the union
does not fix rule-alpha's missing Layer 2). And strict-pair *count* is
not strict-pair *quality*: whether the larger corpus distils better is a
separate measurement, not shown here.

## Cost

The proposer is linear in the limit at roughly 1.5 s per proposal
(measured under three-way CPU contention, so pessimistic):

| limit | family | seconds |
|---|---|---|
| 1 | 1 | 1.19 |
| 2 | 2 | 2.76 |
| 4 | 4 | 6.01 |
| 8 | 8 | 12.90 |
| 16 | 10 (pool-capped) | 16.45 |

In the A/B the proposer took 205 s over 31 states = 6.6 s/state at
limit 4, against the generic provider's 0.5 s/state.

### Where the time actually goes

Not board features. The `Board` is built **once** per state and caches
grids, plateau stats, holes and plateau labels; `choose_for_item` does
not mutate it, so all ten items already share that work. Profiling one
`propose()` on a mid-episode board:

| | seconds | share |
|---|---|---|
| `propose()` total | 25.4 | |
| `layer1.generate_candidates` | 23.1 | 91% |
| `layer1.validate` (40,945 calls) | 21.8 | **86%** |
| `layer1.compute_features` | 1.5 | 6% |

rule-alpha generates ~4,100 candidate boxes **per item** and physically
validates each against every packed item. Inside `validate` the
dominant cost is an accessor rather than geometry:

    2,280,300 calls  agent/agent.py:1102  AABB.minimum
    2,315,380 calls  agent/agent.py:1106  AABB.maximum
    9,895,420 calls  numpy.asarray                     4.0 s

`AABB` is a frozen dataclass whose `minimum`/`maximum` are **properties
that rebuild two numpy arrays from tuples on every access**.
`penetrates_with_lateral_clearance` reads them eight times per call and
then uses only scalar indices — it allocates eight arrays to compute
three floats. Caching those two, taking a plain-float scalar path, and
vectorising the packed-item loop are behaviour-free changes with a large
multiplier. They live in `agent/agent.py`, the shipped production agent,
so they are recorded here rather than made as a side effect of this
work.

### Scope of the 8 s SLA

This pipeline is the offline Cup miner, not the submission. The 8 s
per-action SLA in `docs/COMPETITION_RULES.md` binds `agent/agent.py`,
which calls none of this. rule-alpha itself already pays ~1.2-1.9 s per
action for its single `choose_for_item`. The SLA question therefore
bites only if a union proposer ships in the live policy, and there
`limit=2` at ~2.8 s is already inside budget before any optimisation.

## The pool-width bound, and what it implies

A per-item family is bounded above by the pool width. Cup scenarios use
`look_ahead: 10` (`scripts/build_scenario_matrix.py`), which is where
the 2.71 -> 12.65 widening comes from. The shipped `sample_config` uses
`look_ahead: 1`, and there the family collapses to exactly the actor's
own move — the union adds nothing. This is pinned by a test rather than
left implicit
(`tests/test_rule_alpha_proposal_family_integration.py::test_a_one_item_pool_bounds_the_family_to_the_actors_move`).

So what this union buys is diversity in **which item to place and
where**, not multiple new moves for the *same* item. Widening the choice
set in the one-item regime needs

    a_{i,1}, a_{i,2}, a_{i,3}, ...

for a single item i. That is cheap to get: `choose_for_item` already
builds a full survivor list, sorts it per archetype, and then discards
everything but `pool_for_archetype[0]`. Taking the top-k there costs
almost nothing extra, because the expensive part — generating and
validating the ~4,100 boxes — has already been paid. Same-item
multi-proposal is close to free on top of the current cost; the
speed-up is a separate engineering problem in `agent.py`.

## Where this leaves the larger question

The union is a **baseline that makes teacher actions executable**, not
the goal. It removes the train/inference mismatch for rule-alpha and
nothing more. The self-growth question it unblocks is unchanged and
still open:

    C(s) = C_rules | C_geometric-search | C_learned-proposer

with the test being whether a generic geometric proposer produces
winning actions that rule-alpha does not have. Two families are still
missing. `C_other-experts` in particular is untouched: the current
agent's 78% miss rate comes from its own live generator (deadline-driven
and risk-reranked) diverging from `build_candidate_provider`'s per-item
fixed-attempt scan, which this rule-alpha-specific union does not
address.

## Reproduction

    python scripts/build_scenario_matrix.py \
      --stream-variant permute-000-607 --output-dir <cfg>

    python scripts/run_terminal_rollout_policy.py \
      --config <cfg>/dual-empty.json --case m-dual-empty \
      --environment-seed 42 --attempt-budget 128 \
      --top-k 3 --rollout-top-k 3 --rollout-max-steps 40 --max-steps 40 \
      --policy rule-alpha \
      --mine-against-model reports/cup/model --mine-fork-budget 12 \
      [--union-rule-alpha] [--no-exact-agent-candidate] \
      --output-dir <out>

Support, duplicate and cost figures come from a serial probe; the A/B
wall clock is not reported because the three arms ran concurrently.
