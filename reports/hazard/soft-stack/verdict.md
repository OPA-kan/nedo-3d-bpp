# Stack-aware soft coverage, Stage 1: gate FAILS, and it fails robustly

Protocol: `reports/hazard/soft-stack-protocol.md`, frozen before the
wave. Measurements: `reports/hazard/soft-stack/reach.{json,md}`. Data:
14 episodes, 7 development configs x 2 replicates,
`MULTI_AXIS_SELECTOR_MODE=shadow`, 14/14 complete, zero harness
failures, 273 decisions with more than one retained candidate.

## Result

| measurement | hits | fraction |
|---|---:|---:|
| R1 some retained candidate better on stack-aware soft | 6/273 | 2.2% |
| **R2 dominance-eligible on stack-aware soft** | 0/273 | **0.0%** |
| R3 dominance-eligible on stack-aware priority | 0/273 | 0.0% |
| R4 control: dominance-eligible on CONTACT soft | 0/273 | 0.0% |
| R4 control: dominance-eligible on CONTACT priority | 0/273 | 0.0% |

**Entry gate R2 >= 5%: FAIL.** Stage 2 is not built. The dominance
tie-break is not implemented, the knob does not exist, and no wave is
spent reproducing the attribute filter's inert verdict.

## Why it fails, which is the part worth keeping

Two independent causes stack, and they point the same way.

### 1. The retained set almost never differs on the axis

- decisions where retained candidates differ on stack-aware soft
  violations: **8/273 (2.9%)**
- decisions where any retained candidate carries a stack-aware
  violation at all: 64/273
- distinct items in the retained set: 1 item on **173/273** decisions,
  2 on 47, 3 on 53

So violations are common -- a quarter of decisions have one somewhere --
but the retained candidates share them. Retention is by score, and the
top-scoring poses of a single item are near-duplicates with the same
attribute footprint. A selector cannot choose what retention never
offers it.

### 2. Where a better alternative exists, dominance excludes it -- barely

All six R1 decisions:

| episode | step | chosen | alternative | score delta |
|---|---:|---|---|---:|
| `b001-k30-…-r1` | 17 | 2 violations @ -1.4462 | 0 @ -1.4713 | -0.0251 |
| `b001-k30-…-r1` | 18 | 2 @ -1.6341 | 0 @ -2.5304 | -0.8963 |
| `c000-k1-…-r0` | 20 | 2 @ -1.8121 | 0 @ -1.8172 | -0.0052 |
| `c000-k1-…-r1` | 20 | 2 @ -1.8121 | 0 @ -1.8172 | -0.0052 |
| `c001-k1-…-r0` | 18 | 3 @ -1.2652 | 1 @ -1.2683 | -0.0031 |
| `c001-k1-…-r1` | 18 | 3 @ -1.2652 | 1 @ -1.2683 | -0.0031 |

In five of six the concession is 0.003 to 0.025 on a score of order
1.5, that is a fraction of a percent, to remove two or three violations
outright. The dominance restriction -- the thing that made the design
safe, because selling placed for soft becomes impossible by
construction -- is exactly what makes it inert here.

That tension is the finding, and it is not fixable by widening the
band: **even R1, which ignores score entirely and is therefore the most
generous rule anyone could write on this data, reaches 2.2%.** The gate
fails under every variant available on these decisions, so the verdict
is robust rather than knife-edge. No epsilon is introduced and none is
tested on this stream; that would be retuning on an adjudicated one.

## What the control establishes

R4, the shipped contact reading, is 0.0% -- and 6/273 for mere spread.
This is the direct confirmation that the preregistered attribute
filter's 0-of-16 result was mechanically guaranteed rather than
informative: the predicate it read cannot separate the candidates it
was given.

## Where the lever actually is

Not in selection. 64 of 273 decisions place something over a soft item
while every retained alternative does the same, so the non-covering
placement is either never generated or never retained. The lever is
candidate generation and retention diversity, and no predicate fix
reaches it.

Stating that is not the same as licensing it. Any such work needs its
own preregistration, and it inherits two closed negatives that bear
directly on it: `release attribute hard reject` (closed on placed cost)
and `item-cap 16 / late cap 20` (widening what the agent considers was
measured and did not survive fresh permutations).

## What stays

The stack-aware reading stays in `candidate_attribute_violations`,
default off and logged beside the shipped one, because it is the only
way this measurement can be repeated. `behaviour_sha256` and
`component_sha256` are unmoved, no default changed, `simulator/`
untouched.
