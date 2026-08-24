# Identical-item symmetry equivariance protocol

Status: six-cell physical gate passed. Two narrow, V-independent reuse paths
are active behind explicit contracts; broader search transpositions remain
shadow-only.

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

The integration is deliberately V-independent. The original shadow records:

- quotient-only physical search states and potential transposition reduction;
- terminal-rollout calls that share an item-symmetry state;
- whether those genuine-terminal outcome vectors agree.

The passed gate now licenses two exact-label reuse paths:

1. terminal rollout results are memoized inside one root search by
   `(item-symmetry leaf fingerprint, stream cursor)`; only genuine terminal,
   complete vectors are stored and censored results are never cached;
2. the exact PyBullet legal filter checks one representative of an identical-
   item action orbit and reuses its classification for aliases. An orbit must
   preserve physical item type, command pose, container, and the ordered
   visible-pool type sequence after the selected item is removed.

Both paths fail closed when their metadata is incomplete. Replay-inclusive
physical-step equivalents and reuse counts are reported separately from the
legacy logical step count. The terminal cache is root-local because scenario,
future stream and continuation policy are then fixed.

Search-node transposition remains shadow-only. Provider/ranker stable-ID
tie-breaks and concrete action remapping have not yet passed an equivariance
gate. This protocol does not license container swaps, mirror transforms,
geometric rotations, partial-order reduction, or learned-V caching.

Implementation:

- `scripts/audit_item_symmetry_equivariance.py`
- `scripts/aggregate_item_symmetry_equivariance.py`
- `scripts/item_symmetry_transposition_shadow.py`
- `scripts/run_self_play_packing.py`
- `scripts/run_vector_mcts.py`
- `.github/workflows/item-symmetry-equivariance.yml`
