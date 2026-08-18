# Rule-faithful attribute support: development adjudication

Protocol: `reports/hazard/attribute-support-protocol.md`, which discloses that it was written after the wave launched and takes every placed threshold from `reports/benchmarks/baseline.json` rather than choosing one.

## Per config (paired, same run)

| config | base placed | rule placed | delta | floor | verdict | base fill | rule fill |
|---|---:|---:|---:|---:|---|---:|---:|
| `b000-k15` | 19.00 | 21.00 | +2.00 | 5.23 | inside_floor | 21.74 | 28.39 |
| `b000-k20` | 20.67 | 27.00 | +6.33 | 2.23 | clears | 18.24 | 20.25 |
| `b000-k40` | 17.00 | 19.33 | +2.33 | 3.93 | inside_floor | 19.84 | 22.80 |
| `b001-k20` | 20.33 | 20.33 | +0.00 | 4.22 | inside_floor | 23.73 | 23.73 |
| `b001-k30` | 19.00 | 19.00 | +0.00 | - | no_floor | 27.35 | 27.35 |
| `c000-k1` | 23.00 | 22.00 | -1.00 | 7.10 | inside_floor | 26.10 | 22.45 |
| `c001-k1` | 21.00 | 21.00 | +0.00 | - | no_floor | 25.37 | 25.37 |

## Pooled

| quantity | base | attr_support_rule |
|---|---:|---:|
| episodes | 21 | 21 |
| placed total | 420 | 449 |
| soft violations per placed item | 0.0143 | 0.0178 |
| priority violations per placed item | 0.0286 | 0.0334 |
| shake max shift | 0.1803 | 0.2541 |
| shake peak kinetic energy | 19.34 | 14.34 |
| physical ending rate | 38.1% | 0.0% |

## Gates

| gate | result |
|---|---|
| P placed, >= 3 configs clearing their own floor, none breaching | 1 clearing, 0 breaching -> **fail** |
| A violations per placed item do not rise | **fail** |
| S shake shift and peak energy do not worsen | **fail** |
| C physical endings fall (mechanism) | pass |

## Development verdict: **FAIL**

Not adopted. The failing gate is the finding; no threshold moves and no arm is retuned on this stream.
