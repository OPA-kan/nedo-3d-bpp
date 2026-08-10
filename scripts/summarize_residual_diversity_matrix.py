"""Aggregate safe-split dataset results without pooling scenario effects."""
from __future__ import annotations

import argparse
import json
import pathlib
from typing import Any


def summarize_matrix(summaries: list[dict[str, Any]]) -> dict[str, Any]:
    if not summaries:
        raise ValueError("no scenario summaries were provided")

    rows = []
    for summary in sorted(summaries, key=lambda row: str(row.get("case_id"))):
        context = summary.get("scenario_context") or {}
        steps = summary.get("steps") or []
        positive = sum(int(step.get("positive_transition", 0)) for step in steps)
        negative = sum(
            int(step.get("negative_physical_risk", 0)) for step in steps
        )
        rows.append(
            {
                "case_id": str(summary.get("case_id")),
                "dataset_id": summary.get("dataset_id"),
                "container_count": int(context.get("container_count", 0)),
                "shelf_count": int(context.get("shelf_count", 0)),
                "shelf_pattern": list(context.get("shelf_pattern") or []),
                "priority_container_count": int(
                    context.get("priority_container_count", 0)
                ),
                "initial_preloaded_count": int(
                    context.get("initial_preloaded_count", 0)
                ),
                "steps_measured": int(summary.get("steps_measured", 0)),
                "observed_swap_rounds": summary.get("observed_swap_rounds"),
                "portfolio_constructions": list(
                    summary.get("portfolio_constructions") or []
                ),
                "swaps_applied": summary.get("swaps_applied"),
                "mean_physical_nn_distance_delta": summary.get(
                    "mean_physical_nn_distance_delta"
                ),
                "positive_transition": positive,
                "negative_physical_risk": negative,
                "acceptance_verdict": (
                    (summary.get("acceptance") or {}).get("verdict")
                ),
                "failed_guards": list(
                    (summary.get("acceptance") or {}).get(
                        "failed_guards", []
                    )
                ),
            }
        )

    cells = {
        (row["container_count"], row["shelf_count"] > 0) for row in rows
    }
    # A matrix run is one arm. If the scenarios disagree about which
    # construction they used, the aggregate is not comparable to anything and
    # must say so rather than average across two experiments.
    arms = sorted({str(row["observed_swap_rounds"]) for row in rows})
    constructions = sorted(
        {
            name
            for row in rows
            for name in row["portfolio_constructions"]
        }
    )
    required_cells = {(1, False), (1, True), (2, False), (2, True)}
    failed_scenarios = [
        row["case_id"] for row in rows if row["acceptance_verdict"] != "pass"
    ]
    empty_positive = [
        row["case_id"] for row in rows if row["positive_transition"] <= 0
    ]
    coverage_complete = required_cells.issubset(cells)
    return {
        "schema_version": 2,
        "scenario_count": len(rows),
        # An absent condition and a failed guard are different events. A
        # cancelled or crashed scenario job leaves the matrix incomplete, and
        # reporting that as "fail" with an empty failed_scenarios list reads
        # as a guard result that never happened.
        "completeness": (
            "complete" if coverage_complete else "incomplete_conditions"
        ),
        "condition_coverage": {
            "container_counts": sorted(
                {row["container_count"] for row in rows}
            ),
            "shelf_counts": sorted({row["shelf_count"] for row in rows}),
            "cells": [
                {"container_count": count, "has_shelf": has_shelf}
                for count, has_shelf in sorted(cells)
            ],
            "core_2x2_complete": coverage_complete,
        },
        "arm": {
            "observed_swap_rounds": (
                rows[0]["observed_swap_rounds"] if len(arms) == 1 else None
            ),
            "portfolio_constructions": constructions,
            "swaps_applied": sum(
                int(row["swaps_applied"] or 0) for row in rows
            ),
            "uniform_across_scenarios": len(arms) == 1,
        },
        "labels": {
            "positive_transition": sum(
                row["positive_transition"] for row in rows
            ),
            "negative_physical_risk": sum(
                row["negative_physical_risk"] for row in rows
            ),
        },
        "acceptance": {
            "verdict": (
                "pass"
                if (
                    coverage_complete
                    and not failed_scenarios
                    and not empty_positive
                )
                else "fail"
            ),
            "verdict_reason": (
                "pass"
                if coverage_complete
                and not failed_scenarios
                and not empty_positive
                else (
                    "incomplete_conditions"
                    if not coverage_complete
                    else "guard_failure"
                )
            ),
            "failed_scenarios": failed_scenarios,
            "empty_positive_scenarios": empty_positive,
            "contract": (
                "The 1/2-container x shelf/no-shelf cells must all be present; "
                "each scenario must retain a non-empty safe-positive arm and "
                "pass its paired physical-diversity guards. Scenario metrics "
                "are never pooled to hide a failed condition."
            ),
        },
        "scenarios": rows,
    }


def markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# Residual-state diversity condition matrix",
        "",
        f"- Scenarios: {summary['scenario_count']}",
        (
            "- Core 1/2-container x shelf/no-shelf coverage: "
            f"{summary['condition_coverage']['core_2x2_complete']}"
        ),
        (
            "- Positive / negative-risk labels: "
            f"{summary['labels']['positive_transition']} / "
            f"{summary['labels']['negative_physical_risk']}"
        ),
        (
            "- Arm (observed swap rounds): "
            f"{summary['arm']['observed_swap_rounds']}"
            + (
                ""
                if summary["arm"]["uniform_across_scenarios"]
                else " **(scenarios disagree -- not one arm)**"
            )
        ),
        (
            "- Portfolio construction: "
            f"`{summary['arm']['portfolio_constructions']}`, "
            f"swaps applied: {summary['arm']['swaps_applied']}"
        ),
        (
            "- Acceptance verdict: "
            f"**{summary['acceptance']['verdict']}** "
            f"({summary['acceptance']['verdict_reason']})"
        ),
        (
            "- **The matrix is incomplete: a condition is missing, so this is "
            "not a guard result.** Re-run before citing it."
            if summary["completeness"] != "complete"
            else f"- Completeness: {summary['completeness']}"
        ),
        f"- Failed scenarios: {summary['acceptance']['failed_scenarios']}",
        "",
        "| scenario | containers | shelves | steps | safe positive | "
        "negative risk | mean physical NN delta | verdict |",
        "|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in summary["scenarios"]:
        lines.append(
            "| {case_id} | {container_count} | {shelf_count} | "
            "{steps_measured} | {positive_transition} | "
            "{negative_physical_risk} | "
            "{mean_physical_nn_distance_delta} | "
            "{acceptance_verdict} |".format(**row)
        )
    lines.extend(["", summary["acceptance"]["contract"], ""])
    return "\n".join(lines)


def load_summaries(root: pathlib.Path) -> list[dict[str, Any]]:
    paths = sorted(root.glob("**/summary.json"))
    return [json.loads(path.read_text(encoding="utf-8")) for path in paths]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=pathlib.Path, required=True)
    parser.add_argument("--json-output", type=pathlib.Path, required=True)
    parser.add_argument("--markdown-output", type=pathlib.Path, required=True)
    args = parser.parse_args()

    summary = summarize_matrix(load_summaries(args.root))
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    args.markdown_output.write_text(markdown(summary), encoding="utf-8")
    print(args.markdown_output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
