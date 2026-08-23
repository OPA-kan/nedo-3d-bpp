"""Objective-neutral coverage over the environment's own action domain.

Phase 1A of the frozen roadmap: strategy-free candidate generation that
frees the action support from the legacy generator. The domain is cut by
geometry the simulator itself publishes — the container polytope points
in the observation, shrunk by the item's orientation-rotated half
extents — and by nothing else: no scores, no support surfaces, no
heuristics. Physical legality is decided downstream by the same
fresh-replay filter every other proposal faces.

Sampling is a seeded, digit-scrambled Halton sequence addressed by
``(coverage_seed, stratum, coverage_sequence_index)``. Points are
reproducible from their recorded coordinates alone (no shared mutable
RNG), matching the frozen behavior contract: plain low-discrepancy
sequences carry no action probability, so rows are declared off-policy
via ``proposal_probability = None`` rather than pretending a density.

Strata enumerate (visible item, container, orientation) in a
deterministic order; the sampler round-robins strata so any prefix of
the output is itself balanced coverage.
"""

from __future__ import annotations

import hashlib
from typing import Any

try:
    from scripts.counterfactual_graph import stable_id
except ModuleNotFoundError:
    from counterfactual_graph import stable_id

COVERAGE_GENERATOR = "scrambled_halton_v1"
_PRIMES = (2, 3, 5)


def _scrambled_halton_axis(
    index: int, base: int, *, coverage_seed: int, stratum_key: str, axis: int,
) -> float:
    """Deterministic digit-scrambled radical inverse in ``base``."""
    if index < 0:
        raise ValueError("sequence index must be non-negative")
    value = 0.0
    scale = 1.0 / base
    remaining = index + 1  # skip the origin point of the plain sequence
    digit_position = 0
    while remaining > 0:
        remaining, digit = divmod(remaining, base)
        payload = (
            f"{coverage_seed}:{stratum_key}:{axis}:{digit_position}"
        ).encode("utf-8")
        offset = int.from_bytes(
            hashlib.sha256(payload).digest()[:4], "big"
        ) % base
        value += ((digit + offset) % base) * scale
        scale /= base
        digit_position += 1
    return value


def rotated_half_extents(
    item: dict[str, Any], orientation: int,
) -> tuple[float, float, float]:
    length = float(item["length"])
    width = float(item["width"])
    height = float(item["height"])
    dimensions = (
        (length, width, height),
        (length, height, width),
        (height, width, length),
        (width, length, height),
        (width, height, length),
        (height, length, width),
    )
    if orientation not in range(6):
        raise ValueError("orientation must be between 0 and 5")
    x, y, z = dimensions[orientation]
    return (x / 2.0, y / 2.0, z / 2.0)


def container_domain(container: dict[str, Any]) -> dict[str, tuple[float, float]]:
    """Axis-aligned bounds of the container's own published polytope.

    Container-local frame: the simulator's ``local_to_global`` shifts only
    x by the container offset, so local bounds subtract ``center[0]`` from
    x and keep y/z as published. The cut corner stays inside the bounding
    box on purpose — rejecting it is the physics filter's job, not the
    sampler's.
    """
    points = container.get("points")
    if not points:
        raise ValueError("container observation carries no polytope points")
    center = container.get("center") or [0.0, 0.0, 0.0]
    xs = [float(p[0]) - float(center[0]) for p in points]
    ys = [float(p[1]) for p in points]
    zs = [float(p[2]) for p in points]
    return {
        "x": (min(xs), max(xs)),
        "y": (min(ys), max(ys)),
        "z": (min(zs), max(zs)),
    }


def stratum_domain(
    container: dict[str, Any], item: dict[str, Any], orientation: int,
) -> dict[str, tuple[float, float]] | None:
    """Center-position bounds for one (item, orientation, container).

    None when the oriented item cannot fit inside the bounding box at all.
    """
    bounds = container_domain(container)
    half = rotated_half_extents(item, orientation)
    domain = {}
    for axis, (low, high), extent in zip(
        ("x", "y", "z"), bounds.values(), half
    ):
        lo, hi = low + extent, high - extent
        if lo > hi:
            return None
        domain[axis] = (lo, hi)
    return domain


def enumerate_strata(observation: dict[str, Any]) -> list[dict[str, Any]]:
    """Deterministic (item, container, orientation) strata for one state."""
    strata = []
    pool = observation.get("pool_list") or []
    containers = observation.get("container_list") or []
    for pool_index, item in enumerate(pool):
        for container in containers:
            for orientation in range(6):
                domain = stratum_domain(container, item, orientation)
                if domain is None:
                    continue
                strata.append({
                    "pool_index": pool_index,
                    "stable_item_index": item.get("index"),
                    "container_index": int(container.get("index", 0)),
                    "orientation": orientation,
                    "domain": domain,
                    "stratum_key": stable_id("coverage-stratum-v1", {
                        "stable_item_index": item.get("index"),
                        "container_index": int(container.get("index", 0)),
                        "orientation": orientation,
                    }),
                })
    return strata


def sample_stratum(
    stratum: dict[str, Any], sequence_index: int, *, coverage_seed: int,
    z_mode: str = "volume",
) -> dict[str, Any]:
    """One coverage action.

    ``z_mode='volume'`` samples the full vertical span; most of it is far
    from any resting surface, so it measures the raw action volume.
    ``z_mode='release_top'`` fixes z at the top of the span and lets
    gravity find the contact — still geometry-only (no support surfaces
    are computed), it just reparametrizes the same domain the way a
    release-style command does.
    """
    if z_mode not in {"volume", "release_top"}:
        raise ValueError(f"unsupported z_mode: {z_mode}")
    position = []
    for axis_number, axis in enumerate(("x", "y", "z")):
        low, high = stratum["domain"][axis]
        if axis == "z" and z_mode == "release_top":
            position.append(high)
            continue
        unit = _scrambled_halton_axis(
            sequence_index, _PRIMES[axis_number],
            coverage_seed=coverage_seed,
            stratum_key=stratum["stratum_key"], axis=axis_number,
        )
        position.append(low + unit * (high - low))
    command = {
        "item_idx": int(stratum["pool_index"]),
        "container_idx": int(stratum["container_index"]),
        "place_pos": [float(value) for value in position],
        "orientation": int(stratum["orientation"]),
    }
    provenance = {
        "schema_version": 1,
        "source": "coverage",
        "provider": COVERAGE_GENERATOR,
        "coverage_z_mode": z_mode,
        "mixture_weight": None,
        "proposal_probability": None,
        "proposal_log_probability": None,
        "coverage_seed": int(coverage_seed),
        "coverage_sequence_index": int(sequence_index),
        "dedup_multiplicity": 1,
    }
    return {
        # stable_id returns "namespace-hash"; never truncate it from the
        # front or every candidate collapses onto the namespace prefix.
        "candidate_id": stable_id("coverage-candidate-v1", {
            "seed": int(coverage_seed),
            "stratum": stratum["stratum_key"],
            "sequence_index": int(sequence_index),
            "z_mode": z_mode,
        }),
        "command_action": command,
        "selection": {
            "provider": COVERAGE_GENERATOR,
            "candidate_kind": "coverage_candidate",
            "coverage_z_mode": z_mode,
            "stable_item_index": stratum["stable_item_index"],
            "coverage_stratum_key": stratum["stratum_key"],
        },
        "proposal_provenance": provenance,
    }


def coverage_candidates(
    observation: dict[str, Any], *, coverage_seed: int, budget: int,
    z_mode: str = "volume",
) -> list[dict[str, Any]]:
    """Round-robin balanced coverage proposals for one observed state."""
    if budget < 1:
        raise ValueError("budget must be positive")
    strata = enumerate_strata(observation)
    if not strata:
        return []
    result = []
    sequence_index = 0
    while len(result) < budget:
        for stratum in strata:
            if len(result) >= budget:
                break
            result.append(
                sample_stratum(
                    stratum, sequence_index, coverage_seed=coverage_seed,
                    z_mode=z_mode,
                )
            )
        sequence_index += 1
    return result
