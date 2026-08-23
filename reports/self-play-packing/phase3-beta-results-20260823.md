# Phase 3 results: the feasibility beta passes its conjunction gates

Date: 2026-08-23/24 (Linux, PyBullet 3.2.7, torch CPU)
Contract: `learned-proposal-beta-contract.md`
Data: `reports/self-play-paired-physical/p3a-collection-20260823/` (12
cells, 126 roots, 6422 measurement rows: 730 safe / 5692 unsafe),
results in `reports/self-play-paired-physical/p3-results-20260823/`.

## Phase 3A — feasibility head and proposal

F(s, a) = P(safe), Set Transformer + action branch, 3-member ensemble,
split by cell (held out: `single-empty-shelf-original`,
`dual-preloaded-dedicated-source-001`):

- held-out AUC **0.930** (coverage rows alone 0.886; the 66 held-out
  legacy rows are all safe, so no AUC is defined there);
- the safe manifold — the thin contact band that release-from-top
  measurements proved is physics — is now *learned from PyBullet
  experience*, with no human contact geometry taught.

Proposal = 48 coverage points, soft resampling of 9 by F, permanent
floor of 3 raw points. Conjunction gates on the held-out cells
(16 roots, both arms 12 proposals/root, physically validated):

| gate | coverage arm | beta arm | pass |
|---|---|---|---|
| safe yield | 10.9% (21/192) | **15.1%** (29/192) | yes |
| mean stratum entropy | 2.485 | 2.485 | yes |
| novel safe strata | 21 | **28** | yes |
| reference recall | 0.009 | **0.030** | yes |

No proposal collapse: diversity is byte-identical to raw coverage
(every proposal in a distinct stratum) while yield, discovery and
recall all rise. The gate is a conjunction and every leg holds.

## Phase 3B — paired difference head, shadow only

DeltaY(s, a, a') with architectural antisymmetry
(N(s,a,b) − N(s,b,a)), trained on 1,306 same-state sibling pairs from
the safe measurements, held out by cell (386 pairs):

- per-head sign accuracy: fill **0.985** (n=275), soft violation 1.0
  (n=11), priority covered 1.0 (n=8), CoM 0.887, surface TV 0.797;
- within-root fill ordering tau from pairwise predictions: high on the
  cells where candidates were not tied;
- dominance classification accuracy 0.617 with **incomparable recall
  0.985** — the errors run conservatively: true dominances get called
  incomparable (75 of 93 misses), essentially never inverted (4
  inversions in 386). For a head whose later job is to *avoid false
  eliminations*, this is the right failure direction, and it stayed
  shadow-only per contract.

## Contract compliance notes

- Coverage floor was active in every proposal batch; F never hard
  -pruned anything.
- No outcome head touched proposal weights (3A used F alone).
- Resampling provenance records the generated finite set and each
  draw's conditional probability — no continuous density claimed.
