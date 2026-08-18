# Stack-aware soft coverage: Stage 1 reach

Protocol: `reports/hazard/soft-stack-protocol.md`. The four measurements and the entry gate were fixed before this wave ran. Log-only: the shadow records both readings and selects on neither.

- multi-candidate decisions observed: 273

| measurement | hits | fraction |
|---|---:|---:|
| R1 some candidate better on stack-aware soft | 6/273 | 2.2% |
| **R2 dominance-eligible on stack-aware soft** | 0/273 | 0.0% |
| R3 dominance-eligible on stack-aware priority | 0/273 | 0.0% |
| R4 control: dominance-eligible on CONTACT soft | 0/273 | 0.0% |
| R4 control: dominance-eligible on CONTACT priority | 0/273 | 0.0% |

## Entry gate: R2 >= 5% -- **FAIL**

Stage 2 is NOT built. The rule cannot reach the gate fraction of decisions, so an arm would spend a wave to reproduce the attribute filter's inert verdict. The line closes as measured-inert-with-a-reason and the shadow columns stay as telemetry.

## Why the reach is what it is

A tie-break can only act where the retained set DIFFERS on the axis it reads. These numbers carry no threshold; they say whether a null result is about the predicate or about the intervention point.

- decisions where retained candidates differ on stack-aware soft violations: **8/273** (2.9%)
- decisions where they differ under the shipped contact reading: 6/273
- decisions where ANY retained candidate has a stack-aware violation at all: 64/273
- distinct items in the retained set, by count: `{1: 173, 2: 47, 3: 53}`

Retention is by score, and the top-scoring poses of one item are near-duplicates, so a retained set concentrated on one item cannot differ on any attribute axis. Where that is what the numbers show, the finding is that selection is the wrong intervention point -- the lever is candidate retention diversity -- and no predicate fix reaches it.

## Reading the control

R4 is the shipped contact reading, and it is 0.0%. A near-zero value is the direct confirmation that the attribute filter's 0-of-16 result was mechanically guaranteed rather than informative. A large value would mean the inert verdict, not this line, is what needs revisiting.
