# Swap acceptance: does refusing a component-degrading swap help?

- Verdict: **gate_wins_consumption_rest_indistinguishable**
- 46 boards, both rules on each; the shipped arm ran pareto_gate
- Shipped arm accepted 166 swaps that raised the sum while a component fell, on 41 boards
- The gate refused 2112 moves; 635 swaps applied by the sum rule against 524 by the gate
- Guard number (the sum the acceptance test reads): minimum 0.035931 under the sum rule against 0.033627 under the gate; boards at or below zero, 0 and 0

| quantity | mean gate − sum | median | gate better | tied | gate worse | sign test p | call |
|---|---:|---:|---:|---:|---:|---:|---|
| the single Gower ΔNN (what the sum rule maximises) | -0.004560 | -0.003212 | 4 | 6 | 36 | 0.0000 | sum_better |
| Δ occupancy | +0.001274 | +0.000533 | 25 | 7 | 14 | 0.1081 | indistinguishable |
| Δ consumption | +0.033687 | +0.029412 | 25 | 15 | 6 | 0.0009 | gate_better |

Both arms run on the same board from the same pool, seed and forced keys, so the difference is the acceptance rule and nothing else. The gate is expected to lose on the first row by construction -- it refuses moves the sum rule would take -- so that row is a check that the arms really differ, not a result. The result is the two component rows.
