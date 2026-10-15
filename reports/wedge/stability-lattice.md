# The stability lattice re-read: what the constant 4.1775 says about N

The platform refit (`platform-refit.md`) found the platform's stability
score sitting on a lattice, 4.175 per counted episode, and read it as
N = 19 episodes all counted. This note re-reads the same numbers over all 33
scored builds (v1 to v50) against the alternative readings, because the
question "are there platform episodes we do not get credit for" decides
whether any count lever can still pay. Script and data:
`reports/wedge/stability-lattice/lattice.py`, `data.json`.

## 1. The constant

stability / round(stability / 4.175) over the 33 builds: mean 4.1755, sd
0.016; without v24 (the odd build) and v49 / v50 (the two with a known
negative residual, the band's and the columns' topples): **mean 4.1775, sd
0.0051** (0.12 %), from v1 (placed fraction 0.504, k = 11) to v46 (0.636,
k = 19). The steps at every change of k, read as the stability change per
episode gained or lost, run 4.01 to 4.32.

| build | stab | k | stab / k | frac | fill | sample placed A / B / C |
|---|---:|---:|---:|---:|---:|---|
| v1 | 45.87 | 11 | 4.1700 | .504 | 35.63 | |
| v7 | 37.60 | 9 | 4.1778 | .488 | 34.52 | |
| v12 | 54.46 | 13 | 4.1892 | .540 | 34.05 | |
| v18 | 62.69 | 15 | 4.1793 | .553 | 34.82 | |
| v24 | 46.43 | 11 | 4.2209 | .545 | 31.78 | |
| v31 | 75.22 | 18 | 4.1789 | .610 | 37.90 | 25 / 25 / 23 |
| v38 | 75.15 | 18 | 4.1750 | .614 | 37.95 | 25 / 25 / 25 |
| v43 | 79.28 | 19 | 4.1726 | .637 | 39.18 | |
| v44 | 75.19 | 18 | 4.1772 | .635 | 39.01 | 25 / 26 / 24 |
| v46 | 79.26 | 19 | 4.1716 | .636 | 39.14 | 25 / 26 / 25 |
| v49 | 78.48 | 19 | 4.1305 | .648 | 39.65 | 25 / 26 / 25 |
| v50 | 78.19 | 19 | 4.1153 | .645 | 38.62 | 25 / 26 / 24 |

(The full table is in the script's output.) The constant does not move with
the placed fraction (r = -0.68 over builds, carried by v49 / v50 alone) nor
with the official samples' placed counts (r = -0.29); it moves with the
bench's topples per episode (r = -0.57, n = 10; -0.165 per topple an
episode, v49 and v50 at the end of that line).

## 2. What a constant to 0.1 % can and cannot be

The README says the stability score is the shake test ("how little the
cargo moves when the container is shaken") and that every component but the
fill is zero for an episode that does not load "a certain number" of items
(the half is the refit's fit, not the README's number). A per-episode
quantity read off the physics cannot be the same to 0.1 % across builds
whose topple rates vary from 0.19 to 0.38 an episode and whose placed
counts vary by 30 %. So for a counted episode the stability score is, to
that precision, a fixed credit, and the lattice constant is

    4.1775 = (100 / N) x s,

with s the credit's share of 100. The candidates:

| N | s | per-episode cog / placement / soft at v50 (score x N / 19) | what s would have to be |
|---:|---:|---|---|
| 19 | 0.794 | 64.8 / 50.4 / 50.1 | every counted episode of every build from v1 to v46 scoring 79.4 % on the shake test, to 0.1 %: no physics does that |
| 20 | 0.835 | 68.2 / 53.1 / 52.7 | the same objection |
| 21 | 0.877 | 71.6 / 55.7 / 55.4 | the same |
| 22 | 0.919 | 75.1 / 58.4 / 58.0 | the same |
| 23 | 0.961 | 78.5 / 61.0 / 60.6 | one unstable box in 25, or the episode's last (failing) action in the denominator: n / (n + 1) = 0.961 at n = 24.3, the official samples' mean. But that model predicts the constant rising with n (4.14 at n = 20, 4.19 at n = 27) and it does not. |
| 24 | 1.003 | 81.9 / 63.7 / 63.3 | full credit; but 100 x 19 / 24 = 79.17 and v43 scored 79.28, and the per-episode steps reach 4.32 (continuous parts of about 0.1 can carry both) |

The two readings that survive are N = 23 with a constant 96 % credit, and
N = 24 with full credit and a 0.1-0.3 excess that the continuous (topple)
part would have to supply with the wrong sign. Under either, **k = 19 of 23
or 24: four or five platform episodes are not counted.** The N = 19 reading
needs a constant 79.4 % credit for every episode, which is the one
reading the constant's tightness rules out.

## 3. The placed-fraction objection, and what it assumes

The refit rejected N > 19 because the platform's placed fraction (0.6446 on
v50) is at or above the bench's sample suites (0.62-0.65) and the official
samples (A 25 / 41, B 26 / 42, C 24 / 42: 0.57-0.62): with four uncounted
episodes at 0.5 or less, the counted ones would have to average 0.675. That
holds only if (a) the fraction is a plain mean over all N episodes and (b)
an uncounted episode is one that placed half or fewer. Neither is in the
README. If the fraction and the fill are averaged over the counted episodes
(the evaluation dict carries both per episode; the aggregation is the
platform's), (a) fails. If "a certain number" is not the half, or if an
episode loses its four components for another reason (an action the
validator refused, an item outside the container at the end: the run's
status string names exactly `is_included`, `is_placed_safe`, `is_valid`),
(b) fails, and the uncounted episodes can be ones that placed 0.6.

The transitions are consistent with (a): v11 -> v12 gained 3 episodes with
the fraction +0.040, v41 -> v43 gained 2 with +0.034, v43 -> v44 lost 1
with -0.0022 (an episode falling from about 0.55 to 0.5 moves a plain mean
over 23 by -0.002). They do not decide (b).

## 4. What decides it: one diagnostic submission

A build that declines every Task B item from the first call (the surrender
action at step 0) reads, from one platform result:

- **N_B** from the stability drop: 4.1775 x N_B if every B episode was
  counted before, less if not (each uncounted B episode drops nothing);
  with N_A + N_C from the remainder.
- **the aggregation of the fraction and the fill**: a plain mean over all
  N drops by N_B / N x (the B fraction), a mean over counted episodes
  drops only by the B episodes' share of the counted ones.
- **cog, placement, soft per B episode**, from their drops, which prices
  the B lever directly in platform points.

A second build declining Task C does the same for C and leaves A by
subtraction. Each costs one platform result and nothing else; the agent
code is a two-line override in `submission/agent.py` (the surrender action
when the observation's task is B). Until this is read, the count lever's
value is unknown, not zero.

## 5. What it changes if N = 23 or 24

- Four or five platform episodes do not count, each worth about 2.3 total
  points with the current per-episode quality, so the crossing channel is
  open again and worth up to +9 to +12; which episodes they are (count
  shortfalls on stretch-like streams, or validator refusals late in an
  episode) is what the diagnostic's fraction reading tells.
- The per-episode quality values are 78 / 61 / 61 (cog / placement / soft)
  rather than 65 / 50 / 50: the headroom in the quality terms is smaller
  than the N = 19 reading made it, and the README's example run (placement
  80, soft 100) is within reach of the structure we have.
- The refit's prices per counted episode (soft +4.4 a box) are unchanged in
  form; their N-scaling moves them by 23 / 19.
