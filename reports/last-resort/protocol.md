# Last-resort relaxation: preregistered development protocol

Committed before any paired episode result is opened. Algorithm:
`docs/LAST_RESORT_RELAXATION.md`. Arm: `last_resort`
(`LAST_RESORT_RELAXATION_SECONDS=2.4`, 0.8 s per clearance rung).

## Matrix

`last-resort-ablation.yml`: arms {base, last_resort} x replicates
{0,1,2} x all seven guard configs (b000-k15/k20/k40, b001-k20/k30,
c000-k1, c001-k1).

## Predeclared gates (development)

Sized against the measured per-config floors in
`reports/benchmarks/baseline.json` (paired 3v3 resolvable 2.2-7.1
placements; sd 0 on b001-k30 and c001-k1).

1. Mechanism: pooled transport_invalid endings strictly lower under
   `last_resort`.
2. Direction: across all case-replicate pairs, placed wins >= losses,
   and pooled placed total strictly higher.
3. No harm: no config's mean placed lower by more than its
   single-episode resolvable (2 sd where sd > 0; one placement where
   sd = 0).
4. Safety composition: pooled topple+slide endings may rise only by as
   much as transport_invalid endings fall (converting a certain death
   into a physical gamble is the design; increasing gambles elsewhere
   is not).

All four must hold to advance. Passing is development evidence only;
adoption additionally requires an independent confirmation on fresh
arrival-order permutations under the same gates. Failing any gate
closes the arm and the result is recorded either way.
