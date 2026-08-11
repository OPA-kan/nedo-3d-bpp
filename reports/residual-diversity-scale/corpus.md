# Retained replay corpus

**This file is generated.** Rebuild it with `python scripts/index_replay_corpus.py`.

- Runs retained: 19
- Size: 404 MB raw, about 27 MB stored
- Distinct states (board fingerprints): **189** across 9 cases and 96 (case, step) slots
- States reached by more than one run: 100
- **Runs holding an unfinished dataset: ['31391424126', '31393167142', '31394891316', '31494103024']** — those rows are labelled correctly but their scenario did not run to the end.
- Rows across all runs: negative_physical_risk 10361, paired_random_control 17423, positive_transition 17534

| run | arm (swap rounds) | verdict | scenarios | states | positive | negative | control |
|---|---:|---|---:|---:|---:|---:|---:|
| `31391424126 (partial)` | 64 | fail | 4 | 11 | 231 | 87 | 231 |
| `31393167142 (partial)` | 64 | pass | 8 | 46 | 972 | 679 | 963 |
| `31394891316 (partial)` | 64 | fail | 8 | 44 | 958 | 681 | 948 |
| `31447660500` | 64 | pass | 8 | 40 | 816 | 540 | 814 |
| `31450172632` | 64 | pass | 8 | 45 | 980 | 634 | 970 |
| `31464662520` | 64 | pass | 8 | 46 | 1001 | 670 | 995 |
| `31466807165` | 64 | pass | 8 | 41 | 899 | 465 | 893 |
| `31475060002` | 64 | pass | 8 | 44 | 944 | 542 | 937 |
| `31476716531` | 64 | fail | 8 | 46 | 984 | 619 | 975 |
| `31478264881` | 64 | pass | 8 | 45 | 948 | 511 | 940 |
| `31484299493` | 64 | pass | 8 | 46 | 1056 | 571 | 1052 |
| `31485721899` | 64 | pass | 8 | 46 | 1002 | 561 | 995 |
| `31487974469` | 64 | pass | 8 | 45 | 1006 | 586 | 1002 |
| `31490095025` | 64 | pass | 8 | 44 | 954 | 597 | 944 |
| `31490380791` | 64 | pass | 8 | 41 | 867 | 389 | 865 |
| `31491047020` | 64 | pass | 8 | 44 | 951 | 579 | 948 |
| `31492719115` | 64 | pass | 8 | 46 | 985 | 548 | 981 |
| `31494103024 (partial)` | 64 | pass | 8 | 46 | 974 | 556 | 967 |
| `31494206763` | 64 | pass | 8 | 45 | 1006 | 546 | 1003 |

A state is a board fingerprint, not a (case, step) label: the policy is deadline-limited, so two runs of one scenario reach different boards at the same step index. Re-running the matrix therefore adds states. Rows inside one state share a parent and are not independent examples. Arms are not merged.
