# Retained replay corpus

**This file is generated.** Rebuild it with `python scripts/index_replay_corpus.py`.

- Runs retained: 10
- Size: 202 MB raw, about 14 MB stored
- Distinct states (board fingerprints): **163** across 9 cases and 96 (case, step) slots
- States reached by more than one run: 73
- **Runs holding an unfinished dataset: ['31391424126', '31393167142', '31394891316']** — those rows are labelled correctly but their scenario did not run to the end.
- Rows across all runs: negative_physical_risk 5428, paired_random_control 8666, positive_transition 8733

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

A state is a board fingerprint, not a (case, step) label: the policy is deadline-limited, so two runs of one scenario reach different boards at the same step index. Re-running the matrix therefore adds states. Rows inside one state share a parent and are not independent examples. Arms are not merged.
