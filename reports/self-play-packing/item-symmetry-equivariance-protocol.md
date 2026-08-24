# Identical-item symmetry equivariance protocol

Status: six-cell physical gate passed; physical-search and rollout reuse are
being measured in shadow mode.

## Claim under test

For item types `tau` with multiplicity `n_tau`, the candidate search may have
an exact label symmetry

```text
G_items = product_tau S_(n_tau)
```

where a permutation changes stable item labels but not item geometry,
attributes, dynamics, pool position semantics, or the physical outcome. This
claim is narrower than geometric reflection or container exchange symmetry;
neither is assumed here.

## Paired physical audit

For each of the six frozen single-agent cells:

1. Replay its recorded pool-positional action sequence.
2. Find the first selected stream item with a still-unselected item having an
   identical model-visible physical signature.
3. Transpose those two stable IDs in the full item stream.
4. Replay the exact same pool-positional action sequence with the same seed.
5. Compare each paired transition.

Every audited transition must preserve:

- simulator status and safe/terminal flags;
- every raw cumulative metric within `1e-6` absolute/relative tolerance;
- the item-symmetry child fingerprint.

The ordinary board fingerprint and selected stable label must differ at least
once. A pair without that negative control is vacuous and cannot pass.

## Gate

All six cells must be non-vacuous and the aggregate must contain zero
false-merge transitions. Run `32740787738` passed with 6/6 non-vacuous cells,
64/64 equivariant transitions, and zero false merges. Exact board fingerprints
still remain authoritative. Run `32742830165` then found 14 quotient-only leaf
hits, but 6 learned-V signature conflicts, so V caching is not licensed.

The active integration is deliberately V-independent. It records:

- quotient-only physical search states and potential transposition reduction;
- terminal-rollout calls that share an item-symmetry state;
- whether those genuine-terminal outcome vectors agree.

Every physical expansion and terminal rollout still executes. The shadow can
therefore establish the safe upper bound before any action-orbit deduplication,
state merge, or rollout memoization changes search behavior. It does not
license container swaps, mirror transforms, or partial-order reduction.

Implementation:

- `scripts/audit_item_symmetry_equivariance.py`
- `scripts/aggregate_item_symmetry_equivariance.py`
- `scripts/item_symmetry_transposition_shadow.py`
- `.github/workflows/item-symmetry-equivariance.yml`
