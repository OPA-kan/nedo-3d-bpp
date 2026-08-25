"""Aggregate sharded deadline-aware physical rollout audits."""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.deadline_rollout_summary import summarize  # noqa: E402


def aggregate(rows: list[dict[str, Any]], *, expected_cells: int) -> dict[str, Any]:
    if len(rows) != expected_cells:
        raise ValueError(f"expected {expected_cells} cells, found {len(rows)}")
    if {row.get("contract") for row in rows} != {
        "deadline_rollout_hard_state_audit_v1"
    }:
        raise ValueError("unexpected deadline rollout contract")
    settings = {
        (
            row["candidate_budget"], row["decision_budget_seconds"],
            row["live_action_reserve_seconds"],
            row["max_continuation_steps"], row["safety_factor"],
        )
        for row in rows
    }
    if len(settings) != 1:
        raise ValueError("deadline rollout settings differ between cells")
    roots = [root for row in rows for root in row.get("roots") or []]
    root_ids = [str(root["root_id"]) for root in roots]
    if len(root_ids) != len(set(root_ids)):
        raise ValueError("duplicate deadline rollout root ids")
    candidate_budget, decision_budget, reserve, max_steps, safety = next(
        iter(settings)
    )
    return {
        "contract": "deadline_rollout_hard_state_aggregate_v1",
        "cells": len(rows),
        "candidate_budget": candidate_budget,
        "decision_budget_seconds": decision_budget,
        "live_action_reserve_seconds": reserve,
        "max_continuation_steps": max_steps,
        "max_total_depth": max_steps + 1,
        "safety_factor": safety,
        "value_model": None,
        "summary": summarize(roots),
        "cell_summaries": {
            row["cell"]: row["summary"] for row in rows
        },
        "root_rows": roots,
    }


def markdown(report: dict[str, Any]) -> str:
    row = report["summary"]
    return "\n".join([
        "# Deadline-aware lockstep physical rollout",
        "",
        f"- cells: {report['cells']}",
        f"- hard roots: {row['roots']}",
        f"- candidates per root: {report['candidate_budget']}",
        f"- maximum depth: H{report['max_total_depth']}",
        f"- decision budget: {report['decision_budget_seconds']:.2f}s",
        "- learned value used: no",
        "",
        "| terminal action recall | intervention recall | terminal available | "
        "mean seconds | p95 seconds | max seconds | <=10s | deadline met |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|",
        f"| {row['terminal_action_recall']:.3f} | "
        f"{row['intervention_action_recall']:.3f} | "
        f"{row['terminal_selected_available_recall']:.3f} | "
        f"{row['mean_decision_seconds']:.2f} | "
        f"{row['p95_decision_seconds']:.2f} | "
        f"{row['max_decision_seconds']:.2f} | "
        f"{row['within_10s_rate']:.3f} | "
        f"{row['search_deadline_met_rate']:.3f} |",
        "",
        f"- achieved depth counts: {row['depth_counts']}",
        "",
        "> Candidate choice is group-OOF. Physics checkpoint vectors select "
        "the action; the terminal rollout corpus is reference-only.",
        "",
    ])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=pathlib.Path, required=True)
    parser.add_argument("--expected-cells", type=int, required=True)
    parser.add_argument("--json-output", type=pathlib.Path, required=True)
    parser.add_argument("--markdown-output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    paths = sorted(args.root.rglob("deadline.json"))
    report = aggregate(
        [json.loads(path.read_text(encoding="utf-8")) for path in paths],
        expected_cells=args.expected_cells,
    )
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    args.markdown_output.write_text(markdown(report), encoding="utf-8")
    print(args.markdown_output.read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
