"""Measure state diversity and H1/H3 reversals across behavior policies."""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import sys
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.counterfactual_graph import stable_id
from scripts.evaluate_budgeted_dag_search import evaluate_graph


def _root(graph: dict[str, Any]) -> dict[str, Any]:
    roots = [node for node in graph.get("nodes", []) if int(node.get("depth", -1)) == 0]
    if len(roots) != 1:
        raise ValueError(f"expected one depth-0 root, found {len(roots)}")
    return roots[0]


def evaluate_diversity(graphs: list[dict[str, Any]]) -> dict[str, Any]:
    rows = []
    for graph in graphs:
        root = _root(graph)
        provenance = graph.get("provenance", {})
        behavior = provenance.get("behavior_policy") or {}
        result = evaluate_graph(graph, simulation_budgets=[], cpuct_values=[])
        eligible = bool(
            result["oracle"]["best_value"] is not None
            and result["oracle"]["root_action_count"] >= 2
        )
        rows.append({
            "graph_id": graph.get("graph_id"),
            "case_id": graph.get("case_id"),
            "root_step": int(graph.get("root_step", 0)),
            "behavior_mode": behavior.get("mode", "unknown"),
            "environment_seed": behavior.get("environment_seed"),
            "future_stream_id": graph.get("future_stream_id"),
            "board_fingerprint": root.get("board_fingerprint"),
            "model_visible_state_signature": (
                provenance.get("model_visible_state_signature")
                or stable_id("model-state", root.get("state_tensor"))
            ),
            "eligible": eligible,
            "future_sensitive": bool(eligible and result["future_sensitive"]),
            "root_action_count": result["oracle"]["root_action_count"],
        })

    grouped: dict[tuple[str, int, Any, Any], list[dict[str, Any]]] = (
        collections.defaultdict(list)
    )
    for row in rows:
        grouped[(
            row["case_id"], row["root_step"], row["environment_seed"],
            row["future_stream_id"],
        )].append(row)
    groups = []
    for (case_id, root_step, environment_seed, future_stream_id), members in sorted(
        grouped.items(), key=lambda pair: tuple(str(value) for value in pair[0])
    ):
        baseline = next((row for row in members if row["behavior_mode"] == "baseline"), None)
        alternatives = [row for row in members if row["behavior_mode"] != "baseline"]
        groups.append({
            "case_id": case_id,
            "root_step": root_step,
            "environment_seed": environment_seed,
            "future_stream_id": future_stream_id,
            "trajectory_count": len(members),
            "behavior_modes": sorted(row["behavior_mode"] for row in members),
            "unique_board_fingerprints": len({row["board_fingerprint"] for row in members}),
            "unique_board_rate": len({row["board_fingerprint"] for row in members}) / len(members),
            "unique_model_visible_states": len({row["model_visible_state_signature"] for row in members}),
            "unique_model_visible_state_rate": len({row["model_visible_state_signature"] for row in members}) / len(members),
            "eligible_roots": sum(row["eligible"] for row in members),
            "future_sensitive_roots": sum(row["future_sensitive"] for row in members),
            "baseline_future_sensitive": None if baseline is None else baseline["future_sensitive"],
            "alternative_future_sensitive_roots": sum(row["future_sensitive"] for row in alternatives),
            "new_future_sensitive_state_found": bool(
                alternatives
                and any(row["future_sensitive"] for row in alternatives)
                and (baseline is None or not baseline["future_sensitive"])
            ),
        })

    by_mode = []
    for mode in sorted({row["behavior_mode"] for row in rows}):
        members = [row for row in rows if row["behavior_mode"] == mode]
        eligible = [row for row in members if row["eligible"]]
        by_mode.append({
            "behavior_mode": mode,
            "graphs": len(members),
            "eligible_roots": len(eligible),
            "future_sensitive_roots": sum(row["future_sensitive"] for row in eligible),
            "h1_h3_reversal_rate": (
                sum(row["future_sensitive"] for row in eligible) / len(eligible)
                if eligible else None
            ),
        })
    return {
        "schema_version": 1,
        "experiment": "paired behavior-policy diversity test",
        "graph_count": len(rows),
        "comparison_group_count": len(groups),
        "mean_unique_board_rate": sum(group["unique_board_rate"] for group in groups) / len(groups) if groups else None,
        "mean_unique_model_visible_state_rate": sum(group["unique_model_visible_state_rate"] for group in groups) / len(groups) if groups else None,
        "groups_with_new_future_sensitive_state": sum(group["new_future_sensitive_state_found"] for group in groups),
        "by_behavior_mode": by_mode,
        "groups": groups,
        "graphs": rows,
        "claim_limit": (
            "paired local-simulator evidence; behavior policies alter the visited-state "
            "distribution, while H3 remains a bounded oracle rather than final score"
        ),
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Behavior-policy diversity test", "",
        f"- physical H3 graphs: {report['graph_count']}",
        f"- paired scenario/step groups: {report['comparison_group_count']}",
        f"- mean unique board-fingerprint rate: {report['mean_unique_board_rate']:.1%}",
        f"- mean unique model-visible-state rate: {report['mean_unique_model_visible_state_rate']:.1%}",
        f"- groups where an alternative policy newly exposed a future-sensitive root: {report['groups_with_new_future_sensitive_state']}",
        "", "| behavior | eligible | H1/H3 reversals | reversal rate |",
        "|---|---:|---:|---:|",
    ]
    for row in report["by_behavior_mode"]:
        rate = row["h1_h3_reversal_rate"]
        lines.append(
            f"| {row['behavior_mode']} | {row['eligible_roots']} | "
            f"{row['future_sensitive_roots']} | "
            f"{rate:.1%} |" if rate is not None else
            f"| {row['behavior_mode']} | 0 | 0 | n/a |"
        )
    lines.extend(["", f"> {report['claim_limit']}", ""])
    return "\n".join(lines)


def _load(root: pathlib.Path) -> list[dict[str, Any]]:
    return [json.loads(path.read_text(encoding="utf-8")) for path in sorted(root.rglob("graph.json"))]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph-root", type=pathlib.Path, required=True)
    parser.add_argument("--json-output", type=pathlib.Path, required=True)
    parser.add_argument("--markdown-output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    graphs = _load(args.graph_root)
    if not graphs:
        raise SystemExit(f"no graph.json below {args.graph_root}")
    report = evaluate_diversity(graphs)
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    args.markdown_output.write_text(render_markdown(report), encoding="utf-8")
    print(args.markdown_output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
