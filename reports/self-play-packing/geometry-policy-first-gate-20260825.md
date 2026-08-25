# Geometry-only candidate policy — first gate (group-OOF)

Date: 2026-08-25. Training/evaluation ran to completion in Actions run
`32801677319` (push of `367d4ea`; all 12 recover-actions cells and the
train job succeeded). This report is a post-hoc analysis of that run's
frozen OOF scores (`rollout-geometry-policy-32801677319/oof-report.json`)
— no retraining, no threshold chosen on these labels. Per-intervention
raw rows with full root ids:
`geometry-policy-first-gate-20260825.json`.

Inputs at inference: observed board/container state, packed/visible item
sets, candidate item features, candidate `(container, x, y, z,
orientation)` geometry, incumbent flag. **No H1/H3/H5 physics, no
terminal outcomes, no future information.** Split: trajectory-cell
group-held-out OOF (12 groups, 3 repeats). Candidates are stored in
provider rank order with the incumbent at rank 0, so "ranker next-best"
below is candidate index 1 — a zero-cost baseline requiring no model
and no physics.

## Gate 1 — intervention-action inclusion recall (incumbent + 1 alternate)

131 roots, 16 terminal-oracle interventions (12 at rank 1, 4 at rank 2):

| support (2 branches) | interventions included | note |
|---|---:|---|
| incumbent only | 0/16 | by definition of intervention |
| incumbent + random alternate | 8/16 expected | uniform over 2 alternates |
| incumbent + **ranker next-best** | **12/16 (0.750)** | zero-cost, no NN (p=0.038 vs random) |
| incumbent + geometry policy alternate | **11/16 (0.688)** | matches the H1-leaking allocator's 11/16 (p=0.105 vs random) |

Overlap structure: both capture 8; **geometry-only captures 3 the ranker
misses — all three are rank-2 interventions** (roots
`…c4bf8bb8` dpd-permute-29, `…6cbea2f0` dpd-permute-53, `…38429895`
dsm-permute-23); ranker-only captures 4 (all rank-1); neither captures 1
(`…643cd840` dsm-permute-43, rank 2). The geometry policy found 3 of the
4 interventions that rank order cannot reach at budget 2, at the price of
losing 4 rank-1 interventions.

## Gate 2 — terminal action reproduction upper bound (2-branch support)

| arm | selected action inside support |
|---|---:|
| geometry policy | 126/131 (96.18%) |
| ranker next-best | 127/131 (96.95%) |

## Gate 3 — candidate branch reduction

Budget 2 of 3 root branches; mean terminal branch fraction 0.681 (68.1%
of full terminal branch workload; sequential-read estimate p95 ≈ 40 s —
the deadline executor, not sequential reads, owns the 10 s SLA).

## Gate 4 — calibration / score distribution (group-held-out)

Alternate (non-incumbent) candidate scores:

| class | n | mean | median | p10 | p90 |
|---|---:|---:|---:|---:|---:|
| true intervention target | 16 | 0.0728 | 0.0605 | 0.0038 | 0.1717 |
| other alternates | 240 | 0.0953 | 0.0715 | 0.0115 | 0.2455 |

**Calibration is inverted**: true targets score *lower* on average than
negatives. Root-level trigger AUC 0.584 / AP 0.172 (prevalence 0.122).
The 11/16 argmax result therefore rests on within-root relative order in
a small subset, not on a globally meaningful score. Do not threshold
these scores.

## Gate 5 — scenario/stream breakdown

| cell | roots | interventions | geometry captured | ranker next-best |
|---|---:|---:|---:|---:|
| dual-empty-permute-000-61 | 18 | 0 | – | – |
| dual-empty-permute-000-71 | 11 | 1 | 1 | 1 |
| dual-preloaded-dedicated-permute-000-17 | 9 | 0 | – | – |
| dual-preloaded-dedicated-permute-000-29 | 13 | 5 | 3 | 4 |
| dual-preloaded-dedicated-permute-000-41 | 15 | 1 | 1 | 1 |
| dual-preloaded-dedicated-permute-000-53 | 14 | 3 | 3 | 2 |
| dual-shelf-mixed-permute-001-23 | 12 | 3 | 2 | 2 |
| dual-shelf-mixed-permute-001-31 | 10 | 1 | 1 | 1 |
| dual-shelf-mixed-permute-001-43 | 13 | 2 | 0 | 1 |
| single-empty-noshelf-permute-000-79 | 5 | 0 | – | – |
| single-empty-shelf-permute-001-73 | 8 | 0 | – | – |
| single-preloaded-permute-000-89 | 3 | 0 | – | – |

Interventions remain concentrated in dual-preloaded-dedicated (9) and
dual-shelf-mixed (6).

## Gate 6 — the 16 interventions, one by one

Full root ids in the JSON sidecar. Summary: geometry policy retained 11
(8 shared with ranker order + the 3 rank-2 discoveries), dropped 5;
ranker next-best retained 12, dropped 4; the union of both alternates
would retain 15/16 but costs a third branch at those roots.

## Honest verdict

1. **The leak is fixed at no capture cost**: geometry-only inputs
   reproduce the H1-leaking allocator's 11/16 exactly, so the hidden
   all-candidates-H1 physics cost is gone. This was the question Codex
   stopped on, and the answer is yes.
2. **But the trivial baseline is not beaten**: ranker next-best gets
   12/16 with zero model and zero physics. On inclusion recall alone the
   NN is not yet earning its place. 11/16 vs uniform is p≈0.105 — not
   significant at this n.
3. The one place the NN adds something rank order cannot: 3 of 4 rank-2
   interventions. That signal (and the inverted calibration warning) is
   what the next data collection should grow — more hard roots in
   dual-preloaded / dual-shelf families, not more model.
4. Retroactive note: the earlier H1-leaking allocator result (11/16)
   was also never compared against ranker next-best; its apparent edge
   over uniform carries the same caveat.

## Next (live physical shadow)

The deadline executor consumes the same OOF-report schema, so the live
shadow runs with the allocator artifact swapped
(`rollout-geometry-policy-32801677319`) and — as of this change — an
`--alternate-mode ranker_next` arm as the zero-cost comparator. Three
arms on identical roots/physics: H1-leaking allocator (historical
baseline), geometry policy, ranker next-best. Judged on real wall-clock
(p50/p95/max, ≤10 s rate), terminal action reproduction, intervention
recall, physical steps.
