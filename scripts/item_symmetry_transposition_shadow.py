"""Read-only accounting for a possible identical-item transposition cache."""

from __future__ import annotations

from typing import Any


class ItemSymmetryTranspositionShadow:
    """Measure cache reuse without suppressing any evaluator call.

    Exact board keys remain authoritative.  A quotient-only hit occurs when a
    new exact board key maps to an already observed identical-item symmetry
    key.  Optional value signatures detect whether such a reuse would have
    returned a different deterministic leaf prediction.
    """

    def __init__(self) -> None:
        self.observations = 0
        self.exact_keys: set[str] = set()
        self.symmetry_keys: set[str] = set()
        self.exact_hits = 0
        self.symmetry_hits = 0
        self.quotient_only_hits = 0
        self.evaluator_observations = 0
        self.evaluator_symmetry_keys: set[str] = set()
        self.evaluator_symmetry_hits = 0
        self.evaluator_quotient_only_hits = 0
        self.value_conflicts = 0
        self._exact_by_symmetry: dict[str, set[str]] = {}
        self._value_by_symmetry: dict[str, dict[str, str]] = {}

    def observe(
        self, *, exact_key: str, symmetry_key: str,
        value_signature: str | None = None,
    ) -> dict[str, Any]:
        exact_seen = exact_key in self.exact_keys
        symmetry_seen = symmetry_key in self.symmetry_keys
        quotient_only = symmetry_seen and not exact_seen
        self.observations += 1
        self.exact_hits += int(exact_seen)
        self.symmetry_hits += int(symmetry_seen)
        self.quotient_only_hits += int(quotient_only)
        self.exact_keys.add(exact_key)
        self.symmetry_keys.add(symmetry_key)
        self._exact_by_symmetry.setdefault(symmetry_key, set()).add(exact_key)

        value_conflict = False
        if value_signature is not None:
            evaluator_seen = symmetry_key in self.evaluator_symmetry_keys
            self.evaluator_observations += 1
            self.evaluator_symmetry_hits += int(evaluator_seen)
            self.evaluator_quotient_only_hits += int(
                evaluator_seen and quotient_only
            )
            self.evaluator_symmetry_keys.add(symmetry_key)
            values = self._value_by_symmetry.setdefault(symmetry_key, {})
            if quotient_only and values and value_signature not in values.values():
                value_conflict = True
                self.value_conflicts += 1
            values[exact_key] = value_signature

        return {
            "exact_hit": exact_seen,
            "symmetry_hit": symmetry_seen,
            "quotient_only_hit": quotient_only,
            "value_conflict": value_conflict,
        }

    def summary(self) -> dict[str, Any]:
        quotient_buckets = sum(
            len(exact_keys) > 1
            for exact_keys in self._exact_by_symmetry.values()
        )
        return {
            "contract": "identical_item_leaf_cache_shadow_v1",
            "behavior_effect": "none",
            "observations": self.observations,
            "unique_exact_states": len(self.exact_keys),
            "unique_symmetry_states": len(self.symmetry_keys),
            "exact_hits": self.exact_hits,
            "symmetry_hits": self.symmetry_hits,
            "quotient_only_hits": self.quotient_only_hits,
            "quotient_buckets": quotient_buckets,
            "potential_state_reduction": (
                len(self.exact_keys) - len(self.symmetry_keys)
            ),
            "evaluator_observations": self.evaluator_observations,
            "unique_evaluator_symmetry_states": len(
                self.evaluator_symmetry_keys
            ),
            "evaluator_symmetry_hits": self.evaluator_symmetry_hits,
            "evaluator_quotient_only_hits": self.evaluator_quotient_only_hits,
            "potential_evaluator_call_savings": (
                self.evaluator_observations
                - len(self.evaluator_symmetry_keys)
            ),
            "value_conflicts": self.value_conflicts,
            "zero_conflict_observed": self.value_conflicts == 0,
        }
