# Censored bounded-exhaustion protocol

Date: 2026-08-22

## Change under test

The physical PUCT action set is a bounded provider Top-3, not the mathematical
set of all legal placements. A descendant with no retained Top-3 action is now
treated as an unknown zero-continuation leaf instead of a synthetic game loss:

```text
old: bounded Top-3 exhausted -> +/-50 terminal backup
new: bounded Top-3 exhausted -> keep accrued rewards, add zero continuation
```

The change does not call the value model at that leaf. It does not change
handoff chance, PUCT selection, root candidates, physical legality, the game
level no-candidate rule, or soft/priority reward accounting.

## Shadow candidate-recall audit

At each unique exhausted descendant, the measurement rerun asks the same fixed-
attempt provider for up to 64 candidates. The Top-3 remains the complete
searchable set. Only additional candidates are physically filtered, and none
are inserted into the tree.

Each audited node is classified as:

- `wider_safe_recovered_nodes`: at least one safe candidate exists beyond Top-3;
- `wider_proposal_empty_nodes`: the wider bounded provider also returns none;
- `wider_all_rejected_nodes`: wider proposals exist but all fail exact physics;
- `prefix_mismatch_nodes`: the wider call does not preserve the Top-3 prefix,
  invalidating a clean rank-cap interpretation for that node.

These classes diagnose the bounded provider. They do not certify the true
continuous legal action set; even a width-64 empty result remains censored.

## Frozen rerun

Use the same 58 Q-discriminating roots from Self-Play run `32515349437`, the
same H2/H3/H5 and S12/S24/S48/S96 schedule, deterministic physics, zero leaf
value, unchanged chance RNG, and no root noise. Compare against convergence run
`32543828460`.

Primary outputs:

1. deterministic repeat rate;
2. H2 S24-to-S48 stability;
3. H2/H3/H5 Q-top, visit-top and full-order stability;
4. reference Q-discriminating roots;
5. unique exhausted nodes and repeated censored visits;
6. shadow recall classification above.

No P/V model is accepted or injected from this run. The run decides whether
the former +/-50 proxy dominated the teacher and how much remaining exhaustion
is caused specifically by the Top-3 cap.
