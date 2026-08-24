"""Aggregate paired measured/terminal-rollout vector-search oracle runs."""
from __future__ import annotations

import argparse
import json
import pathlib
from typing import Any


def _root_map(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    roots = payload.get("roots") or []
    return {str(root["root_id"]): root for root in roots}


def _candidate_vectors(root: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(row["root_candidate_id"]): {
            "safe": bool(row.get("safe")),
            "one_step_vector": row.get("one_step_vector"),
        }
        for row in root.get("root_candidates") or []
    }


def compare_pair(
    measured: dict[str, Any], rollout: dict[str, Any], *, cell: str,
) -> dict[str, Any]:
    if measured.get("contract") != "vector_mcts_search_pareto_v1":
        raise ValueError(f"{cell}: invalid measured contract")
    if rollout.get("contract") != "pareto_tree_search_terminal_oracle_v2":
        raise ValueError(f"{cell}: invalid rollout contract")
    if rollout.get("oracle_contract") != "terminal_frontier_resurrection_v1":
        raise ValueError(f"{cell}: invalid rollout oracle contract")
    if measured.get("case_id") != rollout.get("case_id"):
        raise ValueError(f"{cell}: case mismatch")

    measured_roots = _root_map(measured)
    rollout_roots = _root_map(rollout)
    if measured_roots.keys() != rollout_roots.keys():
        raise ValueError(f"{cell}: paired root ids differ")

    complete = 0
    censored = 0
    resurrection: list[dict[str, str]] = []
    for root_id in measured_roots:
        measured_vectors = _candidate_vectors(measured_roots[root_id])
        rollout_vectors = _candidate_vectors(rollout_roots[root_id])
        if measured_vectors != rollout_vectors:
            raise ValueError(f"{cell}/{root_id}: H1 candidate vectors differ")
        oracle_root = rollout_roots[root_id]
        if oracle_root.get("terminal_truth_complete"):
            complete += 1
        else:
            censored += 1
        for candidate_id in (
            oracle_root.get("terminal_frontier_resurrection_candidates") or []
        ):
            resurrection.append({
                "root_id": root_id,
                "candidate_id": str(candidate_id),
            })

    summary = rollout.get("resurrection_summary") or {}
    return {
        "cell": cell,
        "case_id": measured.get("case_id"),
        "roots": len(measured_roots),
        "paired_h1_vectors_identical": True,
        "complete_terminal_truth_roots": complete,
        "censored_terminal_truth_roots": censored,
        "terminal_resurrection_actions": len(resurrection),
        "resurrection_actions": resurrection,
        "deepened_resurrection_actions": int(
            summary.get("deepened_resurrection_actions", 0)
        ),
        "measured_frontier_resurrection_actions": int(
            summary.get("measured_frontier_resurrection_actions", 0)
        ),
        "evaluated_frontier_resurrection_actions": int(
            summary.get("evaluated_frontier_resurrection_actions", 0)
        ),
    }


def aggregate(root: pathlib.Path) -> dict[str, Any]:
    cells = []
    for rollout_path in sorted(root.glob("*/rollout.json")):
        cell = rollout_path.parent.name
        measured_path = rollout_path.with_name("measured.json")
        if not measured_path.exists():
            raise FileNotFoundError(f"{cell}: missing measured.json")
        cells.append(compare_pair(
            json.loads(measured_path.read_text(encoding="utf-8")),
            json.loads(rollout_path.read_text(encoding="utf-8")),
            cell=cell,
        ))
    if not cells:
        raise ValueError(f"no paired oracle cells below {root}")

    resurrection_total = sum(
        cell["terminal_resurrection_actions"] for cell in cells
    )
    deepened_total = sum(
        cell["deepened_resurrection_actions"] for cell in cells
    )
    measured_total = sum(
        cell["measured_frontier_resurrection_actions"] for cell in cells
    )
    evaluated_total = sum(
        cell["evaluated_frontier_resurrection_actions"] for cell in cells
    )

    def recall(numerator: int) -> float | None:
        return numerator / resurrection_total if resurrection_total else None

    return {
        "schema_version": 1,
        "contract": "terminal_resurrection_paired_matrix_v1",
        "paired_h1_vectors_identical": all(
            cell["paired_h1_vectors_identical"] for cell in cells
        ),
        "cells": cells,
        "cell_count": len(cells),
        "root_count": sum(cell["roots"] for cell in cells),
        "complete_terminal_truth_roots": sum(
            cell["complete_terminal_truth_roots"] for cell in cells
        ),
        "censored_terminal_truth_roots": sum(
            cell["censored_terminal_truth_roots"] for cell in cells
        ),
        "terminal_resurrection_actions": resurrection_total,
        "deepened_resurrection_actions": deepened_total,
        "deepened_resurrection_recall": recall(deepened_total),
        "measured_frontier_resurrection_actions": measured_total,
        "measured_frontier_resurrection_recall": recall(measured_total),
        "evaluated_frontier_resurrection_actions": evaluated_total,
        "evaluated_frontier_resurrection_recall": recall(evaluated_total),
    }


def render_markdown(result: dict[str, Any]) -> str:
    rows = [
        "# Terminal rollout resurrection oracle",
        "",
        f"- cells: **{result['cell_count']}**",
        f"- roots: **{result['root_count']}**",
        "- paired H1 vectors identical: "
        f"**{result['paired_h1_vectors_identical']}**",
        "- complete terminal-truth roots: "
        f"**{result['complete_terminal_truth_roots']}**",
        "- censored roots: "
        f"**{result['censored_terminal_truth_roots']}**",
        "- terminal resurrection actions: "
        f"**{result['terminal_resurrection_actions']}**",
        "- deepened resurrection recall: "
        f"**{result['deepened_resurrection_recall']}**",
        "- measured-frontier resurrection recall: "
        f"**{result['measured_frontier_resurrection_recall']}**",
        "- rollout-evaluated frontier resurrection recall: "
        f"**{result['evaluated_frontier_resurrection_recall']}**",
        "",
        "| cell | roots | complete | censored | resurrected |",
        "|---|---:|---:|---:|---:|",
    ]
    rows.extend(
        f"| {cell['cell']} | {cell['roots']} | "
        f"{cell['complete_terminal_truth_roots']} | "
        f"{cell['censored_terminal_truth_roots']} | "
        f"{cell['terminal_resurrection_actions']} |"
        for cell in result["cells"]
    )
    return "\n".join(rows) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=pathlib.Path, required=True)
    parser.add_argument("--expected-cells", type=int, required=True)
    parser.add_argument("--json-output", type=pathlib.Path, required=True)
    parser.add_argument("--markdown-output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    result = aggregate(args.root)
    if result["cell_count"] != args.expected_cells:
        raise ValueError(
            f"expected {args.expected_cells} cells, found {result['cell_count']}"
        )
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    args.markdown_output.write_text(render_markdown(result), encoding="utf-8")
    print(args.markdown_output.read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
