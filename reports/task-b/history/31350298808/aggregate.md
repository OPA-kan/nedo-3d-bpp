## Task B screening aggregate

| Pool | Selection | Coverage | Risk gate | Runs | Placed mean/median/std | Placed min-max | Fill mean/median/std | C1/C2/C3 mean | Failure modes | Starvation signals |
| ---: | --- | --- | --- | ---: | --- | --- | --- | --- | --- | ---: |
| 10 | weighted | class_aware | off | 3 | 16.00/16.00/0.00 | 16-16 | 20.268/20.268/0.000 | 100.0%/100.0%/67.3% | release_failure=3 | 0 |
| 20 | weighted | class_aware | off | 3 | 15.00/15.00/0.00 | 15-15 | 12.696/12.696/0.000 | 50.0%/100.0%/66.9% | release_failure=3 | 0 |
| 40 | weighted | class_aware | off | 3 | 17.67/17.00/1.15 | 17-19 | 23.059/20.914/3.717 | 31.1%/100.0%/62.9% | release_failure=2, unsafe_protocol_fallback=1 | 1 |

### Class coverage means

| Pool | Class | C1 | C2 | C3 |
| ---: | --- | ---: | ---: | ---: |
| 10 | normal | 100.0% | 100.0% | 80.1% |
| 10 | soft | 100.0% | 100.0% | 53.5% |
| 10 | priority | 100.0% | 100.0% | 0.0% |
| 20 | normal | 58.6% | 100.0% | 62.6% |
| 20 | soft | 22.3% | 100.0% | 100.0% |
| 20 | priority | 100.0% | 100.0% | 100.0% |
| 40 | normal | 36.4% | 100.0% | 59.1% |
| 40 | soft | 12.8% | 100.0% | 94.6% |
| 40 | priority | 81.2% | 100.0% | 100.0% |

### Release risk means

| Pool | Risk gate | Static | Gate pass | Pass rate | Gate reject | All rejected | All-reject rate | Protocol fallback | Evaluated | Enforced | Selected | >30° | Large displacement | Physical failure | Gate-pass failures | Shadow reject but safe |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 10 | off | 12011.0 | 0.0 | - | 0.0 | 0.0 | 0.0% | 0.0 | 0.0 | 0.0 | 8.0 | 1.0 | 1.0 | 1.0 | 0.0 | 0.0 |
| 20 | off | 15167.7 | 0.0 | - | 0.0 | 0.0 | 0.0% | 0.0 | 0.0 | 0.0 | 7.0 | 1.0 | 2.0 | 1.0 | 0.0 | 0.0 |
| 40 | off | 13174.7 | 0.0 | - | 0.0 | 0.0 | 0.0% | 0.3 | 0.0 | 0.0 | 9.3 | 0.7 | 0.7 | 0.7 | 0.0 | 0.0 |

### Selected-release confusion matrix means

Means over release candidates the ranking actually selected. They are conditioned on that selection and are **not** the gate's overall precision/recall: the selected set is the top of the ranking, not a sample of all candidates. In `enforce` the reject cells are empty by construction. Estimating gate-wide behaviour needs the stratified counterfactual replay dataset, not more runs of this benchmark.

| Pool | Risk gate | Scored | TN pass/safe | FN pass/failed | FP reject/safe | TP reject/failed | Reject failure rate |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 10 | off | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | - |
| 20 | off | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | - |
| 40 | off | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | - |

### Selected-release physical label means

Independent outcomes. `Dangerous` is the historical OR of rotation, 3D displacement and not-placed-safe, kept only for continuity with earlier runs.

| Pool | Risk gate | Labelled | Rotated >30° | Displaced 3D | Displaced XY | Not placed safe | Not valid | Not included | Dangerous |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 10 | off | 8.0 | 1.0 | 1.0 | 1.0 | 1.0 | 0.0 | 0.0 | 1.0 |
| 20 | off | 7.0 | 1.0 | 2.0 | 0.0 | 1.0 | 0.0 | 0.0 | 2.0 |
| 40 | off | 9.3 | 0.7 | 0.7 | 0.7 | 0.7 | 0.0 | 0.0 | 0.7 |

### Off/shadow action-sequence invariant

| Pool | Comparable replicates | Exact matches | Blocker |
| ---: | ---: | ---: | --- |
