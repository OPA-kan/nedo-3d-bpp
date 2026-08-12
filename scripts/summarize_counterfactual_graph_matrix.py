"""Summarize bounded physical graphs without pooling scenario conditions."""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
from typing import Any, Iterable


def _range(values: Iterable[Any]) -> dict[str, float | None]:
    numeric = [
        float(value)
        for value in values
        if isinstance(value, (int, float)) and not isinstance(value, bool)
    ]
    return {
        "min": min(numeric) if numeric else None,
        "max": max(numeric) if numeric else None,
    }


def summarize_graph(graph: dict[str, Any], *, source: str) -> dict[str, Any]:
    nodes = list(graph.get("nodes", []))
    edges = list(graph.get("edges", []))
    depth_counts = collections.Counter(int(node["depth"]) for node in nodes)
    terminal_counts = collections.Counter(
        node["terminal_reason"]
        for node in nodes
        if node.get("terminal_reason")
    )
    safe = sum(
        bool(edge.get("immediate_outcomes", {}).get("is_placed_safe"))
        for edge in edges
    )
    stable_items = {
        edge.get("selection", {}).get("stable_item_index")
        for edge in edges
        if edge.get("selection", {}).get("stable_item_index") is not None
    }
    cumulative = [node.get("cumulative_outcomes", {}) for node in nodes]
    immediate = [edge.get("immediate_outcomes", {}) for edge in edges]
    return {
        "source": source,
        "graph_id": graph.get("graph_id"),
        "case_id": graph.get("case_id"),
        "root_step": graph.get("root_step"),
        "scenario_axes": graph.get("provenance", {}).get(
            "scenario_axes", {}
        ),
        "horizon": graph.get("budget", {}).get("horizon"),
        "branch_factor": graph.get("budget", {}).get("branch_factor"),
        "nodes": len(nodes),
        "edges": len(edges),
        "nodes_by_depth": {
            str(depth): depth_counts[depth] for depth in sorted(depth_counts)
        },
        "physically_safe_edges": safe,
        "physically_failed_edges": len(edges) - safe,
        "distinct_stable_items": len(stable_items),
        "terminal_reasons": dict(sorted(terminal_counts.items())),
        "ranges": {
            "placed_count": _range(
                row.get("placed_count") for row in cumulative
            ),
            "fill_score_proxy": _range(
                row.get("fill_score_proxy") for row in cumulative
            ),
            "com_z": _range(row.get("com_z") for row in cumulative),
            "surface_total_variation": _range(
                row.get("surface_total_variation") for row in cumulative
            ),
            "priority_misrouted": _range(
                row.get("priority_misrouted") for row in cumulative
            ),
            "soft_covered_by_other": _range(
                row.get("soft_covered_by_other") for row in cumulative
            ),
            "settle_angle_deg": _range(
                row.get("settle_angle_deg") for row in immediate
            ),
            "settle_displacement_norm": _range(
                row.get("settle_displacement_norm") for row in immediate
            ),
        },
    }


def summarize_paths(paths: Iterable[pathlib.Path]) -> dict[str, Any]:
    rows = [
        summarize_graph(
            json.loads(path.read_text(encoding="utf-8")),
            source=path.as_posix(),
        )
        for path in sorted(paths)
    ]
    axes = {
        key: sorted({
            row["scenario_axes"][key]
            for row in rows
            if key in row["scenario_axes"]
        })
        for key in (
            "container_count",
            "shelf_count",
            "dedicated_container_count",
            "preloaded_item_count",
            "pool_width",
            "stream_item_count",
        )
        if any(key in row["scenario_axes"] for row in rows)
    }
    return {
        "schema_version": 1,
        "status": "complete" if rows else "empty",
        "graph_count": len(rows),
        "condition_coverage": axes,
        "total_edges": sum(row["edges"] for row in rows),
        "physically_safe_edges": sum(
            row["physically_safe_edges"] for row in rows
        ),
        "physically_failed_edges": sum(
            row["physically_failed_edges"] for row in rows
        ),
        "graphs": rows,
    }


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# Counterfactual graph condition matrix",
        "",
        f"- Graphs: {summary['graph_count']}",
        f"- Edges: {summary['total_edges']}",
        f"- Physical safe / failed: {summary['physically_safe_edges']} / "
        f"{summary['physically_failed_edges']}",
        "- These synthetic scenarios measure condition coverage; their proxy "
        "scores are not mutually score-comparable.",
        "",
        "| case | step | containers | shelves | preload | dedicated | pool | "
        "nodes | edges | safe | failed | items | terminal reasons |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in summary["graphs"]:
        axes = row["scenario_axes"]
        terminals = ", ".join(
            f"{key}:{value}"
            for key, value in row["terminal_reasons"].items()
        ) or "-"
        lines.append(
            f"| {row['case_id']} | {row['root_step']} | "
            f"{axes.get('container_count', '-')} | "
            f"{axes.get('shelf_count', '-')} | "
            f"{axes.get('preloaded_item_count', '-')} | "
            f"{axes.get('dedicated_container_count', '-')} | "
            f"{axes.get('pool_width', '-')} | {row['nodes']} | "
            f"{row['edges']} | {row['physically_safe_edges']} | "
            f"{row['physically_failed_edges']} | "
            f"{row['distinct_stable_items']} | {terminals} |"
        )
    lines.extend([
        "",
        "The JSON companion retains separate ranges for placed count, fill, "
        "CoG, surface variation, priority, soft-item, rotation, and displacement "
        "labels. No single proxy is treated as the competition score.",
        "",
    ])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=pathlib.Path, required=True)
    parser.add_argument("--json-output", type=pathlib.Path, required=True)
    parser.add_argument("--markdown-output", type=pathlib.Path, required=True)
    parser.add_argument("--expected-graphs", type=int)
    args = parser.parse_args()
    paths = list(args.root.rglob("graph.json"))
    if not paths:
        raise SystemExit(f"no graph.json files below {args.root}")
    if args.expected_graphs is not None and len(paths) != args.expected_graphs:
        raise SystemExit(
            f"expected {args.expected_graphs} graphs, found {len(paths)}; "
            "refusing to publish a partial matrix"
        )
    summary = summarize_paths(paths)
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
