# Live deadline shadow, three arms — the bottleneck moved

Date: 2026-08-25. Same 46 hard roots / 12 permute cells / 16 terminal
interventions (frozen cohort run `32763509936`), same deadline executor
(persistent PyBullet sessions, budget 2 of 3 branches, H ≤ 3 checkpoint,
10 s decision budget), real wall-clock, no value model. Per-intervention
rows: `geometry-policy-live-shadow-20260825.json`.

Runs (all at head `0483545`/`0fcb8b2`):

- **H1-leaking allocator** (historical baseline arm, re-run on current
  code): Actions `32802769267`.
- **Geometry-only policy** (no hidden physics inputs): `32802777408`.
- **Ranker next-best** (zero-cost, no NN): `32803397418`.
- Failed run, on record: `32802783183` requested `ranker_next` but
  executed allocator mode — the CLI parsed `--alternate-mode` and
  `main()` never passed it to `audit()`. Fixed with a regression test in
  `0fcb8b2`. That run stands as a valid geometry-arm replication: its
  recall outcomes are bit-identical to `32802777408`.

## Result — real wall-clock and recovery

| arm | reproduction | intervention in support | live intervention recovery | p50 | mean | p95 | max | ≤10 s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| incumbent-only (implied) | 30/46 (65.2%) | 0/16 | 0/16 | – | – | – | – | – |
| H1-leaking | 34/46 (73.9%) | 11/16 | **6/16** | 5.16 | 5.41 | 8.04 | 10.36 | 45/46 |
| geometry-only | 34/46 (73.9%) | 11/16 | **6/16** | 5.17 | 5.77 | 8.56 | 10.43 | 45/46 |
| ranker next-best | **35/46 (76.1%)** | 12/16 | **6/16** | 5.36 | 5.74 | 8.48 | 10.38 | 45/46 |

All arms hold the SLA at 45/46 (one ~10.4 s overrun each, ≈0.4 s past
budget; the original `d5efd57` run measured 46/46 at max 9.42 s — runner
variance, not a code change). All arms beat incumbent-only. The support
swaps behave exactly as the OOF gate predicted: ranker_next carries the
rank-1 interventions the geometry policy drops and loses the rank-2 ones
it uniquely catches.

## The decisive observation: recovery is capped by the checkpoint, not by support

Every arm recovers exactly **6/16** interventions live, despite carrying
11–12 in support. Five recoveries are common
(`…1b5ad6e1`, `…7fb1786c`, `…3ee943a7`, `…f660394b`, `…5989f40c`); the
sixth differs (`…bb6f8fa7` for H1/ranker arms, `…6cbea2f0` for the
geometry arm). The other 5–6 available interventions were **read to
H ≤ 3 and then rejected by the checkpoint Pareto rule** — the bounded
frontier kept the incumbent where the terminal oracle switches
(`…eee5813c`, `…5f0d2e03`, `…b4a49147`, `…c4bf8bb8`/`…38429895`/…).

Conversion from in-support to recovered is ~50–55% in every arm. A
perfect allocator (16/16 inclusion) would still cap near 8–9/16 under
the current decision rule. **The binding constraint has moved from
branch selection to the H ≤ 3 checkpoint switch decision** — the same
depth lesson the terminal-probe ladder taught: bounded-depth frontiers
do not reproduce terminal ordering.

## Verdicts

1. **Leak removal: PASS.** The geometry arm needs no pre-decision
   physics and matches the H1-leaking arm on every live metric within
   noise. The 8.16 s p95 headline survives without its hidden cost.
2. **NN vs zero-cost baseline: no live advantage.** Ranker next-best is
   equal on recovery (6/16), slightly ahead on reproduction (35 vs 34),
   at zero model cost. At n=16 none of these gaps is meaningful.
3. **Where the NN's unique value shows**: the geometry arm is the only
   one that recovered `…6cbea2f0` — a rank-2 intervention rank order
   cannot reach at budget 2. That is real but rare (1 live event).
4. **Scope**: this is a shadow on replayed prefixes — switches are not
   executed, so final trajectory outcomes are unchanged by construction.
   Trajectory-level outcome comparison requires the execution runner
   (as in `terminal-rollout-policy-results-20260825.md`).

## What this licenses next (in expected-value order)

1. **Fix the checkpoint decision rule before growing the allocator**:
   the recoverable headroom (5–6 interventions per arm) sits behind the
   H ≤ 3 Pareto switch, not behind support selection. Candidate lever:
   deadline-aware deepening of the *surviving* pair (read the two
   still-nondominated branches deeper instead of stopping at the common
   depth), which spends the remaining budget where the decision is
   actually contested.
2. **Production default meanwhile**: incumbent + ranker next-best at
   budget 2 — zero model cost, equal recovery, and the geometry policy
   stays a shadow arm until it beats that baseline on a bigger
   intervention cohort.
3. **Grow the hard-state cohort** (more dual-preloaded / dual-shelf
   permutations) before another model iteration: 16 interventions cannot
   separate 11/16 from 12/16.
