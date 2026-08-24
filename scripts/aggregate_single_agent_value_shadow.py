"""Aggregate terminal-scored fixed-PUCT H2+0 versus H2+V arms."""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.aggregate_terminal_resurrection_oracle import (
    _candidate_evidence, _root_map,
)


def _arm_counts(
    roots: dict[str, dict[str, Any]], truth: dict[str, set[str]], *,
    frontier_field: str,
) -> dict[str, int]:
    counts = {
        "deepened_resurrection_actions": 0,
        "frontier_resurrection_actions": 0,
        "terminal_pareto_actions": 0,
        "terminal_pareto_recovered_actions": 0,
        "search_frontier_actions": 0,
        "false_frontier_actions": 0,
        "physical_steps": 0,
        "terminal_rollout_physical_steps": 0,
    }
    for root_id, root in roots.items():
        resurrected = truth[root_id]
        deepened = set(root.get("deepened_candidates") or [])
        search = set(root.get(frontier_field) or [])
        terminal = set(root.get("terminal_pareto_candidates") or [])
        counts["deepened_resurrection_actions"] += len(resurrected & deepened)
        counts["frontier_resurrection_actions"] += len(resurrected & search)
        counts["terminal_pareto_actions"] += len(terminal)
        counts["terminal_pareto_recovered_actions"] += len(terminal & search)
        counts["search_frontier_actions"] += len(search)
        counts["false_frontier_actions"] += len(search - terminal)
        counts["physical_steps"] += int(root.get("physical_steps", 0))
        counts["terminal_rollout_physical_steps"] += int(
            root.get("terminal_rollout_physical_steps", 0)
        )
    return counts


def compare_pair(zero: dict[str, Any], value: dict[str, Any], *, cell: str) -> dict[str, Any]:
    if zero.get("contract") != "pareto_search_terminal_audit_v3":
        raise ValueError(f"{cell}: invalid zero contract")
    if value.get("contract") != "pareto_puct_value_terminal_audit_v4":
        raise ValueError(f"{cell}: invalid value contract")
    for name, payload, leaf in (("zero", zero, "measured"), ("value", value, "value")):
        if payload.get("allocation_mode") != "pareto-puct":
            raise ValueError(f"{cell}: {name} is not fixed Pareto-PUCT")
        if payload.get("leaf_eval") != leaf or not payload.get("terminal_audit"):
            raise ValueError(f"{cell}: invalid {name} leaf/audit contract")
        if payload.get("max_depth") != 2:
            raise ValueError(f"{cell}: {name} is not H2")
    if zero.get("case_id") != value.get("case_id"):
        raise ValueError(f"{cell}: case mismatch")
    zero_roots, value_roots = _root_map(zero), _root_map(value)
    if zero_roots.keys() != value_roots.keys():
        raise ValueError(f"{cell}: root ids differ")
    truth: dict[str, set[str]] = {}
    complete = censored = 0
    for root_id in zero_roots:
        left, right = zero_roots[root_id], value_roots[root_id]
        if _candidate_evidence(left) != _candidate_evidence(right):
            raise ValueError(f"{cell}/{root_id}: H1 or terminal evidence differs")
        ltruth = set(left.get("terminal_frontier_resurrection_candidates") or [])
        rtruth = set(right.get("terminal_frontier_resurrection_candidates") or [])
        if ltruth != rtruth:
            raise ValueError(f"{cell}/{root_id}: resurrection truth differs")
        if bool(left.get("terminal_truth_complete")) != bool(right.get("terminal_truth_complete")):
            raise ValueError(f"{cell}/{root_id}: censoring differs")
        if left.get("terminal_truth_complete"):
            complete += 1
            truth[root_id] = ltruth
        else:
            censored += 1
            truth[root_id] = set()
    return {
        "cell": cell, "case_id": zero.get("case_id"), "roots": len(zero_roots),
        "complete_terminal_truth_roots": complete,
        "censored_terminal_truth_roots": censored,
        "terminal_resurrection_actions": sum(len(row) for row in truth.values()),
        "zero": _arm_counts(
            zero_roots, truth,
            frontier_field="measured_search_pareto_candidates",
        ),
        "value": _arm_counts(
            value_roots, truth,
            frontier_field="evaluated_search_pareto_candidates",
        ),
    }


def aggregate(root: pathlib.Path) -> dict[str, Any]:
    cells = []
    for value_path in sorted(root.glob("*/value.json")):
        zero_path = value_path.with_name("zero.json")
        if not zero_path.exists():
            raise FileNotFoundError(f"{value_path.parent.name}: missing zero.json")
        cells.append(compare_pair(
            json.loads(zero_path.read_text(encoding="utf-8")),
            json.loads(value_path.read_text(encoding="utf-8")),
            cell=value_path.parent.name,
        ))
    if not cells:
        raise ValueError(f"no H2+0/H2+V cells below {root}")
    truth = sum(row["terminal_resurrection_actions"] for row in cells)

    def summarize(name: str) -> dict[str, Any]:
        total: dict[str, int | float | None] = {}
        for cell in cells:
            for key, value in cell[name].items():
                total[key] = int(total.get(key, 0) or 0) + int(value)
        total["deepened_resurrection_recall"] = (
            total["deepened_resurrection_actions"] / truth if truth else None
        )
        total["frontier_resurrection_recall"] = (
            total["frontier_resurrection_actions"] / truth if truth else None
        )
        terminal = int(total["terminal_pareto_actions"] or 0)
        total["terminal_pareto_recall"] = (
            total["terminal_pareto_recovered_actions"] / terminal if terminal else None
        )
        return total

    zero, value = summarize("zero"), summarize("value")
    accepted = bool(
        value["terminal_pareto_recovered_actions"] > zero["terminal_pareto_recovered_actions"]
        and value["frontier_resurrection_actions"] > zero["frontier_resurrection_actions"]
        and value["false_frontier_actions"] <= zero["false_frontier_actions"]
    )
    return {
        "schema_version": 1,
        "contract": "single_agent_H2_value_shadow_terminal_scored_v1",
        "cells": cells, "cell_count": len(cells),
        "root_count": sum(row["roots"] for row in cells),
        "complete_terminal_truth_roots": sum(row["complete_terminal_truth_roots"] for row in cells),
        "censored_terminal_truth_roots": sum(row["censored_terminal_truth_roots"] for row in cells),
        "terminal_resurrection_actions": truth,
        "zero": zero, "value": value,
        "acceptance_gate": "strict improvement in terminal-Pareto and resurrection-frontier recovery; no false-frontier increase",
        "accepted": accepted,
    }


def render_markdown(result: dict[str, Any]) -> str:
    rows = [
        "# Single-agent H2 leaf-value shadow", "",
        f"- cells / roots: **{result['cell_count']} / {result['root_count']}**",
        f"- complete / censored truth roots: **{result['complete_terminal_truth_roots']} / {result['censored_terminal_truth_roots']}**",
        f"- terminal resurrection actions: **{result['terminal_resurrection_actions']}**", "",
        "| arm | resurrection frontier recall | terminal-Pareto recall | false frontier | physical steps |",
        "|---|---:|---:|---:|---:|",
    ]
    for key, label in (("zero", "H2+0"), ("value", "H2+V")):
        arm = result[key]
        rows.append(
            f"| {label} | {arm['frontier_resurrection_recall']} | "
            f"{arm['terminal_pareto_recall']} | {arm['false_frontier_actions']} | "
            f"{arm['physical_steps']} |"
        )
    rows.extend(("", f"- gate: **{'PASS' if result['accepted'] else 'FAIL'}**", ""))
    return "\n".join(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=pathlib.Path, required=True)
    parser.add_argument("--expected-cells", type=int, required=True)
    parser.add_argument("--json-output", type=pathlib.Path, required=True)
    parser.add_argument("--markdown-output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    result = aggregate(args.root)
    if result["cell_count"] != args.expected_cells:
        raise SystemExit(f"expected {args.expected_cells} cells, got {result['cell_count']}")
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    args.markdown_output.write_text(render_markdown(result), encoding="utf-8")
    print(args.markdown_output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
