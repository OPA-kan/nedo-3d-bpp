# Task A bounded-rollout adoption run 30717998654 — per-repeat analysis

Actions run: https://github.com/OPA-kan/nedo-3d-bpp/actions/runs/30717998654
Head SHA: `896faa0` (`Validate Task A rollout at official budget`)
Case: bundled `sample_config.json` source 000 converted to Task A
(`look_ahead=1`, `max_space=1`, `visible_pool=[]`, `optimize=true`), 41 items.
Budgets: 150 s internal offline search, 180 s external optimization timeout,
8 s policy timeout. Three repeats per arm, one Ubuntu 24.04 runner each.

## Provenance

Two tiers of number appear below and they are not equally durable.

- **Committed** — from `summary.json` in this directory, which is in git.
- **Artifact** — from the per-episode `row.json` / `evaluation_results.json`
  inside the run's Actions artifacts. Those expire (2026-10-30) and are
  served from `*.blob.core.windows.net`, which several sandboxes cannot
  reach. Values in that tier are transcribed here precisely because they
  will not be recoverable later.

## Result

Committed, both arms, three repeats:

| arm | placed mean [min,max] | fill mean [min,max] | evaluated orders [min,max] | optimization s [min,max] | offline proxy placed |
|---|---:|---:|---:|---:|---:|
| base | 20.0 [20,20] | 29.298 [27.541, 30.176] | 3.0 [3,3] | 112.099 [105.208, 115.794] | 21.0 |
| bounded128 | 25.0 [25,25] | 34.949 [34.949, 34.949] | 51.333 [49,54] | 147.348 [146.498, 148.212] | 23.0 |

Artifact tier: centre-of-mass height about 0.753 m (base) to 0.735 m
(bounded128); near-miss count 0 in both arms; policy time about 6.51 s,
unchanged between arms.

## Per-repeat reading

**The bounded arm is fully deterministic; the base arm is not.** The bounded
arm's fill has `min == max == 34.94904885879026` across all three repeats.
Fill is a continuous function of the settled geometry, so three
bit-identical values mean the three episodes selected the same complete
order and the physics reproduced it identically. That is the expected
behaviour — `Agent.optimize` seeds its RNG from the item indices
(`OFFLINE_RANDOM_SEED`), so the only nondeterminism available is how many
evaluations fit in the wall-clock budget.

The base arm placed 20 every time but its fill moved across a 2.6-point
range. With only 3 evaluated orders and no per-item bound, which order the
search lands on depends on where the global deadline happens to cut the
first unplaceable item's scan. Same placed count, different packing.

**Evaluation count varied without changing the outcome.** The bounded arm
evaluated 49, 51 and 54 complete orders across the repeats — runner speed
noise — yet all three converged on the same order. The incumbent was
therefore already settled well before the budget ran out, which is the
signal that 128 attempts/item is not starving the search at this case size.

**The base arm stopped with time left on the clock.** It used 112.1 s of the
150 s internal budget. That is the moving-average guard in ADR-001 §5 doing
its job: it refuses to start an evaluation that costs more than the time
remaining. Base did not run out of clock — each of its three evaluations was
simply too expensive to allow a fourth. The bounded arm used 147.3 s and was
genuinely budget-limited.

## Local reproduction (2026-08-02)

Both arms were re-run once on a 4-vCPU Linux box with PyBullet, the same
config and budgets, to check the adoption before flipping the shipped
default. The `default` arm sets no `OFFLINE_*` variable at all, so it
measures the submission path rather than an environment override.

| arm | placed | fill | evaluated orders | one dry run | optimization s | CoM z | policy s |
|---|---:|---:|---:|---:|---:|---:|---:|
| base | 20 | 27.540718986088258 | 3 | 32.8–38.4 s | 113.8 | 0.7457 | 6.517 |
| default | 25 | 34.94904885879026 | 55 | 1.9–5.1 s | 148.2 | 0.7347 | 6.515 |

Both fill values are bit-identical to CI: `default` matches the bounded128
arm's constant 34.94904885879026, and `base` matches the CI base arm's
minimum 27.540718986088258. The offline search is deterministic given the
item set, so the same order reproduces across machines; the base arm's CI
spread comes from how many evaluations fit, not from randomness.

This is the measurement behind the per-repeat reading above:

- **A legacy dry run costs about 35 s.** Seed 38.4 s, best 32.8 s. Three of
  those plus the macro stage is 113.8 s, and the guard then refuses a fourth
  with ~36 s left. Bounded, one dry run costs 1.9–5.1 s.
- **The legacy search was starved, not inert.** It used 3 of the 1000
  evaluations `OFFLINE_MAX_EVALUATIONS` allows, adopted one pair macro, and
  the shipped order does differ from `constructive_order` (from position 3).
  But both of its neighbours scored proxy placed 21 with first failure at
  index 29 — identical to the seed — so the improvement was confined to
  lower-priority lexicographic keys. Bounded evaluated 55 orders, adopted 17
  macro moves, and lifted the proxy from 16 to 23.
- **The proxy's absolute level is not comparable across arms.** The legacy
  seed scores proxy 21 and the bounded seed 16 on the *same* item set,
  because a deeper per-item scan places more items per order. That is another
  reason to read the proxy only as a within-evaluator ranking.
- **Near-misses are 0 in both arms** (`settle_5_to_30_steps` and
  `settle_over_30_steps` both 0). Max settle angle is 2.542° for base and
  0.178° for the adopted arm, so the deeper order is also the quieter one.

**Both arms end invalid.** In this local reproduction `is_included` is true
but `is_valid` and `is_placed_safe` are false in both arms — base ends at
step 21 of 41 items, `default` at step 26. Under the repository's own rule an
episode is a physical failure unless all three are true, so neither arm
"passes"; the adoption moves the failure point later (placement 20 to 25), it
does not remove it. This is the open fallback channel, not a regression
introduced here. The CI artifacts could not be re-read to confirm the same
flags there, but the CI and local episodes agree bit-for-bit on fill, so they
are the same episodes.

## Proxy calibration

| arm | offline proxy placed | physical placed | error |
|---|---:|---:|---:|
| base | 21.0 | 20.0 | +1 (over) |
| bounded128 | 23.0 | 25.0 | -2 (under) |

The proxy's sign of error flips between arms, so it is not a calibrated
predictor in either direction. It ranked the two arms correctly (23 > 21
matches 25 > 20), which is the only property the search actually needs: it
compares orders against each other under one fixed evaluator. Use it as a
relative selector; do not quote it as a predicted score.

## What this run does not show

- One case. Source 001 was a synthetic Task A conversion and was dropped
  from the adoption matrix; no second real Task A case was measured.
- Two attempt budgets. 64 was rejected in run `30717533328`, 128 adopted
  here. Nothing at 256 or above, and no item-count-adaptive budget.
- The endgame is unchanged. Both arms still end on an invalid action; the
  bounded arm simply reaches placement 25 first. Nothing here bears on the
  fallback channel.
- 147.3 s of a 150 s internal budget leaves 2.7 s of headroom. A later change
  that slows the placement core will eat evaluations here first. Re-measure
  this table after any placement-core change, not just the Task B benchmark.

## Preceding runs

| run | budget | arms | outcome |
|---|---|---|---|
| `30717533328` | 30 s | base, bounded64 | rejected — orders up, executable prefix badly under-estimated, placed 20.0 -> 19.33 |
| `30717848749` | 30 s | base, bounded128 | positive — placed 20 -> 23, fill 29.171 -> 33.124, orders 1 -> 13.7 |
| `30717998654` | 150 s | base, bounded128 | adopted — placed 20 -> 25, fill 29.298 -> 34.949, orders 3.0 -> 51.3 |
