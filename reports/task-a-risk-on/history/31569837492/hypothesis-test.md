# Task A risk-on proposal oracle: exact hypothesis test

Source: `reports\task-a-risk-on\history\31569837492\rows.jsonl`

The 12 episodes were independent GitHub Actions matrix jobs. Repeat IDs are labels, not matched pairs, so this analysis uses an **unpaired exact permutation test within each case**. The primary estimand is the equal-case mean change in placed count (`risk_on - default`).

## Primary result

- Equal-case placed delta: **-2.5**
- Exact one-sided p for improvement: **0.9525**
- Exact one-sided p for harm: **0.05**
- Exact two-sided p: **0.1**
- Stratified label allocations enumerated: 400

There is no evidence that risk-on improves placed count. The observed effect is negative, and the prespecified no-regression adoption gate fails because a000 loses six placements. **Decision: do not adopt risk-on.**

## Case results

| Case | Metric | Default mean | Risk-on mean | Delta | p improve | p harm | p two-sided |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| a000 | placed | 28.6667 | 22.6667 | -6 | 1 | 0.05 | 0.1 |
| a000 | fill | 39.2291 | 31.8775 | -7.35155 | 1 | 0.05 | 0.1 |
| a000 | offline evals | 53.6667 | 42 | -11.6667 | 1 | 0.05 | 0.1 |
| a000 | optimization s | 145.595 | 145.115 | -0.479798 | 0.75 | 0.3 | 0.6 |
| a001 | placed | 19 | 20 | 1 | 0.05 | 1 | 0.1 |
| a001 | fill | 25.4033 | 26.0727 | 0.669433 | 0.05 | 1 | 0.1 |
| a001 | offline evals | 91 | 76.3333 | -14.6667 | 1 | 0.05 | 0.1 |
| a001 | optimization s | 148.682 | 147.658 | -1.02398 | 1 | 0.05 | 0.1 |

## Resolution and interpretation

With three observations per arm, there are only `C(6,3) = 20` label allocations. Therefore the smallest attainable one-sided p is 0.05 and the smallest two-sided p without ties is 0.1. Complete separation can only reach p=0.10 two-sided. Four observations per arm would lower that theoretical two-sided floor to `2/C(8,4) = 0.0286`.

The a000 harm and a001 benefit each sit at the one-sided resolution boundary (p=0.05), but neither is two-sided significant, and separate casewise claims would also require multiplicity control. The defensible conclusion is not that every possible risk-on policy is disproven: this specific F8 proposal oracle has no global benefit signal, has a large practical regression on a000, and fails its adoption gate.

The p-values are exact for exchangeable labels within each case. They do not justify generalization beyond these two bundled Task A cases.
