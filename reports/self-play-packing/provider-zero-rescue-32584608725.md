# Provider-zero rescue benchmark

- unique boards: 49
- represented exhausted nodes: 109
- baseline provider empty on every replay: True

| strategy | rescued boards | board recall | node-weighted recall | rank-0 safe | lazy checks | clean safe rate | safe candidates | mean generation s | mean physics-filter s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| stride4 | 49/49 | 1.000 | 1.000 | 49/49 | 49 | 0.424 | 1401 | 3.350 | 22.412 |
| stride16 | 49/49 | 1.000 | 1.000 | 49/49 | 49 | 0.720 | 1394 | 3.812 | 22.756 |
| deep4x | 49/49 | 1.000 | 1.000 | 49/49 | 49 | 0.582 | 1409 | 13.407 | 22.425 |
| deep16x | 49/49 | 1.000 | 1.000 | 49/49 | 49 | 0.900 | 1473 | 49.712 | 22.741 |

> This is a stratified provider-zero capability sample. Recall is not an on-policy score gain, and soft/priority heads are reported separately rather than collapsed into a local exchange rate.
