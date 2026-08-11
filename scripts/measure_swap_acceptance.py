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
import math
import pathlib
import statistics
from typing import Any

SHIPPED = "swap_optimizer"
SHADOW = "swap_optimizer_shadow"
SUM_RULE = "sum"
GATE_RULE = "pareto_gate"
RULES = (SUM_RULE, GATE_RULE)
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
            traces = [
                split.get(SHIPPED) or {},
                split.get(SHADOW) or {},
            ]
            # Key on the rule each trace ran, never on the slot it sits in.
            # Adopting the gate swapped the two slots, and a reader that
            # assumed the old assignment reported every column with its sign
            # flipped and its label inverted -- the gate's replicated
            # consumption win came out as "sum_better".
            by_rule = {
                str(trace.get("acceptance")): trace
                for trace in traces
                if trace.get("acceptance") in RULES
            }
            if set(by_rule) != set(RULES):
                continue
            sum_arm = by_rule[SUM_RULE]
            gate_arm = by_rule[GATE_RULE]
            row: dict[str, Any] = {
                "source": str(path.parent),
                "case_id": str(case.get("case_id")),
                "step": step.get("step"),
                "shipped_rule": str(
                    (split.get(SHIPPED) or {}).get("acceptance")
                ),
                # Only the sum rule can take a move that costs a component,
                # and only the gate can refuse one. Read each from its own.
                "degrading_swaps": int(
                    sum_arm.get("component_degrading_swaps", 0)
                ),
                "refused_by_gate": int(
                    gate_arm.get("swaps_refused_by_gate", 0)
                ),
                "sum_rule_swaps": int(sum_arm.get("swaps_applied", 0)),
                "gate_swaps": int(gate_arm.get("swaps_applied", 0)),
            }
            for arm, trace in (("sum_rule", sum_arm), ("gate", gate_arm)):
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
            row[f"gate_{name}"] - row[f"sum_rule_{name}"]
            for row in rows
            if row.get(f"gate_{name}") is not None
            and row.get(f"sum_rule_{name}") is not None
        ]

    report: dict[str, Any] = {
        "boards": len(rows),
        "boards_with_a_degrading_swap": sum(
            1 for row in rows if row["degrading_swaps"] > 0
        ),
        "degrading_swaps": sum(row["degrading_swaps"] for row in rows),
        "sum_rule_swaps": sum(row["sum_rule_swaps"] for row in rows),
        "gate_swaps": sum(row["gate_swaps"] for row in rows),
        "shipped_rules": sorted(
            {row["shipped_rule"] for row in rows}
        ),
        "swaps_refused_by_gate": sum(row["refused_by_gate"] for row in rows),
    }
    # Adoption question, separate from the comparison: the acceptance guard
    # tests the single sum, and the gate lowers it. Would any board fall to
    # or below zero and turn a passing condition into a failing one?
    for arm in ("sum_rule", "gate"):
        sums = [row[f"{arm}_sum"] for row in rows if row.get(f"{arm}_sum")]
        report[f"{arm}_guard_number"] = {
            "minimum": min(sums) if sums else None,
            "mean": statistics.fmean(sums) if sums else None,
            "boards_at_or_below_zero": sum(value <= 0.0 for value in sums),
        }
    for name in ("sum", *COMPONENTS):
        values = paired(name)
        better = sum(v > 0 for v in values)
        worse = sum(v < 0 for v in values)
        report[f"gate_minus_sum_{name}"] = {
            "boards": len(values),
            "mean": statistics.fmean(values) if values else None,
            "median": statistics.median(values) if values else None,
            "gate_better": better,
            "tied": sum(v == 0 for v in values),
            "gate_worse": worse,
            "sign_test_p": sign_test(better, worse),
            "direction": direction(
                better,
                worse,
                statistics.fmean(values) if values else None,
            ),
        }
    return report


def sign_test(better: int, worse: int) -> float:
    """Two-sided exact sign test on the paired wins and losses.

    A mean with the right sign is not a result. Occupancy came out at
    +0.0019 with 24 boards better and 13 worse, which reads as a win and is
    not one: p is about 0.1. The verdict reads this, not the mean.
    """
    total = better + worse
    if total == 0:
        return 1.0
    smaller = min(better, worse)
    tail = sum(math.comb(total, k) for k in range(smaller + 1)) / 2**total
    return min(1.0, 2.0 * tail)


SIGNIFICANCE = 0.05


def direction(better: int, worse: int, mean: float | None) -> str:
    if mean is None:
        return "unmeasured"
    if sign_test(better, worse) >= SIGNIFICANCE:
        return "indistinguishable"
    return "gate_better" if mean > 0 else "sum_better"


def verdict(report: dict[str, Any]) -> str:
    if not report["boards"]:
        return "no_paired_boards"
    if report["degrading_swaps"] == 0:
        return "acceptance_rule_cannot_matter_here"
    calls = {
        name: report[f"gate_minus_sum_{name}"]["direction"]
        for name in COMPONENTS
    }
    if any(value == "unmeasured" for value in calls.values()):
        return "insufficient_component_coverage"
    wins = sorted(k for k, v in calls.items() if v == "gate_better")
    losses = sorted(k for k, v in calls.items() if v == "sum_better")
    if wins and losses:
        return "gate_trades_one_component_for_the_other"
    if not wins and not losses:
        return "no_measurable_difference"
    if len(wins) == len(COMPONENTS):
        return "gate_dominates_on_both_components"
    if len(losses) == len(COMPONENTS):
        return "sum_dominates_on_both_components"
    if wins:
        return f"gate_wins_{wins[0]}_rest_indistinguishable"
    return f"sum_wins_{losses[0]}_rest_indistinguishable"


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
        (
            f"- {report['boards']} boards, both rules on each; the shipped "
            f"arm ran {', '.join(report['shipped_rules'])}"
        ),
        (
            f"- Shipped arm accepted {report['degrading_swaps']} swaps that "
            f"raised the sum while a component fell, on "
            f"{report['boards_with_a_degrading_swap']} boards"
        ),
        (
            f"- The gate refused {report['swaps_refused_by_gate']} moves; "
            f"{report['sum_rule_swaps']} swaps applied by the sum rule against "
            f"{report['gate_swaps']} by the gate"
        ),
        (
            "- Guard number (the sum the acceptance test reads): minimum "
            f"{report['sum_rule_guard_number']['minimum']:.6f} under the sum "
            f"rule against {report['gate_guard_number']['minimum']:.6f} "
            "under the gate; boards at or below zero, "
            f"{report['sum_rule_guard_number']['boards_at_or_below_zero']} "
            f"and {report['gate_guard_number']['boards_at_or_below_zero']}"
        ),
        "",
        "| quantity | mean gate − sum | median | gate better | tied | "
        "gate worse | sign test p | call |",
        "|---|---:|---:|---:|---:|---:|---:|---|",
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
            f"| {block['gate_worse']} | {block['sign_test_p']:.4f} "
            f"| {block['direction']} |"
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
