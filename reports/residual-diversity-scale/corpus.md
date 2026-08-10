# Retained replay corpus

**This file is generated.** Rebuild it with `python scripts/index_replay_corpus.py`.

- Runs retained: 1
- Distinct states: **11** across 4 cases
- Rows across all runs: negative_physical_risk 87, paired_random_control 231, positive_transition 231

| run | arm (swap rounds) | verdict | scenarios | states | positive | negative | control |
|---|---:|---|---:|---:|---:|---:|---:|
| `31391424126` | 64 | None | 4 | 11 | 231 | 87 | 231 |

Rows accumulate across runs but distinct states do not: the matrix re-measures the same (case, step) pairs. Rows inside one state share a parent state and are not independent examples. Arms are not merged.
