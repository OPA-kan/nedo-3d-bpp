# Last-resort relaxation: confirmation FAILED — not adopted

Fresh-permutation run `31947832632` (six never-before-used seed-20260816
k20 streams x both arms x two replicates) against the five gates
preregistered before any result was opened:

| gate | requirement | result | verdict |
|---|---|---|---|
| 1 | pooled placed strictly higher | 200 vs 206 | **FAIL** |
| 2 | paired wins >= losses | 2W/2L | pass |
| 3 | transport_invalid non-increasing | 6 -> 5 | pass |
| 4 | gamble conservation | +1 vs -1 | pass |
| 5 | no stream below -3 | worst -3.0 | pass |

Per the protocol: `LAST_RESORT_RELAXATION_SECONDS` stays at default 0,
the arm is closed, and nothing is retuned on these streams.

## What the fresh streams actually showed

On four of six streams the two arms produced bit-identical trajectories
— the rescue never fired, confirming the mechanism is inert outside the
zero-accepted regime. One stream swapped outcomes across replicates
(runner-timing divergence, tied means). The entire pooled deficit is one
replicate of `syn001-per02-k20` (base 19/19; last_resort 12/20): a
single early-topple trajectory draw. The k1 fatal-case gains from the
development run (c001-k1 breaking its certified 21-ceiling to 22 in all
replicates) are real but did not transfer as a pooled improvement on
multi-item k20 streams, where fallback deaths are rarer and later.

## Disposition

The mechanism survives as a documented, measured, default-off
capability: `docs/LAST_RESORT_RELAXATION.md` holds the algorithm, this
directory holds both preregistered experiments, and the knob reproduces
them. The honest summary for a future attempt: the expected-value
argument is sound and the dev gates passed, but the opportunity mass on
ordinary streams is too small for the current gates; a targeted variant
(fire only on pool-1 / late boards, or pair with a better rescue
ranking) would need its own preregistration. The protocol-fallback open
question is now closed in the ledger: a switchable fallback policy
exists and was measured at episode level, and the fixed fallback
remains the shipped default by measurement, not by neglect.
