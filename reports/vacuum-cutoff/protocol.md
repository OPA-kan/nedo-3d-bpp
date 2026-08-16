# Vacuum cutoff: preregistered development protocol

Committed before any paired episode result is opened.

## Mechanism

`VACUUM_SETTLED_CUTOFF` (default 0, off) arms a feasibility-phase
reallocation inside the live scan: when the fraction of settled scan units
exhausted without a single settled candidate reaches the threshold, the
remaining settled units are skipped and the rest of the deadline goes to
release units. The evidence basis is the four-phase study in
`reports/anchor-recall/phase-structure.md`: a truly empty settled phase
lets the scan finish (the candidate space implodes near the collapse),
while drowning states never complete a third of their units, so
"zero settled accepted + completion >= 1/3" called true-empty at precision
1.0 and recall 7/8 on the raw oracle states. At the certified-empty boards
460-1014 physically safe releases existed, and the recorded c000-k1 death
is a release that toppled while safe alternatives existed — release choice
quality is what the freed deadline buys.

The ablation arm `vacuum_cutoff` sets the threshold to the measured
operating point 0.34. The default path is byte-identical to the shipped
agent (`behaviour_sha256` unchanged; only `component_sha256` moved, which
is the registration effect).

## Matrix

`vacuum-cutoff-ablation.yml`: arms {base, vacuum_cutoff} x replicates
{0,1,2} x cases {c000-k1, c001-k1, b000-k20, b001-k20}. The c-cases are
the targeted fatal regime; the b-cases are no-harm controls where the
cutoff should rarely or never fire.

## Predeclared gates (development)

1. Targeted effect: mean placed on c000-k1 strictly higher under
   `vacuum_cutoff` across the three replicates.
2. No harm: on each of c001-k1, b000-k20 and b001-k20, mean placed under
   `vacuum_cutoff` within one placement of base.
3. Safety: pooled unsafe/fallback-ending counts non-increasing.
4. Paired direction: across all case-replicate pairs, placed wins >=
   losses.

All four must hold to advance. Passing is development evidence only; any
adoption additionally requires an independent confirmation on fresh
arrival-order permutations under the same gates, per the late-item-cap
precedent. Failing any gate closes the arm and the result is recorded
either way.
