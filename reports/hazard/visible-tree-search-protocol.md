# Visible-pool tree search: preregistered protocol

Committed 2026-08-17 JST before any implementation result is opened.
Design rationale: docs/theory/LITERATURE_SEARCH_DIRECTION.md (ToP's
division of labor — enumerate the visible future, measure the leaf,
never ask a predictor to carry the whole tail).

## Mechanism (knob `VISIBLE_TREE_SEARCH`, default off)

At each step, after the shipped policy produces its incumbent choice:

1. Expand the incumbent and up to B-1 retained alternatives (B = 4)
   as depth-1 afterstates on the agent's own heightmap machinery.
2. For each, enumerate the remaining visible pool items' best
   candidates (per-item best by the shipped score, same legality and
   risk gate) to depth D (D = 2, i.e. two further placements).
3. Score each leaf by MEASURED receptivity: the count of legal,
   risk-gated placement options per remaining visible item class on
   the leaf board, summed with equal class weights, plus the path's
   shipped scores.
4. The action played is the depth-0 root of the best path ONLY if its
   path score beats the incumbent's path by more than a tie band;
   otherwise the incumbent stands (never refuse, never fall through).

Shadow mode logs would-change without acting. Budget guard: the
search runs inside a fixed wall-clock slice (2.0 s) and degrades to
the incumbent when exhausted; per-step time is recorded.

## Stages and gates

Stage 0 (shadow): 7 guard configs x 3 replicates, arms {base,
shadow}. Gates: bit-identical actions under shadow (negative control);
would-change fires on >= 5% of steps (else the mechanism is inert and
closes); per-step overhead within the 8 s budget with margin (max
policy seconds <= 6).

Stage 1 (enforce, only if stage 0 passes): arms {base, tree_null
(shadow compute), tree_search (enforce)} x 3 replicates x 7 configs,
adjudicated by scripts/adjudicate_safety_rerank.py's gate pattern:
pooled placed strictly higher, paired wins >= losses, no config below
its baseline.json floor, transport_invalid non-increasing, negative
control within floors.

Stage 2: fresh-permutation confirmation, same gates, before any
default flip.

Closure is symmetric: failing any stage closes the line with the knob
at off and the result recorded.
