"""
Does the acceptance rule matter? Read the paired shadow arm and say.

The swap optimizer accepts a move whenever the single Gower ΔNN rises. That
sum averages two different questions -- where the item landed, and which item
left the pool -- and nobody chose the weights, so it can pay for one with the
other. `pareto_gate` keeps the same ordering but refuses a move that degrades
either component.

Which rule is better is not a question prose can settle, so the dataset
builder runs both on every board: same pool, same seed, same forced keys,
only the rule differs. That pairing matters because the policy is
deadline-limited and two runs of one scenario do not reach the same board, so
a between-run comparison of arms is confounded -- which is exactly how the
earlier greedy-versus-seeded verdict turned out to be runner-variable.

This script aggregates those pairs. The number that decides whether the
question is live at all is `component_degrading_swaps` on the shipped arm:
accepted swaps that raised the sum while a component fell. If that is zero
everywhere, the two rules cannot disagree and the sum rule is fine as it is.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import statistics
from typing import Any

SHIPPED = "swap_optimizer"
SHADOW = "swap_optimizer_shadow"
COMPONENTS = ("occupancy", "consumption")


def paired_rows(root: pathlib.Path) -> list[dict[str, Any]]:
    """One row per board that ran both arms."""
    rows: list[dict[str, Any]] = []
    # Two layouts, one reader: a run's own artifacts are
    # <scenario>/dataset/manifest.json while the retained history nests one
    # deeper at <run_id>/dataset/<scenario>/manifest.json. Matching on the
    # file name works for both and for whatever the next one is.
    for path in sorted(root.rglob("manifest.json")):
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        case = manifest.get("case") or {}
        for step in case.get("steps") or []:
            split = (step.get("sampling") or {}).get("outcome_split") or {}
            shipped = split.get(SHIPPED) or {}
            shadow = split.get(SHADOW)
            if not shipped or not isinstance(shadow, dict):
                continue
            row: dict[str, Any] = {
                "source": str(path.parent),
                "case_id": str(case.get("case_id")),
                "step": step.get("step"),
                "degrading_swaps": int(
                    shipped.get("component_degrading_swaps", 0)
                ),
                "refused_by_gate": int(
                    shadow.get("swaps_refused_by_gate", 0)
                ),
                "shipped_swaps": int(shipped.get("swaps_applied", 0)),
                "shadow_swaps": int(shadow.get("swaps_applied", 0)),
            }
            for arm, trace in (("shipped", shipped), ("shadow", shadow)):
                final = trace.get("final_objective") or {}
                row[f"{arm}_sum"] = final.get(
                    "mean_nearest_neighbor_distance_delta"
                )
                components = trace.get("final_components") or {}
                for name in COMPONENTS:
                    row[f"{arm}_{name}"] = components.get(f"{name}_delta")
            rows.append(row)
    return rows


def summarise(rows: list[dict[str, Any]]) -> dict[str, Any]:
    def paired(name: str) -> list[float]:
        return [
            row[f"shadow_{name}"] - row[f"shipped_{name}"]
            for row in rows
            if row.get(f"shadow_{name}") is not None
            and row.get(f"shipped_{name}") is not None
        ]

    report: dict[str, Any] = {
        "boards": len(rows),
        "boards_with_a_degrading_swap": sum(
            1 for row in rows if row["degrading_swaps"] > 0
        ),
        "degrading_swaps": sum(row["degrading_swaps"] for row in rows),
        "shipped_swaps": sum(row["shipped_swaps"] for row in rows),
        "shadow_swaps": sum(row["shadow_swaps"] for row in rows),
        "swaps_refused_by_gate": sum(row["refused_by_gate"] for row in rows),
    }
    for name in ("sum", *COMPONENTS):
        values = paired(name)
        report[f"gate_minus_sum_{name}"] = {
            "boards": len(values),
            "mean": statistics.fmean(values) if values else None,
            "median": statistics.median(values) if values else None,
            "gate_better": sum(v > 0 for v in values),
            "tied": sum(v == 0 for v in values),
            "gate_worse": sum(v < 0 for v in values),
        }
    return report


def verdict(report: dict[str, Any]) -> str:
    if not report["boards"]:
        return "no_paired_boards"
    if report["degrading_swaps"] == 0:
        return "acceptance_rule_cannot_matter_here"
    components = [report[f"gate_minus_sum_{name}"] for name in COMPONENTS]
    means = [block["mean"] for block in components]
    if any(value is None for value in means):
        return "insufficient_component_coverage"
    if all(value > 0 for value in means):
        return "gate_dominates_on_both_components"
    if all(value < 0 for value in means):
        return "sum_dominates_on_both_components"
    return "gate_trades_one_component_for_the_other"


def markdown(report: dict[str, Any]) -> str:
    if not report.get("boards"):
        return (
            "# Swap acceptance rule\n\n"
            f"- Verdict: **{report['verdict']}**\n\n"
            "No board ran both arms. The shadow arm landed in "
            "`scripts/build_replay_dataset.py` after the retained runs were "
            "measured, so a fresh matrix run is needed.\n"
        )
    lines = [
        "# Swap acceptance: does refusing a component-degrading swap help?",
        "",
        f"- Verdict: **{report['verdict']}**",
        f"- {report['boards']} boards, both arms on each",
        (
            f"- Shipped arm accepted {report['degrading_swaps']} swaps that "
            f"raised the sum while a component fell, on "
            f"{report['boards_with_a_degrading_swap']} boards"
        ),
        (
            f"- The gate refused {report['swaps_refused_by_gate']} moves; "
            f"{report['shipped_swaps']} swaps applied by the sum rule against "
            f"{report['shadow_swaps']} by the gate"
        ),
        "",
        "| quantity | mean gate − sum | median | gate better | tied | "
        "gate worse |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for name, label in (
        ("sum", "the single Gower ΔNN (what the sum rule maximises)"),
        ("occupancy", "Δ occupancy"),
        ("consumption", "Δ consumption"),
    ):
        block = report[f"gate_minus_sum_{name}"]
        mean = block["mean"]
        median = block["median"]
        lines.append(
            f"| {label} | "
            + ("—" if mean is None else f"{mean:+.6f}")
            + " | "
            + ("—" if median is None else f"{median:+.6f}")
            + f" | {block['gate_better']} | {block['tied']} "
            f"| {block['gate_worse']} |"
        )
    lines.extend(
        [
            "",
            "Both arms run on the same board from the same pool, seed and "
            "forced keys, so the difference is the acceptance rule and "
            "nothing else. The gate is expected to lose on the first row by "
            "construction -- it refuses moves the sum rule would take -- so "
            "that row is a check that the arms really differ, not a result. "
            "The result is the two component rows.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=pathlib.Path, required=True)
    parser.add_argument("--json-output", type=pathlib.Path, required=True)
    parser.add_argument("--markdown-output", type=pathlib.Path, required=True)
    args = parser.parse_args()

    rows = paired_rows(args.root)
    report = summarise(rows)
    report["schema_version"] = 1
    report["verdict"] = verdict(report)
    report["boards_detail"] = rows
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=float) + "\n",
        encoding="utf-8",
    )
    args.markdown_output.write_text(markdown(report), encoding="utf-8")
    print(args.markdown_output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
