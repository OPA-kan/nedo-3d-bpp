# Five-config branch labels: the live ordering is not anti-predictive

Actions run `31931772512` scaled the long-horizon branch-label instrument
from one episode to five development configs (`b000-k15`, `b000-k20`,
`b000-k40`, `b001-k20`, `b001-k30`), six branch steps each, class-diverse
top-3 siblings at attempt budget 4096, schema 2 with per-sibling
`RankEvaluation` components. All five jobs completed. After the prefix and
parent-fingerprint validity filters, 25 branch states and 59 usable
branches remain; every usable branch carries its component vector.

## Headline: the 0.267 concordance did not replicate

The active ledger carried a one-episode suggestion (15 decided pairs,
concordance 0.267 versus chance 0.5) that the shipped immediate-Q ordering
might be *actively wrong* over long horizons. At five-config scale the sign
reverses:

| outcome | live-q concordant pairs | exact two-sided p | top-q reaches best outcome |
|---|---:|---:|---:|
| final fill | 27/39 (0.692) | 0.0237 | 15/25 states |
| final placed | 19/30 (0.633) | 0.2005 | 15/23 states |

The live ordering agrees with final fill significantly better than chance
and trends the same way on final placed. Every config is at or above 0.5 on
fill except `b001-k20` (3/6). The earlier number was small-sample noise
from a single episode.

## A linear refit of the same components loses held-out

Leave-one-config-out logistic/ridge reweighting of the recorded components
(volume, support, depth, lateral, lift, routing, zone, risk penalty)
scored 19/39 on fill and 10/30 on placed — at or below both chance and the
live ordering. The shipped scalar is not beatable by re-mixing its own
terms on this corpus. The full-data fit assigns support a negative weight
and single-component support concordance is low (3/10 on fill); that is a
hypothesis-generating oddity only — the same fit fails held-out, so it
licenses nothing.

## Consequences

- Do **not** launch an episode-level Ranker weight sweep on the strength of
  the old 0.267 signal; the powered replication points the other way. The
  predeclared proceed-condition for a sweep (held-out reweighting beats the
  live ordering) failed.
- The `ranker-form-never-swept` question stays open in the narrow sense
  (weights are still not knobs), but its motivating evidence is now
  reversed: the form is measured as better-than-chance on long-horizon
  fill, and the cheap linear alternative loses.
- Caveats: pairs within a state share their prefix history (the per-state
  top-pick row is the conservative view); 30–39 decided pairs across five
  configs; one repeat per branch, with reproducibility enforced by the
  instrument's prefix and parent-fingerprint checks rather than repeats.

Per-config datasets are committed beside this file; the analysis is
reproducible with `scripts/analyze_ranker_concordance.py`.
