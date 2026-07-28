# Lookahead sample-simulator comparison

- Timestamp: `2026-07-28T02:07:54+00:00`
- Git SHA: `327035996047a61fba30d5c10ea1996f087a79c9`
- Config: `/home/runner/work/nedo-3d-bpp/nedo-3d-bpp/simulator/configs/sample_config.json`
- Run ID: `30322018380`
- Scope: bundled simulator proxy; not a SIGNATE leaderboard score

## Mode summary

| mode | process | physics | placed total | mean fill | max policy |
|---|---:|---:|---:|---:|---:|
| weighted | 0 | FAIL | 14 | 9.890238 | 6.572s |
| depth2 | 0 | FAIL | 14 | 9.890238 | 6.573s |
| pool_resilience | 0 | FAIL | 14 | 9.890238 | 6.559s |

## Case history

### weighted

| case | fill | placed | included | valid | safe | optimize | policy |
|---|---:|---:|---:|---:|---:|---:|---:|
| 000 | 11.954776 | 7/41 | True | False | False | 149.401s | 2.901s |
| 001 | 7.825700 | 7/42 | True | False | False | 0.000s | 6.572s |

### depth2

| case | fill | placed | included | valid | safe | optimize | policy |
|---|---:|---:|---:|---:|---:|---:|---:|
| 000 | 11.954776 | 7/41 | True | False | False | 149.606s | 2.945s |
| 001 | 7.825700 | 7/42 | True | False | False | 0.000s | 6.573s |

### pool_resilience

| case | fill | placed | included | valid | safe | optimize | policy |
|---|---:|---:|---:|---:|---:|---:|---:|
| 000 | 11.954776 | 7/41 | True | False | False | 149.309s | 2.906s |
| 001 | 7.825700 | 7/42 | True | False | False | 0.000s | 6.559s |

## Interpretation

At least one mode's physical validity failed. Fill and placed comparisons are diagnostic history, not a valid competition result.
