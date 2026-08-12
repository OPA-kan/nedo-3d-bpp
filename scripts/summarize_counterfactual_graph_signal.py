"""Measure bounded-H3 outcome separation without inventing a total score."""

from __future__ import annotations

import argparse
import collections
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
) -> dict[str, list[float | int]]:
    ranges = {}
    for metric in METRIC_DIRECTIONS:
        values = [
            leaf.get("cumulative_outcomes", {}).get(metric)
            for _edges, leaf in paths
        ]
        if values and all(value is not None for value in values):
            ranges[metric] = [min(values), max(values)]
    return ranges


def _ranges_differ(comparisons: dict[str, Any]) -> bool:
    return any(
        row["lower_range"] != row["higher_range"]
        for row in comparisons.values()
    )


def summarize_graph_signal(graph: dict[str, Any], *, source: str) -> dict[str, Any]:
    nodes, outgoing, root_id = _graph_index(graph)
    paths = _leaf_paths(root_id, nodes, outgoing)
    horizon = int(graph.get("budget", {}).get("horizon", 3))
    sibling_rows = []
    lower_score_better = collections.Counter()
    for source_id, edges in outgoing.items():
        if len(edges) != 2:
            continue
        lower, higher = sorted(
            edges, key=lambda edge: float(edge["selection"]["score"])
        )
        lower_paths = _leaf_paths(lower["target"], nodes, outgoing)
        higher_paths = _leaf_paths(higher["target"], nodes, outgoing)
        lower_ranges = _metric_ranges(lower_paths)
        higher_ranges = _metric_ranges(higher_paths)
        score_gap = float(higher["selection"]["score"]) - float(
            lower["selection"]["score"]
        )
        comparisons = {}
        for metric, direction in METRIC_DIRECTIONS.items():
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
            if better:
                lower_score_better[metric] += 1
        sibling_rows.append({
            "source_node_id": source_id,
            "source_depth": int(nodes[source_id]["depth"]),
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
        })
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
        "commit": graph.get("provenance", {}).get("commit"),
        "scenario_axes": graph.get("provenance", {}).get(
            "scenario_axes", {}
        ),
        "edges": len(graph.get("edges", [])),
        "physically_failed_edges": sum(
            not bool(edge.get("immediate_outcomes", {}).get("is_placed_safe"))
            for edge in graph.get("edges", [])
        ),
        "terminal_trajectory_count": len(paths),
        "terminal_reasons": dict(sorted(terminal_reasons.items())),
        "terminal_outcome_ranges": _metric_ranges(paths),
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
            for metric in METRIC_DIRECTIONS
        },
        "sibling_pairs": sibling_rows,
    }


def summarize_paths(
    paths: Iterable[pathlib.Path], *, run_id: str | None = None
) -> dict[str, Any]:
    graphs = [
        summarize_graph_signal(
            json.loads(path.read_text(encoding="utf-8")),
            source=path.as_posix(),
        )
        for path in sorted(paths)
    ]
    terminal_reasons = collections.Counter()
    lower_score_better = collections.Counter()
    for graph in graphs:
        terminal_reasons.update(graph["terminal_reasons"])
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
    return {
        "schema_version": 1,
        "run_id": run_id,
        "commits": sorted({
            graph["commit"] for graph in graphs if graph["commit"]
        }),
        "status": "bounded_h3_signal_measured" if graphs else "empty",
        "training_readiness": "not_established_small_condition_matrix",
        "graph_count": len(graphs),
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
            for metric in METRIC_DIRECTIONS
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
        "# Bounded H3 teacher-signal audit",
        "",
        f"- Graphs / graphs with edges: {summary['graph_count']} / "
        f"{summary['graphs_with_edges']}",
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
        "- Training readiness: not established by this small condition matrix.",
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
    parser.add_argument("--run-id")
    args = parser.parse_args()
    paths = list(args.root.rglob("graph.json"))
    if not paths:
        raise SystemExit(f"no graph.json files below {args.root}")
    if args.expected_graphs is not None and len(paths) != args.expected_graphs:
        raise SystemExit(
            f"expected {args.expected_graphs} graphs, found {len(paths)}; "
            "refusing to audit a partial matrix"
        )
    summary = summarize_paths(paths, run_id=args.run_id)
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
