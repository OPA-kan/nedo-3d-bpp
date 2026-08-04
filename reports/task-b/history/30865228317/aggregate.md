## Task B screening aggregate

| Pool | Selection | Coverage | Risk gate | Runs | Placed mean/median/std | Placed min-max | Fill mean/median/std | C1/C2/C3 mean | Failure modes | Starvation signals |
| ---: | --- | --- | --- | ---: | --- | --- | --- | --- | --- | ---: |
| 10 | weighted | class_aware | off | 3 | 18.00/18.00/0.00 | 18-18 | 21.380/21.380/0.000 | 100.0%/100.0%/60.7% | unsafe_protocol_fallback=3 | 0 |
| 20 | weighted | class_aware | off | 3 | 19.33/19.00/0.58 | 19-20 | 25.119/25.115/1.812 | 50.0%/100.0%/58.7% | release_failure=1, unsafe_protocol_fallback=2 | 1 |
| 40 | weighted | class_aware | off | 3 | 20.00/20.00/0.00 | 20-20 | 23.546/23.546/0.000 | 32.5%/100.0%/60.5% | unsafe_protocol_fallback=3 | 0 |

### Class coverage means

| Pool | Class | C1 | C2 | C3 |
| ---: | --- | ---: | ---: | ---: |
| 10 | normal | 100.0% | 100.0% | 72.5% |
| 10 | soft | 100.0% | 100.0% | 48.0% |
| 10 | priority | 100.0% | 100.0% | 0.0% |
| 20 | normal | 59.5% | 100.0% | 54.4% |
| 20 | soft | 22.1% | 100.0% | 93.4% |
| 20 | priority | 100.0% | 100.0% | 100.0% |
| 40 | normal | 34.9% | 100.0% | 57.1% |
| 40 | soft | 21.8% | 100.0% | 96.5% |
| 40 | priority | 81.2% | 100.0% | 100.0% |

### Release risk means

| Pool | Risk gate | Static | Gate pass | Pass rate | Gate reject | All rejected | All-reject rate | Protocol fallback | Evaluated | Enforced | Selected | >30° | Large displacement | Physical failure | Gate-pass failures | Shadow reject but safe |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 10 | off | 10651.0 | 0.0 | - | 0.0 | 0.0 | 0.0% | 1.0 | 0.0 | 0.0 | 8.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| 20 | off | 10464.3 | 0.0 | - | 0.0 | 0.0 | 0.0% | 0.7 | 0.0 | 0.0 | 12.3 | 0.7 | 0.7 | 0.3 | 0.0 | 0.0 |
| 40 | off | 11762.7 | 0.0 | - | 0.0 | 0.0 | 0.0% | 1.0 | 0.0 | 0.0 | 11.0 | 0.0 | 1.0 | 0.0 | 0.0 | 0.0 |

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
| 10 | off | 8.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| 20 | off | 12.3 | 0.7 | 0.7 | 0.3 | 0.3 | 0.0 | 0.0 | 1.0 |
| 40 | off | 11.0 | 0.0 | 1.0 | 0.0 | 0.0 | 0.0 | 0.0 | 1.0 |

### Off/shadow action-sequence invariant

| Pool | Comparable replicates | Exact matches | Blocker |
| ---: | ---: | ---: | --- |
