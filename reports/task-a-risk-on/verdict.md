# Task A risk-on proposal oracle — rejected

GitHub Actions run `31569837492` compared the shipped risk-off proposal
oracle (`default`) with `OFFLINE_RISK_RERANK=1` on both bundled Task A cases,
three repeats per arm. All 12 physical episodes and aggregation succeeded.

| case | arm | placed mean | fill mean | offline evaluations | optimization s |
|---|---|---:|---:|---:|---:|
| a000 | default | 28.67 | 39.23 | 53.67 | 145.59 |
| a000 | risk_on | 22.67 | 31.88 | 42.00 | 145.11 |
| a001 | default | 19.00 | 25.40 | 91.00 | 148.68 |
| a001 | risk_on | 20.00 | 26.07 | 76.33 | 147.66 |

Risk-on buys one placement on a001 but loses six on a000. The optimization
time is effectively unchanged, while the added per-candidate risk work
reduces the number of complete orders evaluated by about 22% on a000 and 16%
on a001. Matching execution ranking therefore lowers proposal recall under
the fixed Task A budget; fidelity is not free and is not beneficial overall.

Decision: do not adopt. Keep ADR-003's risk-off proposal oracle as shipped.
The flag remains available only to reproduce the comparison.
