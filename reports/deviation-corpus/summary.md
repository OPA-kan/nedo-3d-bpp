# Deviation trigger: avoidable losses are common but not recognizable

Actions run `31941899714` collected branch labels on twelve permuted
pool-1 streams (six arrival-order permutations of each source case, same
item multiset, `top_candidates` siblings, steps 2–16). Pooled with the
original c000-k1/c001-k1 datasets this gives 14 streams and 77 usable
branch states, each with per-sibling q components and support ledgers.

## The two facts, side by side

**Avoidable losses are common.** In 28/77 states (36%) a sibling of the
policy's own top-3 strictly beats its choice on final placed — the mean
avoidable gap is about one placement per such state, with tails up to six.
The c000-k1 finding was not an outlier; single-deviation value is spread
across arrival orders of both cases.

**And they are not recognizable at decision time with these features.**
Leave-one-stream-out ridge over 13 decision-time features (step, sibling
q statistics, candidate kinds, support-ledger aggregates):

| outcome | base rate | held-out rank AUC | top-quartile trigger precision | gap captured vs overall |
|---|---:|---:|---:|---:|
| final placed | 0.36 | **0.512** | 0.32 | 1.47x |
| final fill | 0.44 | 0.603 | 0.68 | 1.90x |

On the outcome that matters most the trigger is chance. On fill there is
a weak real signal (AUC 0.60, top-quartile concentrates 1.9x of the
avoidable gap), not enough to power a live selective-deviation policy,
which would additionally need to know *which* sibling to take.

## Verdict on the deviation line

The chain closes: (1) avoidable single-deviation value exists and is
common; (2) wholesale harvesting is catastrophic (`tiebreak-probe`);
(3) selective harvesting needs a trigger, and the trigger is not in the
sibling-set statistics or the surface ledger. Whatever separates a
harvestable state from a frozen one is either in richer whole-board
structure (full height maps, pool composition ahead) or genuinely in the
future — the same glassy sensitivity that shattered the temporal-chunk
votes. Do not build a live deviation policy on these features; a future
attempt must first beat AUC 0.512 on placed with a new representation,
using this committed corpus, before spending any physics.

## Second collection: board features do not help, but the target is real

Run `31944370582` (plus `31944374285` for the fatal cases) re-collected
all 14 streams at schema 4, adding a per-container 4x4 height grid and
pool composition to every state (`schema4/`). Three findings:

1. **Board structure adds nothing at this resolution.** On the fresh
   corpus, board features score placed AUC 0.532 and fill 0.428
   (below chance); sibling+board 0.548/0.453. Single-collection sibling
   AUCs also swing between collections (placed 0.512 to 0.620, fill
   0.603 to 0.514), so no single-collection number should be quoted.
2. **Pooled over both independent collections (155 states), the
   definitive trigger numbers are placed AUC 0.561 with top-quartile
   precision 0.32 against base rate 0.35, and fill AUC 0.554.** No
   usable trigger in any tested feature set.
3. **The target itself is real and stable.** Matching the 77 (stream,
   step) states across the two independent collections, the avoidable
   label agrees on 72/77 (94%, kappa 0.86 against marginal chance).
   Avoidability is a near-deterministic function of the state — the
   information exists at decision time; sibling statistics and a 4x4
   grid simply do not resolve it.

Finding 3 upgrades the closing verdict from "possibly unknowable" to
"representation-bounded": a future attempt has a well-posed, stable
offline target and must beat pooled placed AUC 0.561 on this corpus
(both collections committed) with a richer state representation before
any physics is spent.
