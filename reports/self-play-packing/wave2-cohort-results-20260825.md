# Wave-2 cohort: 284 roots, 34 interventions — the baseline holds, the NN closes in

Date: 2026-08-25. Cohort: hard-state collection run `32811046786`
(24 cells — wave 1's 12 plus 6 more dual-preloaded-dedicated and 6 more
dual-shelf-mixed streams). 284 roots, all terminal-truth complete, **34
terminal interventions** (25 at ranker rank 1, 9 at rank 2), prevalence
0.12 — stable across the doubling. Wave-1 cells recollected in the same
run reproduce their wave-1 intervention counts exactly (deterministic
replay confirmed). Per-intervention rows:
`wave2-shadow-comparison-20260825.json`.

## OOF gate on the retrained geometry policy (run `32811996191`)

Group-OOF, 24 groups, 3 repeats, geometry-only inputs (no physics):

| 2-branch support | interventions included |
|---|---:|
| incumbent + random | 17/34 expected |
| incumbent + ranker next-best | 25/34 (0.735, p=0.0045 vs random) |
| **incumbent + geometry policy** | **26/34 (0.765, p=0.0015 vs random)** |

- Overlap 19; geometry-only 7 (all rank-2, including `…643cd840` which
  wave 1 lost in every arm); ranker-only 6; neither 2.
- **The wave-1 calibration inversion is gone**: true-target alternates
  now score mean 0.178 vs 0.053 for negatives (wave 1: 0.073 vs 0.095,
  inverted). Root-level AUC 0.584 → 0.636, AP 0.172 → 0.262.
- Doubling the intervention data fixed the score quality and put the NN
  ahead of the zero-cost baseline on inclusion for the first time —
  by one intervention, which n=34 cannot call significant.

## Live deadline shadow, 94 hard roots (24 cells, real wall-clock)

Runs `32812383241` (ranker_next, production default) and `32812391048`
(geometry), both budget 2, H ≤ 3, contested 0, 10 s:

| arm | reproduction | IV in support | IV recovered | conversion | non-IV repro | p50 | p95 | max | ≤10 s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **ranker next-best** | **73/94 (0.777)** | 25/34 | **16/34 (0.471)** | 16/25 (0.64) | **57/60** | 5.54 | 8.64 | 11.15 | 93/94 |
| geometry | 67/94 (0.713) | 26/34 | 15/34 (0.441) | 15/26 (0.58) | 52/60 | 5.65 | 8.49 | 10.46 | 93/94 |

- Recovered by both: 14; ranker-only `…f9c6273f`, `…4c718535`;
  geometry-only `…ccd1b260` (a rank-2 catch).
- One SLA breach per arm (max 11.15 s / 10.46 s) — 93/94 ≤ 10 s.
- Checkpoint conversion improved vs wave 1 (~0.5 → 0.58–0.64) but is
  still the binding constraint: 9–11 in-support interventions per arm
  die at the H ≤ 3 Pareto decision.
- **The geometry arm pays a reproduction tax**: 52/60 vs 57/60 on
  non-intervention roots — its more adventurous alternates displace
  correct incumbent decisions at the bounded checkpoint more often.

## Verdicts

1. **Production default confirmed on the doubled cohort**: incumbent +
   ranker next-best wins every live metric (reproduction +6, recovery
   +1, conversion +0.06) at zero model cost. It stays the default.
2. **The geometry NN is no longer flat**: with 2× data its calibration
   inverted to correct, its inclusion edged past the baseline, and it
   is the only arm that reaches rank-2 interventions (7/9 in support).
   Its live weakness is not selection but what happens after selection
   — the checkpoint both under-converts its unique picks and lets its
   alternates disturb settled decisions.
3. The intervention-recovery ceiling is now clearly the **checkpoint
   decision rule**, with contested deepening already measured and
   rejected (`contested-deepening-shadow-20260825.md`). The remaining
   lever is roadmap item 10: V as a same-budget challenger at the
   checkpoint — score the already-read H ≤ 3 pair with
   `checkpoint (+) V(s_H)` at identical wall-clock and let the paired
   comparison decide. Never a mainline revival.

## Cost note

The whole wave-2 cycle — 24-cell collection (13 min), geometry recovery
+ retraining (5 min), two 24-cell live shadows (2–3 min each) — is
under 25 minutes of wall-clock on Actions, so the next
collection/retrain/shadow iteration is cheap.
