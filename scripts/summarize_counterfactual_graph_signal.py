"""Measure bounded-H3 outcome separation without inventing a total score."""

from __future__ import annotations

import argparse
import collections
import itertools
import json
import pathlib
from typing import Any, Iterable


METRIC_DIRECTIONS = {
    "placed_count": 1,
    "fill_score_proxy": 1,
    "com_z": -1,
    "surface_total_variation": -1,
    "priority_misrouted": -1,
    "soft_covered_by_other": -1,
}

POST_SHAKE_METRIC_DIRECTIONS = {
    "post_shake_items_lost": -1,
    "post_shake_max_shift": -1,
    "post_shake_max_rotation_deg": -1,
    "post_shake_items_shifted": -1,
    "post_shake_items_toppled": -1,
    "post_shake_peak_kinetic_energy": -1,
    "post_shake_priority_covered_by_other": -1,
    "post_shake_priority_misrouted": -1,
    "post_shake_soft_covered_by_other": -1,
    "post_shake_soft_clean_to_covered_events": -1,
}

ACTION_TENSOR_FEATURES = (
    "container_index", "command_x", "command_y", "command_z",
    "orientation", "is_release_candidate", "immediate_score",
)


def _action_tensor(
    edge: dict[str, Any], source_state_tensor: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Join a replayable candidate action to its observed item features."""
    if not isinstance(source_state_tensor, dict):
        return None
    stable_item_index = edge.get("selection", {}).get("stable_item_index")
    visible_indices = source_state_tensor.get("visible_item_indices", [])
    visible_values = source_state_tensor.get("visible_item_values", [])
    try:
        item_offset = visible_indices.index(stable_item_index)
        item_values = [float(value) for value in visible_values[item_offset]]
    except (ValueError, IndexError, TypeError):
        return None
    action = edge.get("command_action", {})
    place_pos = action.get("place_pos")
    if not isinstance(place_pos, list) or len(place_pos) != 3:
        return None
    selection = edge.get("selection", {})
    return {
        "schema_version": 1,
        "contract": "observed_candidate_action_no_future_labels",
        "coordinate_frame": "official_command",
        "feature_names": list(ACTION_TENSOR_FEATURES)
        + list(source_state_tensor.get("visible_item_features", [])),
        "values": [
            float(action["container_idx"]),
            *[float(value) for value in place_pos],
            float(action["orientation"]),
            float(selection.get("candidate_kind") == "release_candidate"),
            float(selection["score"]),
            *item_values,
        ],
        "stable_item_index": int(stable_item_index),
    }


def _graph_index(graph: dict[str, Any]):
    nodes = {node["node_id"]: node for node in graph.get("nodes", [])}
    outgoing: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    incoming = set()
    for edge in graph.get("edges", []):
        outgoing[edge["source"]].append(edge)
        incoming.add(edge["target"])
    roots = [node_id for node_id in nodes if node_id not in incoming]
    if len(roots) != 1:
        raise ValueError(f"expected one graph root, found {len(roots)}")
    return nodes, outgoing, roots[0]


def _leaf_paths(
    start: str,
    nodes: dict[str, dict[str, Any]],
    outgoing: dict[str, list[dict[str, Any]]],
) -> list[tuple[list[dict[str, Any]], dict[str, Any]]]:
    paths = []
    stack = [(start, [])]
    while stack:
        node_id, edges = stack.pop()
        children = outgoing.get(node_id, [])
        if not children:
            paths.append((edges, nodes[node_id]))
            continue
        for edge in children:
            stack.append((edge["target"], edges + [edge]))
    return paths


def _metric_ranges(
    paths: list[tuple[list[dict[str, Any]], dict[str, Any]]],
    metric_directions: dict[str, int] = METRIC_DIRECTIONS,
) -> dict[str, list[float | int]]:
    ranges = {}
    for metric in metric_directions:
        values = [
            leaf.get("cumulative_outcomes", {}).get(metric)
            for _edges, leaf in paths
        ]
        if values and all(value is not None for value in values):
            ranges[metric] = [min(values), max(values)]
    return ranges


def _outcome_vectors(
    paths: list[tuple[list[dict[str, Any]], dict[str, Any]]],
    metric_directions: dict[str, int] = METRIC_DIRECTIONS,
) -> list[dict[str, float | int]]:
    vectors = []
    seen = set()
    for _edges, leaf in paths:
        outcomes = leaf.get("cumulative_outcomes", {})
        if not all(metric in outcomes for metric in metric_directions):
            continue
        vector = {
            metric: outcomes[metric] for metric in metric_directions
        }
        identity = tuple(vector.items())
        if identity not in seen:
            seen.add(identity)
            vectors.append(vector)
    return vectors


def _continuation_outcome_vectors(
    paths: list[tuple[list[dict[str, Any]], dict[str, Any]]],
    afterstate: dict[str, Any],
    metric_directions: dict[str, int] = METRIC_DIRECTIONS,
) -> list[dict[str, float | int]]:
    """Return leaf gains after the first action, excluding its immediate effect."""
    baseline = afterstate.get("cumulative_outcomes", {})
    vectors = []
    seen = set()
    for _edges, leaf in paths:
        outcomes = leaf.get("cumulative_outcomes", {})
        if not all(
            metric in outcomes and metric in baseline
            for metric in metric_directions
        ):
            continue
        vector = {
            metric: outcomes[metric] - baseline[metric]
            for metric in metric_directions
        }
        identity = tuple(vector.items())
        if identity not in seen:
            seen.add(identity)
            vectors.append(vector)
    return vectors


def _continuation_samples(
    paths: list[tuple[list[dict[str, Any]], dict[str, Any]]],
    afterstate: dict[str, Any],
    outgoing: dict[str, list[dict[str, Any]]],
    *,
    horizon: int,
    metric_directions: dict[str, int] = METRIC_DIRECTIONS,
) -> list[dict[str, Any]]:
    """Preserve one continuation sample per searched leaf, including failures.

    Unlike ``_continuation_outcome_vectors``, this intentionally retains
    duplicate outcomes. Each sample carries the probability induced by
    choosing uniformly among the searched children at every future node.
    This is a declared search policy, not an environment probability.
    """
    baseline = afterstate.get("cumulative_outcomes", {})
    samples = []
    for edges, leaf in paths:
        outcomes = leaf.get("cumulative_outcomes", {})
        if not all(
            metric in outcomes and metric in baseline
            for metric in metric_directions
        ):
            continue
        reason = leaf.get("terminal_reason")
        if reason is None and int(leaf.get("depth", 0)) >= horizon:
            reason = "horizon"
        search_policy_weight = 1.0
        for edge in edges:
            branch_count = len(outgoing.get(edge["source"], []))
            if branch_count:
                search_policy_weight /= branch_count
        samples.append({
            "leaf_node_id": leaf.get("node_id"),
            "terminal_reason": reason or "open_leaf",
            "path_stable_item_indices": [
                edge.get("selection", {}).get("stable_item_index")
                for edge in edges
            ],
            "search_policy_weight": search_policy_weight,
            "outcomes": {
                metric: outcomes[metric] - baseline[metric]
                for metric in metric_directions
            },
        })
    return samples


def _ranges_differ(comparisons: dict[str, Any]) -> bool:
    return any(
        row["lower_range"] != row["higher_range"]
        for row in comparisons.values()
    )


def _summarize_sibling_pair(
    source_id: str, lower: dict[str, Any], higher: dict[str, Any],
    nodes: dict[str, dict[str, Any]],
    outgoing: dict[str, list[dict[str, Any]]], *,
    include_afterstate_tensors: bool,
    horizon: int,
    metric_directions: dict[str, int],
) -> dict[str, Any]:
        lower_paths = _leaf_paths(lower["target"], nodes, outgoing)
        higher_paths = _leaf_paths(higher["target"], nodes, outgoing)
        lower_ranges = _metric_ranges(lower_paths, metric_directions)
        higher_ranges = _metric_ranges(higher_paths, metric_directions)
        lower_vectors = _outcome_vectors(lower_paths, metric_directions)
        higher_vectors = _outcome_vectors(higher_paths, metric_directions)
        lower_afterstate = nodes[lower["target"]]
        higher_afterstate = nodes[higher["target"]]
        lower_continuation_vectors = _continuation_outcome_vectors(
            lower_paths, lower_afterstate, metric_directions
        )
        higher_continuation_vectors = _continuation_outcome_vectors(
            higher_paths, higher_afterstate, metric_directions
        )
        lower_continuation_samples = _continuation_samples(
            lower_paths, lower_afterstate, outgoing, horizon=horizon,
            metric_directions=metric_directions,
        )
        higher_continuation_samples = _continuation_samples(
            higher_paths, higher_afterstate, outgoing, horizon=horizon,
            metric_directions=metric_directions,
        )
        score_gap = float(higher["selection"]["score"]) - float(
            lower["selection"]["score"]
        )
        comparisons = {}
        for metric, direction in metric_directions.items():
            if metric not in lower_ranges or metric not in higher_ranges:
                continue
            lower_range = lower_ranges[metric]
            higher_range = higher_ranges[metric]
            lower_best = lower_range[1] if direction > 0 else lower_range[0]
            higher_best = higher_range[1] if direction > 0 else higher_range[0]
            better = score_gap > 0.0 and (
                lower_best > higher_best
                if direction > 0
                else lower_best < higher_best
            )
            comparisons[metric] = {
                "lower_range": lower_range,
                "higher_range": higher_range,
                "lower_score_has_better_reachable_leaf": better,
            }
        source_state_tensor = nodes[source_id].get("state_tensor")
        sibling_row = {
            "source_node_id": source_id,
            "source_depth": int(nodes[source_id]["depth"]),
            "source_state_tensor": source_state_tensor,
            "lower_action_tensor": _action_tensor(lower, source_state_tensor),
            "higher_action_tensor": _action_tensor(higher, source_state_tensor),
            "lower_reachable_outcome_vectors": lower_vectors,
            "higher_reachable_outcome_vectors": higher_vectors,
            "lower_continuation_outcome_vectors": lower_continuation_vectors,
            "higher_continuation_outcome_vectors": higher_continuation_vectors,
            "lower_continuation_samples": lower_continuation_samples,
            "higher_continuation_samples": higher_continuation_samples,
            "score_gap": score_gap,
            "equal_immediate_score": score_gap == 0.0,
            "downstream_ranges_differ": _ranges_differ(comparisons),
            "lower_stable_item_index": lower["selection"].get(
                "stable_item_index"
            ),
            "higher_stable_item_index": higher["selection"].get(
                "stable_item_index"
            ),
            "comparisons": comparisons,
        }
        if include_afterstate_tensors:
            sibling_row["lower_afterstate_tensor"] = lower_afterstate.get(
                "state_tensor"
            )
            sibling_row["higher_afterstate_tensor"] = higher_afterstate.get(
                "state_tensor"
            )
        return sibling_row


def summarize_graph_signal(
    graph: dict[str, Any], *, source: str,
    include_afterstate_tensors: bool = False,
) -> dict[str, Any]:
    nodes, outgoing, root_id = _graph_index(graph)
    paths = _leaf_paths(root_id, nodes, outgoing)
    horizon = int(graph.get("budget", {}).get("horizon", 3))
    metric_directions = dict(METRIC_DIRECTIONS)
    if graph.get("provenance", {}).get("post_shake_labels"):
        outcome_keys = set.intersection(*(
            set(node.get("cumulative_outcomes", {}))
            for node in nodes.values()
        ))
        metric_directions.update({
            metric: direction
            for metric, direction in POST_SHAKE_METRIC_DIRECTIONS.items()
            if metric in outcome_keys
        })
    sibling_rows = []
    lower_score_better = collections.Counter()
    for source_id, edges in outgoing.items():
        if len(edges) < 2:
            continue
        ordered_edges = sorted(
            edges,
            key=lambda edge: (
                float(edge["selection"]["score"]),
                int(edge["selection"].get("stable_item_index", -1)),
            ),
        )
        for lower, higher in itertools.combinations(ordered_edges, 2):
            sibling_row = _summarize_sibling_pair(
                source_id, lower, higher, nodes, outgoing,
                include_afterstate_tensors=include_afterstate_tensors,
                horizon=horizon,
                metric_directions=metric_directions,
            )
            sibling_rows.append(sibling_row)
            for metric, comparison in sibling_row["comparisons"].items():
                if comparison["lower_score_has_better_reachable_leaf"]:
                    lower_score_better[metric] += 1
    terminal_reasons = collections.Counter(
        leaf.get("terminal_reason")
        or ("horizon" if int(leaf["depth"]) >= horizon else "open_leaf")
        for _edges, leaf in paths
    )
    equal = [row for row in sibling_rows if row["equal_immediate_score"]]
    unequal = [row for row in sibling_rows if not row["equal_immediate_score"]]
    return {
        "source": source,
        "graph_id": graph.get("graph_id"),
        "case_id": graph.get("case_id"),
        "root_step": graph.get("root_step"),
        "horizon": horizon,
        "branch_factor": int(graph.get("budget", {}).get("branch_factor", 0)),
        "commit": graph.get("provenance", {}).get("commit"),
        "scenario_axes": graph.get("provenance", {}).get(
            "scenario_axes", {}
        ),
        "metric_directions": metric_directions,
        "edges": len(graph.get("edges", [])),
        "physically_failed_edges": sum(
            not bool(edge.get("immediate_outcomes", {}).get("is_placed_safe"))
            for edge in graph.get("edges", [])
        ),
        "terminal_trajectory_count": len(paths),
        "terminal_reasons": dict(sorted(terminal_reasons.items())),
        "terminal_outcome_ranges": _metric_ranges(paths, metric_directions),
        "sibling_pair_count": len(sibling_rows),
        "equal_immediate_score_pairs": len(equal),
        "equal_score_pairs_with_different_downstream_ranges": sum(
            row["downstream_ranges_differ"] for row in equal
        ),
        "unequal_score_pairs_with_different_downstream_ranges": sum(
            row["downstream_ranges_differ"] for row in unequal
        ),
        "lower_score_better_reachable_leaf_counts": {
            metric: lower_score_better[metric]
            for metric in metric_directions
        },
        "sibling_pairs": sibling_rows,
    }


def summarize_paths(
    paths: Iterable[pathlib.Path], *, run_id: str | None = None,
    include_afterstate_tensors: bool = False,
) -> dict[str, Any]:
    graphs = [
        summarize_graph_signal(
            json.loads(path.read_text(encoding="utf-8")),
            source=path.as_posix(),
            include_afterstate_tensors=include_afterstate_tensors,
        )
        for path in sorted(paths)
    ]
    terminal_reasons = collections.Counter()
    lower_score_better = collections.Counter()
    metric_directions = dict(METRIC_DIRECTIONS)
    for graph in graphs:
        terminal_reasons.update(graph["terminal_reasons"])
        metric_directions.update(graph.get("metric_directions", {}))
        lower_score_better.update(
            graph["lower_score_better_reachable_leaf_counts"]
        )
    equal_count = sum(
        graph["equal_immediate_score_pairs"] for graph in graphs
    )
    equal_separated = sum(
        graph["equal_score_pairs_with_different_downstream_ranges"]
        for graph in graphs
    )
    unequal_separated = sum(
        graph["unequal_score_pairs_with_different_downstream_ranges"]
        for graph in graphs
    )
    partitions = {}
    for name, selected in (
        ("discovery_step_lt_15", [
            graph for graph in graphs if int(graph["root_step"]) < 15
        ]),
        ("late_holdout_step_ge_15", [
            graph for graph in graphs if int(graph["root_step"]) >= 15
        ]),
    ):
        partitions[name] = {
            "graph_count": len(selected),
            "graphs_with_edges": sum(graph["edges"] > 0 for graph in selected),
            "sibling_pair_count": sum(
                graph["sibling_pair_count"] for graph in selected
            ),
            "unequal_score_pairs_with_different_downstream_ranges": sum(
                graph[
                    "unequal_score_pairs_with_different_downstream_ranges"
                ]
                for graph in selected
            ),
            "score_order_counterexample_observed": any(
                any(
                    graph["lower_score_better_reachable_leaf_counts"].values()
                )
                for graph in selected
            ),
        }
    readiness_gates = {
        "minimum_16_graphs": len(graphs) >= 16,
        "terminal_label_coverage": bool(
            terminal_reasons.get("physical_failure")
            or terminal_reasons.get("no_candidate")
        ),
        "discovery_score_order_counterexample": partitions[
            "discovery_step_lt_15"
        ]["score_order_counterexample_observed"],
        "late_holdout_score_order_counterexample": partitions[
            "late_holdout_step_ge_15"
        ]["score_order_counterexample_observed"],
        "exact_score_future_separation": equal_separated > 0,
    }
    ready = all(readiness_gates.values())
    return {
        "schema_version": 1,
        "run_id": run_id,
        "commits": sorted({
            graph["commit"] for graph in graphs if graph["commit"]
        }),
        "status": "bounded_h3_signal_measured" if graphs else "empty",
        "horizons": sorted({
            int(graph.get("horizon", 0))
            for graph in graphs
            if graph.get("horizon") is not None
        }),
        "branch_factors": sorted({
            int(graph.get("branch_factor", 0))
            for graph in graphs
            if graph.get("branch_factor") is not None
        }),
        "training_readiness": (
            "h3_teacher_baseline_ready"
            if ready
            else "not_established_preregistered_gates_failed"
        ),
        "readiness_gates": readiness_gates,
        "root_step_partitions": partitions,
        "graph_count": len(graphs),
        "condition_count": len({
            (
                graph["case_id"],
                json.dumps(graph["scenario_axes"], sort_keys=True),
            )
            for graph in graphs
        }),
        "graphs_with_edges": sum(graph["edges"] > 0 for graph in graphs),
        "total_edges": sum(graph["edges"] for graph in graphs),
        "physically_failed_edges": sum(
            graph["physically_failed_edges"] for graph in graphs
        ),
        "terminal_trajectory_count": sum(
            graph["terminal_trajectory_count"] for graph in graphs
        ),
        "terminal_reasons": dict(sorted(terminal_reasons.items())),
        "sibling_pair_count": sum(
            graph["sibling_pair_count"] for graph in graphs
        ),
        "equal_immediate_score_pairs": equal_count,
        "equal_score_pairs_with_different_downstream_ranges": equal_separated,
        "unequal_score_pairs_with_different_downstream_ranges": (
            unequal_separated
        ),
        "lower_score_better_reachable_leaf_counts": {
            metric: lower_score_better[metric]
            for metric in metric_directions
        },
        "findings": {
            "terminal_label_coverage_observed": bool(
                terminal_reasons.get("physical_failure")
                or terminal_reasons.get("no_candidate")
            ),
            "score_order_counterexample_observed": any(
                lower_score_better.values()
            ),
            "equal_score_future_separation_observed": equal_separated > 0,
        },
        "graphs": graphs,
    }


def render_markdown(summary: dict[str, Any]) -> str:
    reasons = ", ".join(
        f"{key}:{value}" for key, value in summary["terminal_reasons"].items()
    ) or "-"
    lower = ", ".join(
        f"{key}:{value}"
        for key, value in summary[
            "lower_score_better_reachable_leaf_counts"
        ].items()
        if value
    ) or "none"
    lines = [
        "# Bounded counterfactual teacher-signal audit",
        "",
        f"- Graphs / graphs with edges: {summary['graph_count']} / "
        f"{summary['graphs_with_edges']}",
        f"- Conditions: {summary['condition_count']}",
        f"- Edges / failed physical edges: {summary['total_edges']} / "
        f"{summary['physically_failed_edges']}",
        f"- Terminal trajectories: {summary['terminal_trajectory_count']} "
        f"({reasons})",
        f"- Sibling pairs: {summary['sibling_pair_count']}",
        f"- Equal-immediate-score pairs with different recorded downstream "
        f"ranges: {summary['equal_score_pairs_with_different_downstream_ranges']}"
        f" / {summary['equal_immediate_score_pairs']}",
        f"- Unequal-score pairs with different downstream ranges: "
        f"{summary['unequal_score_pairs_with_different_downstream_ranges']}",
        f"- Lower-score action had a better reachable leaf: {lower}",
        f"- Training readiness: {summary['training_readiness']}.",
        "- Root-step split is preregistered as discovery <15 and late "
        "holdout >=15.",
        "",
        "| case | step | edges | terminal trajectories | terminals | siblings | "
        "equal score separated | unequal score separated |",
        "|---|---:|---:|---:|---|---:|---:|---:|",
    ]
    for graph in summary["graphs"]:
        terminals = ", ".join(
            f"{key}:{value}"
            for key, value in graph["terminal_reasons"].items()
        ) or "-"
        lines.append(
            f"| {graph['case_id']} | {graph['root_step']} | {graph['edges']} | "
            f"{graph['terminal_trajectory_count']} | {terminals} | "
            f"{graph['sibling_pair_count']} | "
            f"{graph['equal_score_pairs_with_different_downstream_ranges']} / "
            f"{graph['equal_immediate_score_pairs']} | "
            f"{graph['unequal_score_pairs_with_different_downstream_ranges']} |"
        )
    lines.extend([
        "",
        "This audit keeps placed, fill, CoG, surface variation, priority and "
        "soft-item outcomes separate. A 'better reachable leaf' is an "
        "existence result inside the bounded graph, not a probability, a "
        "competition-score total, or a learned value estimate.",
        "",
    ])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=pathlib.Path, required=True)
    parser.add_argument("--json-output", type=pathlib.Path, required=True)
    parser.add_argument("--markdown-output", type=pathlib.Path, required=True)
    parser.add_argument("--expected-graphs", type=int)
    parser.add_argument("--minimum-graphs", type=int)
    parser.add_argument("--expected-conditions", type=int)
    parser.add_argument("--run-id")
    parser.add_argument("--include-afterstate-tensors", action="store_true")
    args = parser.parse_args()
    paths = list(args.root.rglob("graph.json"))
    if not paths:
        raise SystemExit(f"no graph.json files below {args.root}")
    if args.expected_graphs is not None and len(paths) != args.expected_graphs:
        raise SystemExit(
            f"expected {args.expected_graphs} graphs, found {len(paths)}; "
            "refusing to audit a partial matrix"
        )
    summary = summarize_paths(
        paths, run_id=args.run_id,
        include_afterstate_tensors=args.include_afterstate_tensors,
    )
    if args.minimum_graphs is not None and len(paths) < args.minimum_graphs:
        raise SystemExit(
            f"expected at least {args.minimum_graphs} graphs, found "
            f"{len(paths)}; refusing to audit an undersized matrix"
        )
    if (
        args.expected_conditions is not None
        and summary["condition_count"] != args.expected_conditions
    ):
        raise SystemExit(
            f"expected {args.expected_conditions} conditions, found "
            f"{summary['condition_count']}; refusing to audit a partial "
            "condition matrix"
        )
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    args.markdown_output.write_text(
        render_markdown(summary), encoding="utf-8"
    )
    print(args.markdown_output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
