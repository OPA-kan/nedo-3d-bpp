"""Aggregate sharded bounded-rollout checkpoint audits."""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.audit_rollout_checkpoints import summarize_roots  # noqa: E402


def aggregate(rows: list[dict[str, Any]], *, expected_cells: int):
    if len(rows) != expected_cells:
        raise ValueError(
            f"expected {expected_cells} cells, found {len(rows)}"
        )
    contracts = {row.get("contract") for row in rows}
    if contracts != {"bounded_physical_rollout_checkpoint_oracle_v1"}:
        raise ValueError(f"unexpected contracts: {contracts}")
    cap_sets = {tuple(row.get("continuation_caps") or []) for row in rows}
    if len(cap_sets) != 1:
        raise ValueError("checkpoint caps differ between cells")
    caps = list(next(iter(cap_sets)))
    roots = [root for row in rows for root in row.get("roots") or []]
    root_ids = [root["root_id"] for root in roots]
    if len(root_ids) != len(set(root_ids)):
        raise ValueError("duplicate checkpoint root ids")
    return {
        "contract": "bounded_physical_rollout_checkpoint_aggregate_v1",
        "cells": len(rows),
        "roots": len(roots),
        "interventions": sum(
            root["terminal_selected_candidate_id"]
            != root["incumbent_candidate_id"]
            for root in roots
        ),
        "continuation_caps": caps,
        "total_depths": [cap + 1 for cap in caps],
        "value_model": None,
        "summary": summarize_roots(roots, caps),
        "cell_summaries": {
            row["cell"]: {
                "roots": len(row.get("roots") or []),
                "summary": row["summary"],
            }
            for row in rows
        },
        "root_rows": roots,
    }


def markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Bounded physical rollout checkpoint oracle",
        "",
        f"- cells: {report['cells']}",
        f"- targeted roots: {report['roots']}",
        f"- terminal interventions: {report['interventions']}",
        "- learned value used: no",
        "",
        "| total depth | terminal action recall | intervention recall | "
        "mean seconds | p95 seconds | <=10s |",
        "|---:|---:|---:|---:|---:|---:|",
    ]
    for cap in report["continuation_caps"]:
        row = report["summary"][str(cap)]
        lines.append(
            f"| H{row['total_depth']} | "
            f"{row['terminal_action_recall']:.3f} | "
            f"{row['intervention_action_recall']:.3f} | "
            f"{row['mean_decision_seconds']:.2f} | "
            f"{row['p95_decision_seconds']:.2f} | "
            f"{row['within_10s_rate']:.3f} |"
        )
    lines.extend([
        "",
        "> Checkpoint vectors are achieved physical prefixes. Terminal truth "
        "remains the frozen genuine-terminal rollout from the source corpus.",
        "",
    ])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=pathlib.Path, required=True)
    parser.add_argument("--expected-cells", type=int, required=True)
    parser.add_argument("--json-output", type=pathlib.Path, required=True)
    parser.add_argument("--markdown-output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    paths = sorted(args.root.rglob("checkpoint.json"))
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
