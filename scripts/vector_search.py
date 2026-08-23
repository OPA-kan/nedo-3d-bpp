"""Scale-free paired comparisons for vector-valued physical outcomes."""

from __future__ import annotations

import math
from typing import Any


def _wilson_lower_bound(successes: int, total: int, z: float) -> float:
    if total <= 0:
        return 0.0
    proportion = successes / total
    denominator = 1.0 + z * z / total
    center = proportion + z * z / (2.0 * total)
    radius = z * math.sqrt(
        proportion * (1.0 - proportion) / total
        + z * z / (4.0 * total * total)
    )
    return max(0.0, (center - radius) / denominator)


def _eligible_vectors(
    samples: list[dict[str, Any]], objectives: dict[str, str],
) -> tuple[
    dict[str, dict[str, dict[str, float]]], dict[str, set[str]],
]:
    by_candidate: dict[str, dict[str, dict[str, float]]] = {}
    worlds_by_candidate: dict[str, set[str]] = {}
    for sample in samples:
        candidate = str(sample["root_candidate_id"])
        world = str(sample["exogenous_world_id"])
        worlds_by_candidate.setdefault(candidate, set()).add(world)
        values = sample.get("raw_outcome_vector") or {}
        eligibility = sample.get("head_eligibility") or {}
        if not all(
            eligibility.get(head) is True and isinstance(values.get(head), (int, float))
            and math.isfinite(float(values[head]))
            for head in objectives
        ):
            continue
        candidate_worlds = by_candidate.setdefault(candidate, {})
        if world in candidate_worlds:
            raise ValueError(
                f"duplicate paired outcome for candidate={candidate} world={world}"
            )
        candidate_worlds[world] = {
            head: float(values[head]) for head in objectives
        }
    return by_candidate, worlds_by_candidate


def paired_dominance(
    samples: list[dict[str, Any]], *, candidate_id: str, incumbent_id: str,
    objectives: dict[str, str], tolerances: dict[str, float] | None = None,
    confidence_z: float = 1.96,
) -> dict[str, Any]:
    """Estimate joint confidence dominance from matched exogenous worlds."""
    if not objectives:
        raise ValueError("at least one objective is required")
    invalid = set(objectives.values()) - {"maximize", "minimize"}
    if invalid:
        raise ValueError(f"unsupported objective directions: {sorted(invalid)}")
    if confidence_z < 0.0:
        raise ValueError("confidence_z must be non-negative")
    tolerances = dict(tolerances or {})
    if any(float(tolerances.get(head, 0.0)) < 0.0 for head in objectives):
        raise ValueError("tolerances must be non-negative")

    by_candidate, worlds_by_candidate = _eligible_vectors(samples, objectives)
    candidate_worlds = by_candidate.get(str(candidate_id), {})
    incumbent_worlds = by_candidate.get(str(incumbent_id), {})
    paired_world_ids = sorted(set(candidate_worlds) & set(incumbent_worlds))
    nonworse_count = 0
    strict_count = 0
    for world in paired_world_ids:
        nonworse = True
        strict = False
        for head, direction in objectives.items():
            left = candidate_worlds[world][head]
            right = incumbent_worlds[world][head]
            tolerance = float(tolerances.get(head, 0.0))
            if direction == "maximize":
                nonworse = nonworse and left >= right - tolerance
                strict = strict or left > right + tolerance
            else:
                nonworse = nonworse and left <= right + tolerance
                strict = strict or left < right - tolerance
        nonworse_count += int(nonworse)
        strict_count += int(nonworse and strict)

    total = len(paired_world_ids)
    return {
        "candidate_id": str(candidate_id),
        "incumbent_id": str(incumbent_id),
        "paired_worlds": total,
        "paired_world_ids": paired_world_ids,
        "excluded_worlds": len(
            worlds_by_candidate.get(str(candidate_id), set())
            | worlds_by_candidate.get(str(incumbent_id), set())
        ) - total,
        "joint_nonworse_count": nonworse_count,
        "joint_strict_count": strict_count,
        "dominance_probability": strict_count / total if total else None,
        "dominance_probability_lcb": _wilson_lower_bound(
            strict_count, total, confidence_z
        ),
        "confidence_z": float(confidence_z),
        "tolerances": {
            head: float(tolerances.get(head, 0.0)) for head in objectives
        },
    }


def confidence_pareto_frontier(
    samples: list[dict[str, Any]], *, objectives: dict[str, str],
    tolerances: dict[str, float] | None = None, minimum_pairs: int = 1,
    minimum_probability_lcb: float = 0.8, confidence_z: float = 1.96,
) -> dict[str, Any]:
    """Remove only actions dominated with sufficient paired evidence."""
    if minimum_pairs < 1:
        raise ValueError("minimum_pairs must be positive")
    if not 0.0 <= minimum_probability_lcb <= 1.0:
        raise ValueError("minimum_probability_lcb must be in [0, 1]")
    candidates = sorted({str(row["root_candidate_id"]) for row in samples})
    dominated_by: dict[str, list[str]] = {}
    comparisons = []
    for target in candidates:
        dominators = []
        for challenger in candidates:
            if challenger == target:
                continue
            result = paired_dominance(
                samples, candidate_id=challenger, incumbent_id=target,
                objectives=objectives, tolerances=tolerances,
                confidence_z=confidence_z,
            )
            comparisons.append(result)
            if (
                result["paired_worlds"] >= minimum_pairs
                and result["dominance_probability_lcb"]
                >= minimum_probability_lcb
            ):
                dominators.append(challenger)
        if dominators:
            dominated_by[target] = sorted(dominators)
    dominated = sorted(dominated_by)
    return {
        "frontier_candidate_ids": [
            candidate for candidate in candidates if candidate not in dominated_by
        ],
        "dominated_candidate_ids": dominated,
        "dominated_by": dominated_by,
        "minimum_pairs": int(minimum_pairs),
        "minimum_probability_lcb": float(minimum_probability_lcb),
        "comparisons": comparisons,
    }
