"""Read-only accounting for identical-item physical evaluator reuse."""

from __future__ import annotations

from typing import Any


class ItemSymmetryTranspositionShadow:
    """Measure physical-state reuse without suppressing evaluator calls.

    Exact board keys remain authoritative.  A quotient-only hit occurs when a
    new exact board key maps to an already observed identical-item symmetry
    key.  Optional evaluator signatures detect whether such a reuse would have
    returned a different deterministic result.  Evaluator kinds are tracked
    separately so an unstable learned V cannot contaminate rollout evidence.
    """

    def __init__(self) -> None:
        self.observations = 0
        self.exact_keys: set[str] = set()
        self.symmetry_keys: set[str] = set()
        self.exact_hits = 0
        self.symmetry_hits = 0
        self.quotient_only_hits = 0
        self._exact_by_symmetry: dict[str, set[str]] = {}
        self._evaluator_observations: dict[str, int] = {}
        self._evaluator_symmetry_keys: dict[str, set[str]] = {}
        self._evaluator_symmetry_hits: dict[str, int] = {}
        self._evaluator_quotient_only_hits: dict[str, int] = {}
        self._evaluator_conflicts: dict[str, int] = {}
        self._signature_by_evaluator_symmetry: dict[
            str, dict[str, dict[str, str]]
        ] = {}

    def observe(
        self, *, exact_key: str, symmetry_key: str,
        value_signature: str | None = None,
        evaluator_signature: str | None = None,
        evaluator_kind: str | None = None,
    ) -> dict[str, Any]:
        if value_signature is not None:
            if evaluator_signature is not None:
                raise ValueError(
                    "provide value_signature or evaluator_signature, not both"
                )
            evaluator_signature = value_signature
            evaluator_kind = "value"
        if evaluator_signature is not None and not evaluator_kind:
            raise ValueError("evaluator_signature requires evaluator_kind")
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

        evaluator_conflict = False
        if evaluator_signature is not None:
            kind = str(evaluator_kind)
            keys = self._evaluator_symmetry_keys.setdefault(kind, set())
            evaluator_seen = symmetry_key in keys
            self._evaluator_observations[kind] = (
                self._evaluator_observations.get(kind, 0) + 1
            )
            self._evaluator_symmetry_hits[kind] = (
                self._evaluator_symmetry_hits.get(kind, 0)
                + int(evaluator_seen)
            )
            self._evaluator_quotient_only_hits[kind] = (
                self._evaluator_quotient_only_hits.get(kind, 0)
                + int(evaluator_seen and quotient_only)
            )
            keys.add(symmetry_key)
            values = self._signature_by_evaluator_symmetry.setdefault(
                kind, {}
            ).setdefault(symmetry_key, {})
            if (
                evaluator_seen and quotient_only
                and values
                and evaluator_signature not in values.values()
            ):
                evaluator_conflict = True
                self._evaluator_conflicts[kind] = (
                    self._evaluator_conflicts.get(kind, 0) + 1
                )
            values[exact_key] = evaluator_signature

        return {
            "exact_hit": exact_seen,
            "symmetry_hit": symmetry_seen,
            "quotient_only_hit": quotient_only,
            "evaluator_kind": evaluator_kind,
            "evaluator_conflict": evaluator_conflict,
            # Backward-compatible event field for the original V-only probe.
            "value_conflict": (
                evaluator_conflict and evaluator_kind == "value"
            ),
        }

    def summary(self) -> dict[str, Any]:
        quotient_buckets = sum(
            len(exact_keys) > 1
            for exact_keys in self._exact_by_symmetry.values()
        )
        evaluator_by_kind = {}
        for kind in sorted(self._evaluator_observations):
            observations = self._evaluator_observations[kind]
            unique = len(self._evaluator_symmetry_keys[kind])
            evaluator_by_kind[kind] = {
                "observations": observations,
                "unique_symmetry_states": unique,
                "symmetry_hits": self._evaluator_symmetry_hits.get(kind, 0),
                "quotient_only_hits": (
                    self._evaluator_quotient_only_hits.get(kind, 0)
                ),
                "potential_call_savings": observations - unique,
                "conflicts": self._evaluator_conflicts.get(kind, 0),
            }
        evaluator_observations = sum(
            row["observations"] for row in evaluator_by_kind.values()
        )
        unique_evaluator_states = sum(
            row["unique_symmetry_states"]
            for row in evaluator_by_kind.values()
        )
        evaluator_conflicts = sum(
            row["conflicts"] for row in evaluator_by_kind.values()
        )
        return {
            "contract": "identical_item_physical_evaluator_cache_shadow_v2",
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
            "evaluator_observations": evaluator_observations,
            "unique_evaluator_symmetry_states": unique_evaluator_states,
            "evaluator_symmetry_hits": sum(
                row["symmetry_hits"] for row in evaluator_by_kind.values()
            ),
            "evaluator_quotient_only_hits": sum(
                row["quotient_only_hits"]
                for row in evaluator_by_kind.values()
            ),
            "potential_evaluator_call_savings": (
                evaluator_observations - unique_evaluator_states
            ),
            "evaluator_conflicts": evaluator_conflicts,
            "evaluator_by_kind": evaluator_by_kind,
            # Compatibility fields consumed by the existing V aggregate.
            "value_conflicts": evaluator_by_kind.get(
                "value", {}
            ).get("conflicts", 0),
            "rollout_conflicts": evaluator_by_kind.get(
                "rollout", {}
            ).get("conflicts", 0),
            "zero_conflict_observed": evaluator_conflicts == 0,
        }
