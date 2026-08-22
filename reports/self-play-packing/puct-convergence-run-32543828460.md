# Targeted physical-PUCT convergence — run 32543828460

Status: completed; the 58 roots are retained as a hard-root benchmark, but the
current bounded-search Q/visit targets are not teacher-ready.

- source Self-Play matrix: Actions `32515349437`
- targeted convergence run: Actions `32543828460`
- implementation commits: `1e270c0`, `d0e2ea3`, `46d1384`
- physical result: all eight shards and the aggregate job succeeded
- elapsed wall time: 2026-08-22 01:34:28Z to 03:55:23Z (2 h 21 min)

## Question and frozen measurement contract

The source matrix contained 58 raw roots where the original H2/S12 physical
PUCT assigned different Q values to visited candidates. They represent 36
unique model-visible/game-state signatures; raw roots are retained because
their replay streams and candidate IDs are trajectory-local, while uniqueness
is reported separately.

Every rerun reconstructed the exact saved root and reused its exact root
candidate set. Measurement searches used the original uniform prior and
`cpuct=2.0`, with root Dirichlet noise disabled. The schedule was:

1. H2/S12 twice with the same seed as a determinism control;
2. H2 at S24 and S48 for budget stability;
3. H2/H3/H5 at S48 for horizon stability;
4. any root whose Q order, Q-top, or visit-top changed was promoted to
   H2/H3/H5 at S96.

"Stable" means Q-top, visit-top, and every pairwise Q relation agree across
the relevant measured conditions. It does not mean convergence to Q-star or
to an unbounded legal-move oracle.

## Result

| measurement | stable / total |
|---|---:|
| identical H2/S12 deterministic repeat | **58 / 58** |
| complete signature, H2 S24 to S48 | 32 / 58 |
| complete signature, H2/H3/H5 at S48 | 13 / 58 |
| promoted to S96 | 53 / 58 |
| final bounded Q-top | 16 / 58 |
| final bounded visit-top | 19 / 58 |
| final complete pairwise Q order | **10 / 58** |
| conservative stable game-state groups | **7 / 36** |
| still Q-discriminating at deepest measured reference | **52 / 58** |
| original noisy H2/S12 Q-top equals deepest reference Q-top | **15 / 58** |

The instrument is deterministic, but the estimated answer is generally not
stable under search depth and budget. This separates reproducibility from
teacher quality.

### Budget versus horizon

| comparison | Q-top | visit-top | all pairwise Q relations |
|---|---:|---:|---:|
| H2, S24 to S48 (58 roots) | 52 | 57 | 32 |
| H2/H3/H5, S48 (58 roots) | 24 | 25 | 13 |
| H2/H3/H5, S96 (53 promoted roots) | 17 | 18 | 8 |
| H5, S48 to S96 (53 promoted roots) | 40 | 44 | 31 |

The main instability is horizon, not merely insufficient visits at fixed H2.
Doubling S48 to S96 improves sampling but does not make H2, H3 and H5 answer
the same question.

### The roots themselves remain valuable

The signal did not disappear: 52/58 roots still had unequal reference Q
values. The median top-versus-second reference Q margin was 0.1641 in the
normalized search return. The reference Q-top was rank 0/1/2 in 16/17/25
roots, so the hard set contains many genuine challenges to the hand-written
ranker rather than only rank-0 confirmations. Reference Q-top and visit-top
agreed in 55/58 roots.

Per-case final complete stability was:

| case | stable / roots |
|---|---:|
| dual-preloaded-dedicated | 2 / 18 |
| dual-shelf-mixed | 2 / 5 |
| single-empty-noshelf | 1 / 15 |
| single-empty-shelf | 5 / 20 |

This corpus was selected conditional on original Q discrimination. These
fractions do not estimate prevalence over all 389 Self-Play policy roots.

## Mechanism exposed by the audit

Across the 58 deepest measured reference searches, the recorded terminal
reason was `bounded_candidate_exhaustion` 4,334 times. Current search converts
that event into a game loss with magnitude 50. But the search action set is
only the candidate generator's bounded set, not the mathematical set of all
legal placements. Therefore:

```text
bounded generator found no candidate != certified true game loss
```

Increasing H creates more opportunities to hit this proxy terminal and back
up its ±50 value. That mechanism is structurally capable of changing Q order
with horizon, and the experiment observes exactly that pattern. Attribute
rewards may also contribute, but no evidence here licenses interpreting every
candidate-exhaustion event as a true dead end.

## Decision

1. Do not train a policy head on all 58 original H2/S12 Q or visit targets.
   Only 15 original Q-tops agree with the deepest measured reference.
2. Keep all 58 as a regression/capability benchmark. The 10 fully stable raw
   roots (seven unique state groups) are positive controls; the other 48 are
   the hard set.
3. Do not call H5/S96 an oracle. It is still bounded, zero-leaf PUCT and only
   16/58 roots have a stable Q-top under the measured convergence contract.
4. Before another policy learner, change bounded candidate exhaustion from a
   forced terminal loss into an explicitly censored/leaf-valued outcome unless
   an independent candidate-recall audit certifies true no-move. Then rerun
   exactly these 58 roots and require horizon stability to rise.
5. The run cost also rules out this H5/S96 implementation at every live move:
   eight parallel shards required 52 minutes to 2 h 21 min. Its present role
   is offline teacher auditing, not online production search.

The AlphaZero direction is not rejected. What failed is narrower and useful:
the current bounded-search teacher is dominated by a horizon-sensitive proxy
terminal while its leaf value is zero. The next AlphaZero-relevant gate is to
repair that leaf/terminal semantics, then ask whether the same 58 roots become
stable enough to teach P and V.
