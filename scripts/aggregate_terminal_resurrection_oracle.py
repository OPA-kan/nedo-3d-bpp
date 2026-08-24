"""Aggregate terminal-scored v0 versus Pareto-PUCT physical searches."""
from __future__ import annotations

import argparse
import json
import pathlib
from typing import Any


def _root_map(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(root["root_id"]): root for root in payload.get("roots") or []
    }


def _candidate_evidence(root: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(row["root_candidate_id"]): {
            "safe": bool(row.get("safe")),
            "one_step_vector": row.get("one_step_vector"),
            "terminal_genuine": bool(row.get("terminal_genuine")),
            "terminal_termination": row.get("terminal_termination"),
            "terminal_vector": row.get("terminal_vector"),
        }
        for row in root.get("root_candidates") or []
    }


def _arm_counts(
    roots: dict[str, dict[str, Any]],
    truth: dict[str, set[str]],
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
        "symmetry_shadow_observations": 0,
        "symmetry_shadow_quotient_only_hits": 0,
        "symmetry_shadow_potential_state_reduction": 0,
        "symmetry_shadow_potential_rollout_savings": 0,
        "symmetry_shadow_rollout_conflicts": 0,
    }
    for root_id, root in roots.items():
        resurrected = truth[root_id]
        deepened = set(root.get("deepened_candidates") or [])
        search = set(root.get("measured_search_pareto_candidates") or [])
        terminal = set(root.get("terminal_pareto_candidates") or [])
        counts["deepened_resurrection_actions"] += len(
            resurrected & deepened
        )
        counts["frontier_resurrection_actions"] += len(
            resurrected & search
        )
        counts["terminal_pareto_actions"] += len(terminal)
        counts["terminal_pareto_recovered_actions"] += len(terminal & search)
        counts["search_frontier_actions"] += len(search)
        counts["false_frontier_actions"] += len(search - terminal)
        counts["physical_steps"] += int(root.get("physical_steps", 0))
        counts["terminal_rollout_physical_steps"] += int(
            root.get("terminal_rollout_physical_steps", 0)
        )
        symmetry = root.get("item_symmetry_cache_shadow") or {}
        rollout = (symmetry.get("evaluator_by_kind") or {}).get(
            "rollout", {}
        )
        counts["symmetry_shadow_observations"] += int(
            symmetry.get("observations", 0)
        )
        counts["symmetry_shadow_quotient_only_hits"] += int(
            symmetry.get("quotient_only_hits", 0)
        )
        counts["symmetry_shadow_potential_state_reduction"] += int(
            symmetry.get("potential_state_reduction", 0)
        )
        counts["symmetry_shadow_potential_rollout_savings"] += int(
            rollout.get("potential_call_savings", 0)
        )
        counts["symmetry_shadow_rollout_conflicts"] += int(
            rollout.get("conflicts", 0)
        )
    return counts


def compare_allocation_pair(
    v0: dict[str, Any], puct: dict[str, Any], *, cell: str,
) -> dict[str, Any]:
    for name, payload, allocation in (
        ("v0", v0, "frontier"), ("puct", puct, "pareto-puct")
    ):
        if payload.get("contract") != "pareto_search_terminal_audit_v3":
            raise ValueError(f"{cell}: invalid {name} contract")
        if payload.get("oracle_contract") != (
            "terminal_frontier_resurrection_v1"
        ):
            raise ValueError(f"{cell}: invalid {name} oracle contract")
        if payload.get("leaf_eval") != "measured":
            raise ValueError(f"{cell}: {name} allocation saw terminal values")
        if payload.get("allocation_mode") != allocation:
            raise ValueError(f"{cell}: invalid {name} allocation")
    if v0.get("case_id") != puct.get("case_id"):
        raise ValueError(f"{cell}: case mismatch")

    v0_roots = _root_map(v0)
    puct_roots = _root_map(puct)
    if v0_roots.keys() != puct_roots.keys():
        raise ValueError(f"{cell}: paired root ids differ")

    complete = 0
    censored = 0
    truth: dict[str, set[str]] = {}
    resurrection_rows: list[dict[str, str]] = []
    for root_id in v0_roots:
        v0_root = v0_roots[root_id]
        puct_root = puct_roots[root_id]
        if _candidate_evidence(v0_root) != _candidate_evidence(puct_root):
            raise ValueError(
                f"{cell}/{root_id}: paired H1 or terminal evidence differs"
            )
        v0_resurrection = set(
            v0_root.get("terminal_frontier_resurrection_candidates") or []
        )
        puct_resurrection = set(
            puct_root.get("terminal_frontier_resurrection_candidates") or []
        )
        if v0_resurrection != puct_resurrection:
            raise ValueError(f"{cell}/{root_id}: terminal truth differs")
        if bool(v0_root.get("terminal_truth_complete")) != bool(
            puct_root.get("terminal_truth_complete")
        ):
            raise ValueError(f"{cell}/{root_id}: censoring differs")
        if v0_root.get("terminal_truth_complete"):
            complete += 1
            truth[root_id] = v0_resurrection
            resurrection_rows.extend(
                {"root_id": root_id, "candidate_id": candidate}
                for candidate in sorted(v0_resurrection)
            )
        else:
            censored += 1
            truth[root_id] = set()

    return {
        "cell": cell,
        "case_id": v0.get("case_id"),
        "roots": len(v0_roots),
        "paired_h1_and_terminal_evidence_identical": True,
        "complete_terminal_truth_roots": complete,
        "censored_terminal_truth_roots": censored,
        "terminal_resurrection_actions": len(resurrection_rows),
        "resurrection_actions": resurrection_rows,
        "v0": _arm_counts(v0_roots, truth),
        "pareto_puct": _arm_counts(puct_roots, truth),
    }


def aggregate(root: pathlib.Path) -> dict[str, Any]:
    cells = []
    for puct_path in sorted(root.glob("*/puct.json")):
        cell = puct_path.parent.name
        v0_path = puct_path.with_name("v0.json")
        if not v0_path.exists():
            raise FileNotFoundError(f"{cell}: missing v0.json")
        cells.append(compare_allocation_pair(
            json.loads(v0_path.read_text(encoding="utf-8")),
            json.loads(puct_path.read_text(encoding="utf-8")),
            cell=cell,
        ))
    if not cells:
        raise ValueError(f"no paired v0/Pareto-PUCT cells below {root}")

    truth = sum(cell["terminal_resurrection_actions"] for cell in cells)

    def arm_summary(name: str) -> dict[str, Any]:
        total: dict[str, Any] = {}
        for cell in cells:
            for key, value in cell[name].items():
                total[key] = total.get(key, 0) + int(value)
        total["deepened_resurrection_recall"] = (
            total["deepened_resurrection_actions"] / truth if truth else None
        )
        total["frontier_resurrection_recall"] = (
            total["frontier_resurrection_actions"] / truth if truth else None
        )
        terminal = total["terminal_pareto_actions"]
        total["terminal_pareto_recall"] = (
            total["terminal_pareto_recovered_actions"] / terminal
            if terminal else None
        )
        return total

    return {
        "schema_version": 2,
        "contract": "terminal_scored_pareto_puct_matrix_v2",
        "paired_h1_and_terminal_evidence_identical": all(
            cell["paired_h1_and_terminal_evidence_identical"]
            for cell in cells
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
        "terminal_resurrection_actions": truth,
        "v0": arm_summary("v0"),
        "pareto_puct": arm_summary("pareto_puct"),
    }


def render_markdown(result: dict[str, Any]) -> str:
    rows = [
        "# Terminal-scored Pareto-PUCT allocation",
        "",
        f"- cells: **{result['cell_count']}**",
        f"- roots: **{result['root_count']}**",
        "- paired H1 and terminal evidence identical: "
        f"**{result['paired_h1_and_terminal_evidence_identical']}**",
        "- complete terminal-truth roots: "
        f"**{result['complete_terminal_truth_roots']}**",
        f"- censored roots: **{result['censored_terminal_truth_roots']}**",
        "- terminal resurrection actions: "
        f"**{result['terminal_resurrection_actions']}**",
        "",
        "| arm | resurrection deepening | resurrection frontier | "
        "terminal-Pareto recall | false frontier | physical steps |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for key, label in (("v0", "v0 frontier-first"),
                       ("pareto_puct", "Pareto-PUCT")):
        arm = result[key]
        rows.append(
            f"| {label} | {arm['deepened_resurrection_recall']} | "
            f"{arm['frontier_resurrection_recall']} | "
            f"{arm['terminal_pareto_recall']} | "
            f"{arm['false_frontier_actions']} | {arm['physical_steps']} |"
        )
    rows.extend((
        "",
        "## Identical-item physical rollout reuse shadow",
        "",
        "| arm | state observations | quotient-only hits | state reduction | "
        "potential rollout calls saved | rollout conflicts |",
        "|---|---:|---:|---:|---:|---:|",
    ))
    for key, label in (("v0", "v0 frontier-first"),
                       ("pareto_puct", "Pareto-PUCT")):
        arm = result[key]
        rows.append(
            f"| {label} | {arm['symmetry_shadow_observations']} | "
            f"{arm['symmetry_shadow_quotient_only_hits']} | "
            f"{arm['symmetry_shadow_potential_state_reduction']} | "
            f"{arm['symmetry_shadow_potential_rollout_savings']} | "
            f"{arm['symmetry_shadow_rollout_conflicts']} |"
        )
    rows.extend((
        "",
        "This is shadow-only: every physical rollout still executes.",
        "",
        "| cell | roots | complete | censored | resurrected |",
        "|---|---:|---:|---:|---:|",
    ))
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
