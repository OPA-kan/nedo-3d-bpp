# Retained replay corpus

**This file is generated.** Rebuild it with `python scripts/index_replay_corpus.py`.

- Runs retained: 1
- Distinct states (board fingerprints): **11** across 4 cases and 11 (case, step) slots
- States reached by more than one run: 0
- **Runs holding an unfinished dataset: ['31391424126']** — those rows are labelled correctly but their scenario did not run to the end.
- Rows across all runs: negative_physical_risk 87, paired_random_control 231, positive_transition 231

| run | arm (swap rounds) | verdict | scenarios | states | positive | negative | control |
|---|---:|---|---:|---:|---:|---:|---:|
| `31391424126 (partial)` | 64 | fail | 4 | 11 | 231 | 87 | 231 |

A state is a board fingerprint, not a (case, step) label: the policy is deadline-limited, so two runs of one scenario reach different boards at the same step index. Re-running the matrix therefore adds states. Rows inside one state share a parent and are not independent examples. Arms are not merged.
