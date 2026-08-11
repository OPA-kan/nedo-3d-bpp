# Swap acceptance: does refusing a component-degrading swap help?

- Verdict: **gate_wins_consumption_rest_indistinguishable**
- 44 boards, both arms on each
- Shipped arm accepted 171 swaps that raised the sum while a component fell, on 40 boards
- The gate refused 2062 moves; 605 swaps applied by the sum rule against 490 by the gate
- Guard number (the sum the acceptance test reads): minimum 0.035931 under the sum rule against 0.030851 under the gate; boards at or below zero, 0 and 0

| quantity | mean gate − sum | median | gate better | tied | gate worse | sign test p | call |
|---|---:|---:|---:|---:|---:|---:|---|
| the single Gower ΔNN (what the sum rule maximises) | -0.005548 | -0.004107 | 2 | 6 | 36 | 0.0000 | sum_better |
| Δ occupancy | +0.001921 | +0.000527 | 24 | 7 | 13 | 0.0989 | indistinguishable |
| Δ consumption | +0.029919 | +0.031373 | 25 | 15 | 4 | 0.0001 | gate_better |

Both arms run on the same board from the same pool, seed and forced keys, so the difference is the acceptance rule and nothing else. The gate is expected to lose on the first row by construction -- it refuses moves the sum rule would take -- so that row is a check that the arms really differ, not a result. The result is the two component rows.
