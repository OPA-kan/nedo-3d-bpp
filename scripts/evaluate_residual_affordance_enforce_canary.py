"""Adjudicate the preregistered guarded residual-affordance canary."""
from __future__ import annotations

import argparse
import json
import pathlib
from typing import Any


BASE_ARM = "base"
ENFORCE_ARM = "residual_affordance_enforce"
MINIMUM_EPISODES = 15
MINIMUM_ENFORCED = 5
EPSILON = 1e-12


def _comparison(
    arms: dict[str, Any],
    metric: str,
    *,
    higher_is_better: bool,
    missing: list[dict[str, str]],
) -> dict[str, Any] | None:
    values = {}
    for arm in (BASE_ARM, ENFORCE_ARM):
        record = (arms.get(arm) or {}).get(metric)
        if (
            not isinstance(record, dict)
            or int(record.get("n", 0)) < MINIMUM_EPISODES
            or not isinstance(record.get("mean"), (int, float))
        ):
            missing.append({"arm": arm, "metric": metric})
            return None
        values[arm] = float(record["mean"])
    delta = values[ENFORCE_ARM] - values[BASE_ARM]
    passed = delta >= -EPSILON if higher_is_better else delta <= EPSILON
    return {
        "metric": metric,
        "direction": "higher" if higher_is_better else "lower",
        "base_mean": values[BASE_ARM],
        "enforce_mean": values[ENFORCE_ARM],
        "delta": round(delta, 9),
        "passed": passed,
    }


def _gate(
    arms: dict[str, Any],
    metrics: tuple[str, ...],
    *,
    higher_is_better: bool,
    missing: list[dict[str, str]],
) -> dict[str, Any]:
    comparisons = [
        comparison
        for metric in metrics
        if (
            comparison := _comparison(
                arms,
                metric,
                higher_is_better=higher_is_better,
                missing=missing,
            )
        )
        is not None
    ]
    return {
        "comparisons": comparisons,
        "passed": (
            len(comparisons) == len(metrics)
            and all(item["passed"] for item in comparisons)
        ),
    }


def evaluate(summary: dict[str, Any]) -> dict[str, Any]:
    arms = summary.get("arms") or {}
    trace = (summary.get("policy_trace_by_arm") or {}).get(ENFORCE_ARM) or {}
    missing: list[dict[str, str]] = []

    trajectory = _gate(
        arms,
        ("placed", "fill", "steps"),
        higher_is_better=True,
        missing=missing,
    )
    trajectory["strict_score_gain"] = any(
        comparison["metric"] in {"placed", "fill"}
        and comparison["delta"] > EPSILON
        for comparison in trajectory["comparisons"]
    )
    trajectory["passed"] = bool(
        trajectory["passed"] and trajectory["strict_score_gain"]
    )
    attributes = _gate(
        arms,
        ("priority_clean", "soft_clean"),
        higher_is_better=True,
        missing=missing,
    )
    physical = _gate(
        arms,
        (
            "shake_max_shift",
            "shake_peak_ke",
            "shake_shifted",
            "shake_toppled",
            "shake_shifted_fraction",
        ),
        higher_is_better=False,
        missing=missing,
    )
    terminal = _gate(
        arms,
        (
            "terminal_included",
            "terminal_valid",
            "terminal_placed_safe",
        ),
        higher_is_better=True,
        missing=missing,
    )
    enforced = int(trace.get("residual_affordance_enforced_count", 0))
    guarded_regressions = int(
        trace.get(
            "residual_affordance_guarded_contract_regression_count", 0
        )
    )
    reach = {
        "minimum_enforced": MINIMUM_ENFORCED,
        "enforced": enforced,
        "guarded_contract_regressions": guarded_regressions,
        "passed": enforced >= MINIMUM_ENFORCED and guarded_regressions == 0,
    }
    gates = {
        "causal_reach": reach,
        "trajectory_value": trajectory,
        "attribute_safety": attributes,
        "physical_safety": physical,
        "terminal_validity": terminal,
    }
    return {
        "schema_version": 1,
        "protocol": "residual-affordance-guarded-enforce-canary-v1",
        "passed": not missing and all(gate["passed"] for gate in gates.values()),
        "gates": gates,
        "missing": missing,
        "weighted_total": None,
        "action_sequence_hash_role": "diagnostic_only",
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Residual-affordance guarded-enforce canary v1",
        "",
        f"Overall: **{'PASS' if report['passed'] else 'FAIL'}**",
        "",
        "| gate | passed | detail |",
        "|---|---|---|",
    ]
    for name, gate in report["gates"].items():
        detail = {
            key: value
            for key, value in gate.items()
            if key not in {"passed", "comparisons"}
        }
        if "comparisons" in gate:
            detail["deltas"] = {
                item["metric"]: item["delta"]
                for item in gate["comparisons"]
            }
        lines.append(
            f"| {name} | {gate['passed']} | "
            f"{json.dumps(detail, sort_keys=True)} |"
        )
    lines += [
        "",
        f"Missing metrics: {len(report['missing'])}",
        "No weighted total is formed; every safety axis is an independent veto.",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--summary", type=pathlib.Path, required=True)
    parser.add_argument("--output-json", type=pathlib.Path)
    parser.add_argument("--output-md", type=pathlib.Path)
    parser.add_argument("--require-pass", action="store_true")
    args = parser.parse_args()
    report = evaluate(json.loads(args.summary.read_text(encoding="utf-8")))
    if args.output_json:
        args.output_json.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    markdown = render_markdown(report)
    if args.output_md:
        args.output_md.write_text(markdown, encoding="utf-8")
    print(markdown, end="")
    return int(args.require_pass and not report["passed"])


if __name__ == "__main__":
    raise SystemExit(main())
