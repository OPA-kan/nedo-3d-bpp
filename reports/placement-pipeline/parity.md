# Structured placement pipeline parity

Date: 2026-08-10

## Why this exists

The temporal-delay experiment is retained as a useful negative result: delayed
greedy proposals survived static validation, but did not agree on an action or
even on an item. That result exposed an integration problem as well as a
policy result. Candidate generation, scalar ranking, settled/release choice,
and command construction were fused inside `PlacementCore`, so a richer
selector either had to repeat search or reconstruct facts after the scalar had
discarded them.

The new contract separates proposal facts, named evaluation terms, selection,
and the external command. It does **not** change the default Ranker or adopt a
temporal policy.

## Performance guard

The first implementation eagerly built the rich objects for every valid
candidate. In Task B run 31350300314 this lowered observed candidate
throughput by about 16--17% relative to control run 31350298808. The eager
design was rejected.

The final implementation makes rich evaluation opt-in. With no custom
selector, `choose()` and `top_candidates()` execute the former scalar loop
verbatim. Linux CPU verification was green at run 31351104085. Task B run
31351112589 found no catastrophic placed-count regression, but separate
wall-clock runners are too noisy to establish exact parity.

## Deterministic fixed-work comparison

`scripts/check_placement_pipeline_parity.py` imports the pre-refactor agent and
the candidate agent side by side, supplies the same synthetic state, and runs
both under identical attempt budgets. Timing is reported but excluded from
the equality predicate.

At budgets 128 and 512, all of the following matched exactly:

- consumed attempts for `choose()` and `top_candidates()`;
- selected command and the ordered top-three commands;
- candidate center, size, orientation, mode, and item/container identities;
- every scalar score, compared through `float.hex()`.

Result: `all_match=true`. The raw local record is intentionally ignored under
`reports/raw/pipeline-parity/fixed-work.json`; this compact report is the
shared artifact.

## Adoption boundary

The architecture is accepted as infrastructure. Default execution remains on
the old allocation-light scalar path. Rollout, delayed-ensemble, learned, or
constraint-aware policies must enter through an explicit selector and be
evaluated independently in shadow and paired physical runs.
