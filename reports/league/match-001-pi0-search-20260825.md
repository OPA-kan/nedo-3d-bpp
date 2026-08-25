# League match 001: pi0-search dethrones pi0-legacy

Date: 2026-08-25. Runs: bootstrap `32819941124` (anchor), match
`32820682727` (challenger). Local promotion application reproduced the
CI verdict exactly; registry now at generation 1.

- Challenger: **pi0-search** — the hand-coded policy augmented by the
  V-free terminal-rollout search at every live decision. Not
  SLA-compliant (this league measures executed outcome quality only;
  the 10 s production stack is a separate concern).
- Champion: **pi0-legacy** — pure rank-0, the permanent anchor.
- Arena: the 10 frozen eval episodes (streams never used by any
  training wave), seed 42, paired and deterministic.

## Verdict: PROMOTED

| | count |
|---|---:|
| challenger wins (Pareto) | **3** |
| champion wins | 0 |
| equal | 3 |
| incomparable (trade-offs) | 4 |

Main gate: wins 3 > losses 0; aggregate hard heads exactly level
(violations Δ0 — including the three pre-existing violations on
dpd-193, unchanged; completion Δ0). League collapse checks: none
applicable at generation 0 beyond the anchor=champion identity.

## What the search actually changed

11 live action switches across the 10 episodes. Where they cashed out:
fill +1.016 on dual-shelf-mixed-167, +0.254 on
dual-preloaded-dedicated-191, +0.195 on single-empty-noshelf-191;
CoG improved on five cells; placed counts and violation counts
identical everywhere. Four episodes ended as head trade-offs
(logged, unadjudicated per contract); three were bit-equal.

## Meaning, stated carefully

This is the league instrument working end to end and the first
executed-outcome promotion through it: search genuinely improves the
executed episodes of π_0 on held-out streams, so the Expert Iteration
loop has a real teacher signal to distill. It is **not** the
breakthrough — that remains the first promotion of a *distilled* π_1
(a network, inside the SLA) through this same gate. pi0-search is now
the champion that π_1 ultimately has to face, with pi0-legacy anchored
forever underneath.
