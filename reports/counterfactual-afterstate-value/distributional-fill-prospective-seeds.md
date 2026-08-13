# Distributional fill consensus: prospective seed audit

## Frozen contract

- Teacher: schema-v5 `distributional_continuation_labels`
- Axis: `fill_score_proxy` only
- Model: fixed-L2 no-intercept ridge, trained on discovery rows from runs
  `31722131035`, `31720120600`, `31718231518`, and `31722145273`
- Selector: predict only when the packed-only and packed+visible afterstate
  models agree
- Comparison: action-geometry ridge on exactly the covered rows
- Prospective physical targets: original stream, H3/B3, seeds 43, 44, and 45
- Gate fixed before seeds 44/45: consensus wins over action geometry, exact
  two-sided sign-test p < 0.05, and coverage >= 75% in every target run

The two rotation-stream attempts were not evaluated: `31724480463`
(`rotate-000-7`) ended the single-preloaded episode at step 3 and
`31724727147` (`rotate-001-5`) ended it at step 2, so neither produced the
declared mid/late roots for all eight conditions. Their partial condition
artifacts were not used.

## Results

| Seed | Run | Fill rows | Covered | Coverage | Consensus | Action geometry | W/T/L |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 43 | `31724977409` | 57 | 45 | 78.9% | 34/45 | 32/45 | 2/43/0 |
| 44 | `31726615939` | 38 | 26 | 68.4% | 19/26 | 17/26 | 2/24/0 |
| 45 | `31726618901` | 53 | 45 | 84.9% | 39/45 | 28/45 | 15/26/4 |
| **Pooled** | - | **148** | **116** | **78.4%** | **92/116** | **77/116** | **19/93/4** |

The pooled exact two-sided sign-test p-value is `0.00259948`. Pooled covered
accuracy is 79.3% for the consensus and 66.4% for action geometry.

## Verdict

**Prospective directional signal established; preregistered shadow-readiness
gate failed.** The consensus has a statistically reliable covered-row advantage
over action geometry, but seed 44 coverage is below the per-run 75% floor.
Pooled coverage cannot override that failed replication gate. This result
supports a next shadow-policy experiment, not live ranking or an episode-score
improvement claim.

The next experiment must improve or replace the abstention mechanism using
development data, freeze the new rule, and confirm it on new seeds. Seeds
43--45 are now inspected and must not be reused as unopened confirmation data.
