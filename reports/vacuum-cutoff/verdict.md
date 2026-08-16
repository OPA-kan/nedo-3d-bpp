# Vacuum cutoff: development verdict — rejected

Actions run `31941364445` completed all 24 paired episodes and the
aggregate. Evaluated against the four gates preregistered in
`protocol.md` before any result was opened:

| gate | requirement | result | verdict |
|---|---|---|---|
| targeted effect | c000-k1 mean placed strictly higher | 18.33 vs 18.33 (same outcome multiset, order shuffled by runner timing) | FAIL |
| no harm | each control within one placement | b000-k20 −1.00 (boundary), b001-k20 −1.33, **c001-k1 −5.00** (21,21,21 → 16,16,16) | FAIL |
| safety | unsafe endings non-increasing | transport_invalid 5→1 but topple 4→7, slide 3→4 | FAIL |
| paired direction | placed wins ≥ losses | 2 wins / 7 losses | FAIL |

**Do not enable `VACUUM_SETTLED_CUTOFF`. The knob stays registered at
default 0 solely to reproduce this negative result.**

## Why it failed: a classifier is not a controller

The operating point (completion ≥ 1/3 with zero settled candidates,
precision 1.0 on the oracle corpus) was measured as a *post-hoc
classifier over finished searches*. Turning it into an in-flight
early-stop rule changed its semantics: firing at one-third completion
abandons the remaining two-thirds of settled units, and on c001-k1 those
units held the settled placements the shipped policy was finding — the
freed deadline bought an earlier, toppling release instead (all three
replicates: 21 placed via late transport_invalid became 16 via topple).
The false-fire cost of an early-stopping rule is invisible to classifier
metrics computed on completed scans. Note also that full settled
exhaustion — the sound trigger this rule approximates — is already
handled by the shipped `anchor_fallback` path, so the exploitable gap
this mechanism assumed may not exist at all.

The one predicted effect that did appear: transport_invalid endings fell
from 5 to 1 and the bundled valid rate rose 0.583 → 0.917, confirming
the reallocation does buy release quality — but at the cost of abandoning
live settled placements, which is the wrong exchange everywhere it fired.

## What carries forward

- The four-phase structure and the true-empty classifier remain valid as
  *measurement* instruments; their misuse as a stopping rule is what
  failed.
- Any future in-flight regime controller must be gated on a criterion
  whose false-fire cost is measured in-flight, not inherited from a
  post-hoc classifier — and must include this experiment's paired
  no-harm controls from the start.
