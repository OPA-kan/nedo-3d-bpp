# Probe guard: preregistered behavioral protocol

Committed 2026-08-17 JST before any behavioral episode result is
opened. Licensed by fidelity gates 1-3
(`physics-probe-oracle-real-but-loud`: AUC 0.980, fatal recall 8/10,
1 false alarm in 247 safe steps); the timing footprint that failed
gate 4 is priced here by the null arm instead of assumed away.

## Mechanism (`PHYSICS_PROBE_MODE=guard`, default off)

At each placement-core decision, after all live selection is frozen
(the standard seam):

1. Probe the chosen action with the validated settle clone.
2. If predicted SAFE at the official thresholds (displacement <= 0.3,
   angle <= 30): play it unchanged. Expected on ~95% of steps
   (13 unsafe in 260).
3. If predicted UNSAFE: probe alternatives in shipped-score order
   (retained top-K, then observed legal candidates, deduplicated), up
   to 6 probes or a 1.5 s slice, and play the first alternative that
   predicts safe. If none does, play the incumbent — never refuse,
   never fall through (a wrong guess then costs nothing versus the
   status quo).
4. Trace event per step: probed count, incumbent verdict, swapped,
   alternative verdict, elapsed.

No learned component is involved anywhere in the loop; the trigger
and the substitute check are the same physical oracle.

## Matrix and gates

`physics-probe-fidelity.yml` successor wave: {base, probe_null
(PHYSICS_PROBE_SHADOW log-only — prices the timing footprint),
probe_guard} x 3 replicates x the seven guard configs. All five
standard gates, adjudicated from the rows:

1. Mechanism: pooled topple+slide endings strictly lower under
   probe_guard than base.
2. Direction: pooled placed strictly higher, paired wins >= losses.
3. No harm: no config's mean placed below base by more than its
   baseline.json floor (2 sd, or 1 where sd = 0).
4. Fallback conservation: pooled transport_invalid non-increasing.
5. Null control: probe_null within each config's floor of base on
   mean placed (the timing footprint must not itself account for the
   guard's effect).

An inert guard (zero swaps) closes the arm. Pass licenses the
fresh-permutation confirmation before any default flip. Fail closes
the line with the result recorded; no retuning of thresholds, probe
counts, or slice on these streams.
