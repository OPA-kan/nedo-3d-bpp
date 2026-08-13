# Counterfactual afterstate collection audit

- Runs: recovered-b3-source-31672407187, 31672410385, recovered-b3-interleave-31672413055, recovered-b3-rotate0015-31678079848
- Independence gate: **FAIL**

| Split | Directional rows | Unique signatures | Unique fraction | Cross-run duplicate groups | Conflicting signatures |
|---|---:|---:|---:|---:|---:|
| discovery | 104 | 67 | 64.4% | 0 | 0 |
| late | 46 | 21 | 45.7% | 0 | 0 |

> Collection audit only. Different run IDs, serialized rows, or environment seeds are not independent model support when their model-visible afterstate signatures repeat.
