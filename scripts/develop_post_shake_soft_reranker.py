"""Select a post-shake soft afterstate model without reading late roots.

The target is the distributional H3 continuation relation for
``post_shake_soft_covered_by_other``.  Every validation fold holds out a
complete physical graph.  The exported policy is therefore safe to evaluate
once on ``distributional_late_holdout.jsonl`` in a separate process.
"""

from __future__ import annotations

import argparse
import json
import math
import pathlib
import statistics
from typing import Any, Callable

try:
    from scripts.evaluate_counterfactual_afterstate_value import (
        _features,
        _predict_ridge,
        _read_jsonl,
        _state_delta,
        fit_ridge_model,
    )
except ModuleNotFoundError:  # direct ``python scripts/...`` execution
    from evaluate_counterfactual_afterstate_value import (
        _features,
        _predict_ridge,
        _read_jsonl,
        _state_delta,
        fit_ridge_model,
    )


METRIC = "post_shake_soft_covered_by_other"
LABEL_FAMILY = "distributional_continuation_labels"
DIRECTIONAL = ("lower_afterstate_better", "higher_afterstate_better")
CONTACT_TOLERANCE = 0.035
MODEL_ORDER = (
    "action_geometry",
    "pooled_afterstate",
    "soft_topology_afterstate",
    "action_plus_soft_topology",
)


def _named(state: dict[str, Any], prefix: str) -> list[dict[str, float]]:
    names = state[f"{prefix}_features"]
    return [
        {name: float(value) for name, value in zip(names, row)}
        for row in state[f"{prefix}_values"]
    ]


def _extent(item: dict[str, float]) -> tuple[float, float, float]:
    dimensions = [item.get(name, 0.0) for name in ("length", "width", "height")]
    if "quaternion_w" not in item:
        return tuple(value / 2.0 for value in dimensions)
    x, y, z, w = (
        item.get(f"quaternion_{name}", 0.0) for name in ("x", "y", "z", "w")
    )
    rotation = (
        (1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)),
        (2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)),
        (2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)),
    )
    return tuple(
        sum(abs(rotation[row][column]) * dimensions[column] for column in range(3))
        / 2.0
        for row in range(3)
    )


def _overlap(first: dict[str, float], second: dict[str, float]) -> float:
    first_extent = _extent(first)
    second_extent = _extent(second)
    overlap_x = (
        first_extent[0] + second_extent[0]
        - abs(first.get("local_x", 0.0) - second.get("local_x", 0.0))
    )
    overlap_y = (
        first_extent[1] + second_extent[1]
        - abs(first.get("local_y", 0.0) - second.get("local_y", 0.0))
    )
    return max(0.0, overlap_x) * max(0.0, overlap_y)


def soft_topology_summary(state: dict[str, Any]) -> list[float]:
    """Compact rule-faithful geometry available from a physical afterstate."""
    containers = _named(state, "container")
    packed = _named(state, "packed_item")
    result: list[float] = []
    # The scenario contract currently has one or two containers.  Two fixed
    # slots keep the exported model shape stable for both cases.
    for container_index in range(2):
        current = [
            item for item in packed
            if int(item.get("container_index", -1)) == container_index
        ]
        soft_items = [item for item in current if bool(item.get("is_soft", 0.0))]
        ordinary = [item for item in current if not bool(item.get("is_soft", 0.0))]
        direct_pairs = stack_pairs = 0
        covered_direct = covered_stack = 0
        overlap_area = load_mass = 0.0
        positive_gaps: list[float] = []
        for protected in soft_items:
            protected_top = protected.get("local_z", 0.0) + _extent(protected)[2]
            has_direct = has_stack = False
            for upper in ordinary:
                area = _overlap(protected, upper)
                if area <= 0.0:
                    continue
                upper_bottom = upper.get("local_z", 0.0) - _extent(upper)[2]
                gap = upper_bottom - protected_top
                if gap < -CONTACT_TOLERANCE:
                    continue
                has_stack = True
                stack_pairs += 1
                overlap_area += area
                load_mass += upper.get("mass", 1.0)
                positive_gaps.append(max(0.0, gap))
                if abs(gap) <= CONTACT_TOLERANCE:
                    has_direct = True
                    direct_pairs += 1
            covered_direct += int(has_direct)
            covered_stack += int(has_stack)
        container = containers[container_index] if container_index < len(containers) else {}
        length = container.get("length", 1.0) or 1.0
        width = container.get("width", 1.0) or 1.0
        soft_tops = [item.get("local_z", 0.0) + _extent(item)[2] for item in soft_items]
        soft_wall_clearances = [
            min(
                length / 2.0 - abs(item.get("local_x", 0.0)) - _extent(item)[0],
                width / 2.0 - abs(item.get("local_y", 0.0)) - _extent(item)[1],
            )
            for item in soft_items
        ]
        result.extend([
            float(len(current)),
            float(len(soft_items)),
            float(len(ordinary)),
            float(covered_direct),
            float(direct_pairs),
            float(covered_stack),
            float(stack_pairs),
            overlap_area,
            load_mass,
            min(positive_gaps, default=max(length, width)),
            statistics.fmean(positive_gaps) if positive_gaps else max(length, width),
            statistics.fmean(soft_tops) if soft_tops else 0.0,
            max(soft_tops, default=0.0),
            min(soft_wall_clearances, default=min(length, width) / 2.0),
            statistics.fmean(soft_wall_clearances)
            if soft_wall_clearances else min(length, width) / 2.0,
        ])
    return result


def soft_topology_delta(
    row: dict[str, Any],
    pair: tuple[dict[str, Any], dict[str, Any]] | None = None,
) -> list[float]:
    lower, higher = pair or (
        row["lower_afterstate_tensor"], row["higher_afterstate_tensor"]
    )
    left = soft_topology_summary(lower)
    right = soft_topology_summary(higher)
    return [higher_value - lower_value for lower_value, higher_value in zip(left, right)]


def feature_sets() -> dict[str, Callable[[dict[str, Any]], list[float]]]:
    return {
        "action_geometry": lambda row: _features(
            row, include_action=True, include_afterstate=False
        ),
        "pooled_afterstate": _state_delta,
        "soft_topology_afterstate": soft_topology_delta,
        "action_plus_soft_topology": lambda row: _features(
            row, include_action=True, include_afterstate=False
        ) + soft_topology_delta(row),
    }


def _eligible(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        row for row in rows
        if row.get(LABEL_FAMILY, {}).get(METRIC, {}).get("relation") in DIRECTIONAL
    ]


def _correct(predictions: dict[str, str], rows: list[dict[str, Any]]) -> int:
    return sum(
        predictions.get(row["teacher_id"])
        == row[LABEL_FAMILY][METRIC]["relation"]
        for row in rows
    )


def _rotated_pairs(rows: list[dict[str, Any]], shift: int) -> dict[str, tuple[dict, dict]]:
    ordered = sorted(rows, key=lambda row: row["teacher_id"])
    pairs = [
        (row["lower_afterstate_tensor"], row["higher_afterstate_tensor"])
        for row in ordered
    ]
    return {
        row["teacher_id"]: pairs[(index + shift) % len(pairs)]
        for index, row in enumerate(ordered)
    }


def evaluate_discovery(rows: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
    eligible = _eligible(rows)
    groups = sorted({row["graph_id"] for row in eligible})
    if len(groups) < 2:
        raise ValueError("soft afterstate evaluation requires at least two directional graph groups")
    features = feature_sets()
    predictions = {name: {} for name in MODEL_ORDER}
    afterstate_candidates = (
        "pooled_afterstate",
        "soft_topology_afterstate",
        "action_plus_soft_topology",
    )
    permutation_predictions = {
        name: {shift: {} for shift in range(1, 8)}
        for name in afterstate_candidates
    }
    graph_results = []
    for group in groups:
        train = [row for row in eligible if row["graph_id"] != group]
        test = [row for row in eligible if row["graph_id"] == group]
        for name, values in features.items():
            predictions[name].update(
                _predict_ridge(train, test, METRIC, values, label_family=LABEL_FAMILY)
            )
        for shift in range(1, 8):
            rotated = _rotated_pairs(train, shift)
            for name in permutation_predictions:
                include_action = name == "action_plus_soft_topology"

                def permuted(row, *, rotated=rotated, include_action=include_action):
                    pair = rotated.get(row["teacher_id"])
                    if name == "pooled_afterstate":
                        return _state_delta(row, pair)
                    values = (
                        _features(row, include_action=True, include_afterstate=False)
                        if include_action else []
                    )
                    return values + soft_topology_delta(row, pair)

                permutation_predictions[name][shift].update(
                    _predict_ridge(
                        train, test, METRIC, permuted, label_family=LABEL_FAMILY
                    )
                )
        graph_results.append({"graph_id": group, "rows": len(test)})

    immediate = {
        row["teacher_id"]: "higher_afterstate_better" for row in eligible
    }
    model_counts = {
        "immediate_score": _correct(immediate, eligible),
        **{name: _correct(values, eligible) for name, values in predictions.items()},
    }
    permutation_counts = {
        name: [
            _correct(permutation_predictions[name][shift], eligible)
            for shift in range(1, 8)
        ]
        for name in permutation_predictions
    }
    candidates = afterstate_candidates
    selected = max(candidates, key=lambda name: (model_counts[name], -candidates.index(name)))
    graph_wins = graph_ties = graph_losses = 0
    for graph in graph_results:
        subset = [row for row in eligible if row["graph_id"] == graph["graph_id"]]
        selected_correct = _correct(predictions[selected], subset)
        action_correct = _correct(predictions["action_geometry"], subset)
        if selected_correct > action_correct:
            graph_wins += 1
        elif selected_correct < action_correct:
            graph_losses += 1
        else:
            graph_ties += 1
    gate = (
        model_counts[selected] > model_counts["immediate_score"]
        and model_counts[selected] > model_counts["action_geometry"]
        and model_counts[selected] > max(permutation_counts[selected])
        and graph_wins > graph_losses
    )
    report = {
        "schema_version": 1,
        "protocol": "discovery_only_leave_one_physical_graph_out",
        "late_holdout_accessed": False,
        "target": METRIC,
        "label_family": LABEL_FAMILY,
        "directional_rows": len(eligible),
        "graph_groups": len(groups),
        "models": {
            name: {"correct": correct, "total": len(eligible)}
            for name, correct in model_counts.items()
        },
        "permuted_afterstate_negative_control": {
            name: {
                "correct_by_shift": values,
                "minimum": min(values),
                "median": statistics.median(values),
                "maximum": max(values),
                "total": len(eligible),
            }
            for name, values in permutation_counts.items()
        },
        "selected_model": selected,
        "selected_vs_action_by_graph": {
            "wins": graph_wins, "ties": graph_ties, "losses": graph_losses,
        },
        "promotion_gate": {
            "passed": gate,
            "contract": (
                "selected strictly beats immediate score, action geometry, and "
                "all seven permuted-afterstate controls; graph wins exceed losses"
            ),
        },
    }
    policy = {
        "schema_version": 1,
        "target": METRIC,
        "label_family": LABEL_FAMILY,
        "selection_source": "discovery_only_leave_one_physical_graph_out",
        "late_holdout_accessed_for_selection": False,
        "status": "late_evaluation_licensed" if gate else "abstain_discovery_gate_failed",
        "selected_model": selected,
        "feature_contract": "physical_afterstate_soft_topology_v1",
        "model": fit_ridge_model(
            eligible, METRIC, features[selected], label_family=LABEL_FAMILY
        ),
        "discovery_evidence": report,
    }
    return report, policy


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Post-shake soft reranker: discovery gate", "",
        f"Directional rows / graph folds: **{report['directional_rows']} / {report['graph_groups']}**", "",
        "| Model | Correct |", "|---|---:|",
    ]
    for name, result in report["models"].items():
        lines.append(f"| {name} | {result['correct']}/{result['total']} |")
    selected = report["selected_model"]
    control = report["permuted_afterstate_negative_control"][selected]
    graph = report["selected_vs_action_by_graph"]
    lines.extend([
        "",
        f"Selected: **{selected}**. Permuted control min/median/max: "
        f"{control['minimum']}/{control['median']:g}/{control['maximum']}.",
        f"Graph wins/ties/losses versus action geometry: "
        f"{graph['wins']}/{graph['ties']}/{graph['losses']}.", "",
        f"Promotion gate: **{'PASS' if report['promotion_gate']['passed'] else 'FAIL'}**.", "",
    ])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--discovery", type=pathlib.Path, required=True)
    parser.add_argument("--json-output", type=pathlib.Path, required=True)
    parser.add_argument("--markdown-output", type=pathlib.Path, required=True)
    parser.add_argument("--policy-output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    report, policy = evaluate_discovery(_read_jsonl(args.discovery))
    for path in (args.json_output, args.markdown_output, args.policy_output):
        path.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    args.markdown_output.write_text(render_markdown(report), encoding="utf-8")
    args.policy_output.write_text(json.dumps(policy, indent=2) + "\n", encoding="utf-8")
    print(args.markdown_output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
