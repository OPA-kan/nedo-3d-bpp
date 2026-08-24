"""Pure single-agent packing semantics (Phase 2 mainline contract).

No players, no handoff, no zero-sum rewards, no terminal prize: an
episode is one agent placing a stream, and its record is the raw
component vector, never a scalar. See
``reports/self-play-packing/single-agent-mainline-contract.md``.
"""

from __future__ import annotations

import math
from typing import Any

BEHAVIOR_CONTRACT = "single_agent_v1"

# Bounded one-step measurement heads: the two-player game head is gone;
# post-shake stability stays declared-unmeasured at branch level.
COMPONENT_HEAD_SPECS = {
    "fill_gain": "maximize",
    "placed_gain": "diagnostic",
    "soft_violation_gain": "minimize",
    "soft_direct_pair_gain": "diagnostic_minimize_proxy",
    "soft_stack_item_gain": "diagnostic_minimize_proxy",
    "soft_stack_pair_gain": "diagnostic_minimize_proxy",
    "priority_covered_gain": "minimize",
    "priority_direct_pair_gain": "diagnostic_minimize_proxy",
    "priority_stack_item_gain": "diagnostic_minimize_proxy",
    "priority_stack_pair_gain": "diagnostic_minimize_proxy",
    "priority_misrouted_gain": "minimize",
    "center_of_mass_z_delta": "diagnostic",
    "surface_total_variation_delta": "minimize_proxy",
}

# Episode suffix value heads: component returns plus terminal-only heads.
SUFFIX_HEAD_SPECS = {
    "fill_return": "maximize",
    "placed_return": "diagnostic",
    "stream_completed": "maximize",
    "soft_violation_return": "minimize",
    "soft_direct_pair_return": "diagnostic_minimize_proxy",
    "soft_stack_item_return": "diagnostic_minimize_proxy",
    "soft_stack_pair_return": "diagnostic_minimize_proxy",
    "priority_covered_return": "minimize",
    "priority_direct_pair_return": "diagnostic_minimize_proxy",
    "priority_stack_item_return": "diagnostic_minimize_proxy",
    "priority_stack_pair_return": "diagnostic_minimize_proxy",
    "priority_misrouted_return": "minimize",
    "center_of_mass_z_return": "diagnostic",
    "surface_total_variation_return": "minimize_proxy",
    "terminal_stability_max_shift": "minimize",
    "terminal_stability_peak_kinetic_energy": "minimize",
    "terminal_stability_items_toppled": "minimize",
}

GENUINE_TERMINATIONS = {
    "stream_exhausted", "no_retained_candidate", "no_safe_retained_candidate",
}

_METRIC_ALIASES = {
    "fill": ("fill_score_proxy", "fill_percent_proxy"),
    "placed": ("placed_count",),
    "soft_violation": ("soft_covered_by_other",),
    "soft_direct_pair": ("soft_direct_violating_pairs",),
    "soft_stack_item": ("soft_stack_violated_items",),
    "soft_stack_pair": ("soft_stack_violating_pairs",),
    "priority_covered": ("priority_covered_by_other",),
    "priority_direct_pair": ("priority_direct_violating_pairs",),
    "priority_stack_item": ("priority_stack_violated_items",),
    "priority_stack_pair": ("priority_stack_violating_pairs",),
    "priority_misrouted": ("priority_misrouted",),
    "center_of_mass_z": ("center_of_mass_z", "com_z"),
    "surface_total_variation": ("surface_total_variation",),
}
_COMPONENT_TO_METRIC = {
    "fill_gain": "fill",
    "placed_gain": "placed",
    "soft_violation_gain": "soft_violation",
    "soft_direct_pair_gain": "soft_direct_pair",
    "soft_stack_item_gain": "soft_stack_item",
    "soft_stack_pair_gain": "soft_stack_pair",
    "priority_covered_gain": "priority_covered",
    "priority_direct_pair_gain": "priority_direct_pair",
    "priority_stack_item_gain": "priority_stack_item",
    "priority_stack_pair_gain": "priority_stack_pair",
    "priority_misrouted_gain": "priority_misrouted",
    "center_of_mass_z_delta": "center_of_mass_z",
    "surface_total_variation_delta": "surface_total_variation",
}
_SUFFIX_TO_METRIC = {
    "fill_return": "fill",
    "placed_return": "placed",
    "soft_violation_return": "soft_violation",
    "soft_direct_pair_return": "soft_direct_pair",
    "soft_stack_item_return": "soft_stack_item",
    "soft_stack_pair_return": "soft_stack_pair",
    "priority_covered_return": "priority_covered",
    "priority_direct_pair_return": "priority_direct_pair",
    "priority_stack_item_return": "priority_stack_item",
    "priority_stack_pair_return": "priority_stack_pair",
    "priority_misrouted_return": "priority_misrouted",
    "center_of_mass_z_return": "center_of_mass_z",
    "surface_total_variation_return": "surface_total_variation",
}


def _metric(metrics: dict[str, Any], name: str) -> float | None:
    for key in _METRIC_ALIASES[name]:
        value = metrics.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            value = float(value)
            if math.isfinite(value):
                return value
    return None


def component_delta_vector(
    before: dict[str, Any], after: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """Masked one-step component deltas; missing metrics censor, never zero."""
    result = {}
    for head, objective in COMPONENT_HEAD_SPECS.items():
        metric = _COMPONENT_TO_METRIC[head]
        left, right = _metric(before, metric), _metric(after, metric)
        value = None if left is None or right is None else right - left
        result[head] = {
            "value": value,
            "target_eligible": value is not None,
            "censor_reason": None if value is not None else "unmeasured",
            "objective": objective,
        }
    return result


def suffix_value_heads(
    step_metrics: dict[str, Any], final_metrics: dict[str, Any], *,
    termination: str,
) -> dict[str, dict[str, Any]]:
    """Suffix component returns from one visited state to episode end."""
    genuine = termination in GENUINE_TERMINATIONS
    result = {}
    for head, objective in SUFFIX_HEAD_SPECS.items():
        if head == "stream_completed":
            value = 1.0 if termination == "stream_exhausted" else 0.0
        elif head.startswith("terminal_stability_"):
            key = head.replace("terminal_stability_", "post_shake_")
            raw = final_metrics.get(key)
            value = (
                float(raw)
                if isinstance(raw, (int, float))
                and not isinstance(raw, bool) and math.isfinite(float(raw))
                else None
            )
        else:
            metric = _SUFFIX_TO_METRIC[head]
            left = _metric(step_metrics, metric)
            right = _metric(final_metrics, metric)
            value = None if left is None or right is None else right - left
        eligible = bool(genuine and value is not None)
        result[head] = {
            "value": value,
            "target_eligible": eligible,
            "censor_reason": (
                None if eligible
                else (termination if not genuine else "unmeasured")
            ),
            "objective": objective,
        }
    return result
