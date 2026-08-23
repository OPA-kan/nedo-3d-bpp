# Phase 1B pilot: coverage support under real physics

Date: 2026-08-23 (Linux, PyBullet 3.2.7)
Data: `reports/self-play-paired-physical/coverage-audit-20260823/`
Instruments: `scripts/coverage_action_sampler.py`,
`scripts/audit_coverage_support.py`

## Setup

12 roots (2 cells: `single-empty-noshelf-original`,
`dual-shelf-mixed-original`, steps 0-5 of the executed trajectory), per
root: 96 coverage samples per z mode (volume, release_top) plus 32
legacy proposals, all validated by the same fresh-replay physical
filter. ~230 (item, container, orientation) strata per state, so the
96-sample budget places under one sample per stratum per root.

## Measurements

| quantity | volume | release_top |
|---|---|---|
| P(safe \| coverage) | **6.5%** (75/1152) | **0.0%** (0/1152) |
| legacy-safe recovered (xy <= 10 cm) | 0/384 | 0/384 |
| legacy-safe with any same-stratum safe neighbor | 6/384 (nearest 0.27-1.0 m) | 0/384 |
| coverage-only safe strata | 69 | 0 |

Legacy proposals were 32/32 safe at every root.

## What the numbers mean

1. **The safe set is a thin manifold hugging contact surfaces.**
   Release-from-top fails *systematically*: the settle validator rejects
   large drops (displacement/rotation thresholds), so "let gravity find
   the contact" is not available in this environment — that is a
   physical law of the simulator now measured, not an implementation
   detail. Uniform volume sampling still lands in the manifold 6.5% of
   the time (the acceptance band above contact plus lucky stack
   contacts), which is a usable, unbiased data-collection rate: about
   6 safe novel actions per root at this budget.
2. **Legacy recovery is a density question, not a feasibility one.**
   With <1 sample per stratum, almost no legacy-safe action even shares
   a stratum with a safe coverage point; nearest in-plane distances are
   0.27-1.0 m. Recovering legacy's contact placements at 10 cm needs
   10-100x per-stratum budget — or the learned proposal whose job that
   manifold is (Phase 3).
3. **Coverage already produces safe support outside everything legacy
   emitted** (69 strata). Caveat kept honest: with `legacy_limit=32`
   most of those strata are *unproposed* by legacy rather than proven
   unsafe for it, so this upper-bounds legacy blindness; the
   demonstrated fact is that strategy-free sampling yields legal
   actions the legacy pipeline never surfaces — exactly the raw
   material a non-distilled beta needs.

## Decision points left open (deliberately)

- **Scale as-is (recommended for data collection now):** 6.5% at ~15
  preview replays per safe action is affordable; a
  `A_legacy ∪ A_coverage` physical-outcome collection can start with
  the sampler unchanged, provenance already flowing.
- **A third geometry-only z mode from the observation's depth map**
  (z = observed surface height + clearance at the sampled (x, y)): the
  height map is simulator-published state, but "place at contact" is a
  reparametrization that encodes more than the raw action domain —
  whether it stays inside the Strict-Zero boundary is a contract
  decision, not an implementation one.
- **Leave manifold discovery to beta:** the 6.5% stream plus legacy
  data is the training signal; the thin-manifold measurement above is
  the quantitative argument for why a learned proposal earns its place.

## Costs

~6.5 s per root per 96-sample mode at empty-container states (one
preview replay per sample; grows with prefix length). Full pilot: under
3 minutes per cell.
