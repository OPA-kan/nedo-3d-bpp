# Selfplay hazard line: preregistered protocol

Committed 2026-08-17 JST, before any model is trained on the scaled
corpus. Successor to the closed reranker campaign, licensed by its
final finding (`safety-rerank-gate2c-fail-campaign-closed`): with
perception validated, pricing absolute, and the pool complete, acting
on one-step settle safety still failed the gates — the binding
constraint on the topple channel is afterstate VALUE.

## Relationship to closed lines (what this is NOT)

- NOT decision-time Monte-Carlo ranking
  (`mc-rollout-value-fails-validation-line-closed` stays closed; its
  own caveat — proper validation averages continuations over sampled
  streams, unjustified "by anything measured today" — is discharged by
  the Gate 2c closure, which is the new measurement).
- NOT hand-built receptivity ranking (`board-receptivity-mixed` stays
  mixed and unshipped; here the model LEARNS from the raw height
  field, 0.6 ms/row, instead of the 1.2 s/call hand scan).
- Honors `board-receptivity-is-not-a-feasibility-predictor`: nothing
  in this line calls a heightmap cell "placeable"; legality inside the
  selfplay env is the shipped release contract plus the risk gate.

## Corpus (schema 2)

`generate_selfplay.py` rows now carry the raw substrate: 16x12
max-pooled relative height grid of the afterstate, sealed-void
fractions (the one quantity a heightmap cannot express), corrected
largest-free-span, candidate geometry, and container dims. Label
unchanged: `placements_after` — survival under the sampled
seven-type prior (uniform-mix caveat carried verbatim from the
generator).

Scale: `selfplay-corpus.yml`, two container geometries (source cases
000 and 001) x 10 seed blocks x 250 episodes = 5000 episodes,
~100k rows — a 13x growth over the 7764-row physics corpus that
motivated the transformer question.

## Training (offline, torch, no live wiring)

Arms, all fitted on identical splits:

1. `linear_scalars` — the six collapsed descriptors + sealed void +
   span. The floor: what the fullness axis alone buys.
2. `mlp_scalars` — same inputs, MLP capacity.
3. `mlp_grid` — flattened 16x12 grid + scalars.
4. `attention_grid` — the transformer rematch at 13x data, tokens from
   grid patches + candidate + scalars. The standing hypothesis it
   tests is recorded: set_attention only tied the MLP at 7764 rows.

Targets: within-episode ranking of `placements_after` (primary),
`terminal_in_3` hazard AUC (secondary). Held-out evaluation is
leave-one-container-out AND episode-disjoint; single-split numbers are
not quotable (the pooled-only rule).

## Entry gate to any physics or live spend (fixed)

The committed bar stands unchanged: **pooled placed AUC > 0.561** on
the two-collection deviation corpus
(`reports/deviation-corpus/`, avoidable-label kappa 0.86). Mapping,
fixed here: branch afterstates are reconstructed from the
branch-labels run artifacts' step-state snapshots (runs 31941899714 /
31938388838 / 31931772512 cohort) — parent packed items painted onto a
fresh `AfterstateBoard`, forced action painted at its command pose —
and scored by the trained hazard model through the exact schema-2
feature path. AUC is per-state sibling ranking against final placed,
pooled over both collections, computed once per arm. No arm that
fails the bar is wired into anything live; passing licenses a hazard-
pricing experiment under its own preregistration (paired arms,
physical negative control, baseline floors — the Gate 2 machinery
unchanged).

## What would falsify the line

If no arm — including attention at 13x data — beats the bar, the
conclusion is that decision-time state as represented cannot carry
episode value, and the line closes toward mid-game search (wider
retained sets scored by Q) rather than toward more representation.
That closure would itself be recorded.
