# Provider-zero rescue capability protocol

Frozen from physical-PUCT run `32572648489`. This is a candidate-support
experiment, not a live-policy comparison and not an official-score gate.

## Population

The deep reference contains 1,169 exhausted nodes where the unchanged
provider emitted zero proposals even when asked for width 64. They collapse to
521 unique physical board fingerprints:

| scenario | nodes | unique boards |
|---|---:|---:|
| dual-preloaded-dedicated | 253 | 149 |
| dual-shelf-mixed | 44 | 27 |
| single-empty-noshelf | 244 | 97 |
| single-empty-shelf | 628 | 248 |

The durable corpus is
`provider-zero-corpus-32572648489.json`. A benchmark run deterministically
samples up to eight unique boards from each `scenario x effective-step-band`
stratum using seed `20260823`, yielding 49 boards across seven populated
strata. Node occurrence counts remain attached, so results report both
board-weighted and occurrence-weighted recall without treating transpositions
as independent states.

## Frozen rescue strategies

All strategies scan every visible item and retain at most 64 distinct-item
proposals. The original attempt budget is read from each source manifest
(`stride=1`, 128 attempts per item in this corpus) and must reproduce zero
proposals before a board is evaluated.

| strategy | attempts/item | anchor stride | hypothesis |
|---|---:|---:|---|
| `deep4x` | 512 | 1 | modest extra attempts recover the existing order |
| `deep16x` | 2,048 | 1 | a much deeper ceiling is still useful |
| `stride4` | 128 | 4 | equal-budget spatial coverage beats the natural prefix |
| `stride16` | 128 | 16 | equal-budget coarse global coverage is required |

Every proposal is replayed in an independent PyBullet environment. A rescue
counts only if `is_included`, `is_valid`, and `is_placed_safe` are all true.
The benchmark also saves proposal/filter time and separate direct/stack-aware
soft coverage, direct/stack-aware priority coverage, and priority-routing
heads. These heads are not collapsed into a hand-chosen exchange rate.

## Readout

Primary KPI:

\[
R_{provider}=P(\exists\text{ physically safe rescue}\mid
\text{old provider}=0)
\]

Report the unique-board point estimate and Wilson 95% interval. Also report
node-occurrence-weighted recall, scenario breakdown, safe-candidate count and
mean generation/physics-filter cost.

- A point estimate at or above 20% is a promising provider-support result,
  not a license to change the policy.
- If a deep arm wins, the first defect is attempt starvation.
- If a strided arm wins at the same 128-attempt budget, the first defect is
  spatial prefix coverage.
- If all three are near zero, stop increasing K/attempts and test a new
  proposal family, including learned or continuous action proposals.

Any winning rescue must next be confirmed on an independently collected state
distribution and then evaluated through search/trajectory outcome. Recall on
this targeted capability sample alone cannot establish score improvement.
