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
31351112589 was used only as a coarse performance diagnostic. It did not
collect a complete official-proxy vector, and its placed/fill values are
therefore **not** an algorithm-adoption result. Separate wall-clock runners
are also too noisy to establish exact parity.

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

No selector may be adopted from placed/fill alone. The paired physical report
must retain the full observable vector: placed and fill; final CoM height;
shake shifted fraction, topples, maximum displacement and peak kinetic energy;
priority-clean and soft-clean ratios; terminal inclusion/valid/safe state and
failure channel; and policy time/attempt coverage. These are Pareto and
dominance signals. They must not be collapsed into a fabricated total because
the official component normalizations and weights are unpublished.
