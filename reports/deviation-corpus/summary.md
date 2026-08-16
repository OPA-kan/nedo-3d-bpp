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
