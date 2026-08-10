# Retained replay corpus

**This file is generated.** Rebuild it with `python scripts/index_replay_corpus.py`.

- Runs retained: 3
- Distinct states (board fingerprints): **93** across 9 cases and 92 (case, step) slots
- States reached by more than one run: 8
- **Runs holding an unfinished dataset: ['31391424126', '31393167142', '31394891316']** — those rows are labelled correctly but their scenario did not run to the end.
- Rows across all runs: negative_physical_risk 1447, paired_random_control 2142, positive_transition 2161

| run | arm (swap rounds) | verdict | scenarios | states | positive | negative | control |
|---|---:|---|---:|---:|---:|---:|---:|
| `31391424126 (partial)` | 64 | fail | 4 | 11 | 231 | 87 | 231 |
| `31393167142 (partial)` | 64 | pass | 8 | 46 | 972 | 679 | 963 |
| `31394891316 (partial)` | 64 | fail | 8 | 44 | 958 | 681 | 948 |

A state is a board fingerprint, not a (case, step) label: the policy is deadline-limited, so two runs of one scenario reach different boards at the same step index. Re-running the matrix therefore adds states. Rows inside one state share a parent and are not independent examples. Arms are not merged.
