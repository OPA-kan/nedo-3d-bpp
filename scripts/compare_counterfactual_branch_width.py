"""Compare preregistered root-pair continuation labels across branch widths."""

from __future__ import annotations

import argparse
import json
import math
import pathlib
from typing import Any

try:
    from scripts.summarize_counterfactual_graph_signal import (
        METRIC_DIRECTIONS, _graph_index, _leaf_paths,
        _continuation_outcome_vectors,
    )
except ModuleNotFoundError:
    from summarize_counterfactual_graph_signal import (
        METRIC_DIRECTIONS, _graph_index, _leaf_paths,
        _continuation_outcome_vectors,
    )


def _relation(
    metric: str, lower: list[dict[str, Any]], higher: list[dict[str, Any]],
) -> tuple[str, float | int, float | int]:
    direction = METRIC_DIRECTIONS[metric]
    lower_values = [row[metric] for row in lower]
    higher_values = [row[metric] for row in higher]
    lower_best = max(lower_values) if direction > 0 else min(lower_values)
    higher_best = max(higher_values) if direction > 0 else min(higher_values)
    equal = (
        lower_best == higher_best if metric in (
            "placed_count", "priority_misrouted", "soft_covered_by_other"
        ) else math.isclose(
            float(lower_best), float(higher_best), rel_tol=0.0, abs_tol=1e-12
        )
    )
    if equal:
        relation = "equal"
    elif direction * (lower_best - higher_best) > 0:
        relation = "lower_afterstate_better"
    else:
        relation = "higher_afterstate_better"
    return relation, lower_best, higher_best


def compare_graph(graph: dict[str, Any], expected: dict[str, Any]) -> dict[str, Any]:
    nodes, outgoing, root_id = _graph_index(graph)
    root_edges = outgoing[root_id]
    by_item = {
        int(edge["selection"]["stable_item_index"]): edge
        for edge in root_edges
    }
    lower_id = int(expected["lower_stable_item_index"])
    higher_id = int(expected["higher_stable_item_index"])
    if lower_id not in by_item or higher_id not in by_item:
        raise ValueError(
            f"preregistered pair absent from B3 root: {lower_id}, {higher_id}"
        )
    lower_edge, higher_edge = by_item[lower_id], by_item[higher_id]
    lower_node = nodes[lower_edge["target"]]
    higher_node = nodes[higher_edge["target"]]
    lower = _continuation_outcome_vectors(
        _leaf_paths(lower_edge["target"], nodes, outgoing), lower_node
    )
    higher = _continuation_outcome_vectors(
        _leaf_paths(higher_edge["target"], nodes, outgoing), higher_node
    )
    relation, lower_best, higher_best = _relation(
        expected.get("metric", "fill_score_proxy"), lower, higher
    )
    expected_relation = expected["b2_relation"]
    return {
        "target_id": expected["target_id"],
        "case_id": graph["case_id"],
        "root_step": graph["root_step"],
        "stream_variant": graph["provenance"]["scenario_axes"]["stream_variant"],
        "b2_relation": expected_relation,
        "b3_relation": relation,
        "stable": relation == expected_relation,
        "lower_best_continuation": lower_best,
        "higher_best_continuation": higher_best,
        "lower_continuation_count": len(lower),
        "higher_continuation_count": len(higher),
    }


def evaluate(root: pathlib.Path, specification: dict[str, Any]) -> dict[str, Any]:
    graphs = [json.loads(path.read_text(encoding="utf-8")) for path in root.rglob("graph.json")]
    indexed = {
        (
            graph["provenance"]["scenario_axes"]["stream_variant"],
            graph["case_id"], int(graph["root_step"]),
        ): graph for graph in graphs
    }
    rows = []
    for target in specification["targets"]:
        key = (target["stream_variant"], target["case_id"], int(target["root_step"]))
        if key not in indexed:
            raise ValueError(f"missing preregistered B3 graph: {key}")
        rows.append(compare_graph(indexed[key], target))
    stable = sum(row["stable"] for row in rows)
    return {
        "schema_version": 1,
        "comparison_contract": "matched root sibling pair; H3 fixed; B2 versus B3",
        "target_count": len(rows),
        "stable_count": stable,
        "changed_count": len(rows) - stable,
        "all_relations_stable": stable == len(rows),
        "model_work_may_resume": stable == len(rows),
        "targets": rows,
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# H3 branch-width label stability", "",
        f"- Stable: {report['stable_count']}/{report['target_count']}",
        f"- Model work may resume: {'yes' if report['model_work_may_resume'] else 'no'}",
        "", "| Target | Variant | Case | B2 | B3 | Stable |", "|---|---|---|---|---|---|",
    ]
    for row in report["targets"]:
        lines.append(
            f"| {row['target_id']} | {row['stream_variant']} | {row['case_id']} | "
            f"{row['b2_relation']} | {row['b3_relation']} | "
            f"{'yes' if row['stable'] else 'no'} |"
        )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=pathlib.Path, required=True)
    parser.add_argument("--specification", type=pathlib.Path, required=True)
    parser.add_argument("--json-output", type=pathlib.Path, required=True)
    parser.add_argument("--markdown-output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    specification = json.loads(args.specification.read_text(encoding="utf-8"))
    report = evaluate(args.root, specification)
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    args.markdown_output.write_text(render_markdown(report), encoding="utf-8")
    print(args.markdown_output)
    return 0 if report["all_relations_stable"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
