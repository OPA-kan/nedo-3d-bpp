"""Shadow attribute counters at multiple geometric resolutions.

The bundled evaluator's published-rule proxy counts each protected item at
most once and only for direct contact.  That contract remains untouched.
This module records the alternative item/pair and direct/stack-aware readings
side by side so later calibration can select a measurement without rewriting
past physical trajectories.
"""

from __future__ import annotations

from typing import Any


CONTACT_TOLERANCE = 0.02
FOOTPRINT_EPSILON = 1e-6


def _overlap_area(lower: dict[str, Any], upper: dict[str, Any]) -> float:
    lower_min, lower_max = lower["aabb_min"], lower["aabb_max"]
    upper_min, upper_max = upper["aabb_min"], upper["aabb_max"]
    dx = min(lower_max[0], upper_max[0]) - max(lower_min[0], upper_min[0])
    dy = min(lower_max[1], upper_max[1]) - max(lower_min[1], upper_min[1])
    return max(0.0, float(dx)) * max(0.0, float(dy))


def _is_above(
    lower: dict[str, Any], upper: dict[str, Any], *, stack_aware: bool,
) -> bool:
    if _overlap_area(lower, upper) <= FOOTPRINT_EPSILON:
        return False
    lower_top = float(lower["aabb_max"][2])
    upper_bottom = float(upper["aabb_min"][2])
    if stack_aware:
        return upper_bottom >= lower_top - CONTACT_TOLERANCE
    gap = upper_bottom - lower_top
    return -CONTACT_TOLERANCE <= gap <= CONTACT_TOLERANCE


def _coverage_counts(
    items: list[dict[str, Any]], attribute: str, *, stack_aware: bool,
) -> tuple[int, int]:
    violated_items: set[int] = set()
    violating_pairs = 0
    for lower_index, lower in enumerate(items):
        if not bool(lower.get(attribute)):
            continue
        for upper_index, upper in enumerate(items):
            if upper_index == lower_index or bool(upper.get(attribute)):
                continue
            if _is_above(lower, upper, stack_aware=stack_aware):
                violated_items.add(lower_index)
                violating_pairs += 1
    return len(violated_items), violating_pairs


def attribute_violation_counters(
    containers: list[dict[str, Any]],
) -> dict[str, int]:
    """Return raw counters without claiming an official score mapping."""
    result: dict[str, int] = {}
    for public_name, attribute in (
        ("soft", "is_soft"),
        ("priority", "is_prioritized"),
    ):
        for resolution, stack_aware in (
            ("direct", False),
            ("stack", True),
        ):
            item_total = 0
            pair_total = 0
            for container in containers:
                items = list(container.get("packed_items", []))
                violated_items, violating_pairs = _coverage_counts(
                    items, attribute, stack_aware=stack_aware,
                )
                item_total += violated_items
                pair_total += violating_pairs
            result[f"{public_name}_{resolution}_violated_items"] = item_total
            result[f"{public_name}_{resolution}_violating_pairs"] = pair_total
    return result


def settled_attribute_violation_counters(env) -> dict[str, int]:
    """Capture the shadow counters from the current settled PyBullet board."""
    client = getattr(env, "client", None)
    manager = getattr(env, "container_manager", None)
    if client is None or manager is None:
        return {}
    snapshots = []
    for container in manager.containers:
        packed_items = []
        for item in container.packed_items:
            pybullet_id = getattr(item, "pybullet_id", None)
            if pybullet_id is None:
                # Test doubles and non-physical states have no honest AABB
                # reading. Missing shadow metrics are censored downstream;
                # fabricating zero would falsely certify a clean board.
                return {}
            if not all(hasattr(item, name) for name in (
                "index", "is_soft", "is_prioritized",
            )):
                return {}
            aabb_min, aabb_max = client.getAABB(pybullet_id)
            packed_items.append({
                "index": int(item.index),
                "aabb_min": [float(value) for value in aabb_min],
                "aabb_max": [float(value) for value in aabb_max],
                "is_soft": bool(item.is_soft),
                "is_prioritized": bool(item.is_prioritized),
            })
        snapshots.append({
            "index": int(container.index),
            "packed_items": packed_items,
        })
    return attribute_violation_counters(snapshots)
