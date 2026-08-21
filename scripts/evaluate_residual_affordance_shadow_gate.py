"""Adjudicate the preregistered residual-affordance shadow v2 gates."""
from __future__ import annotations

import argparse
import json
import pathlib
import statistics
from typing import Any


SHADOW_ARM = "residual_affordance_shadow"
MINIMUM_OBSERVED = 50
MINIMUM_GUARDED_CHANGES = 5
MINIMUM_REPEATS = 3
REQUIRED_PHYSICAL_METRICS = (
    "placed",
    "fill",
    "policy_seconds",
    "priority_clean_ratio",
    "soft_clean_ratio",
    "shake_max_shift",
    "shake_peak_kinetic_energy",
    "shake_items_shifted",
    "shake_items_toppled",
    "shake_shifted_fraction",
    "terminal_included",
    "terminal_valid",
    "terminal_placed_safe",
)


def _series(metric: dict[str, Any], arm: str) -> list[float]:
    values = metric.get(arm)
    if not isinstance(values, list):
        return []
    return [float(value) for value in values if isinstance(value, (int, float))]


def evaluate(summary: dict[str, Any], noise_floor: dict[str, Any]) -> dict[str, Any]:
    decision = summary.get("decision_invariance_negative_control") or {}
    trace = (summary.get("policy_trace_by_arm") or {}).get(SHADOW_ARM) or {}
    observed = int(trace.get("residual_affordance_observed_steps", 0))
    guarded_changes = int(
        trace.get("residual_affordance_guarded_change_count", 0)
    )
    unrestricted_regressions = int(
        trace.get("residual_affordance_contract_regression_count", 0)
    )
    blocked = int(trace.get("residual_affordance_attr_blocked_count", 0))
    guarded_regressions = int(
        trace.get(
            "residual_affordance_guarded_contract_regression_count", 0
        )
    )

    physical_comparisons = []
    physical_breaches = []
    physical_missing = []
    scenarios = noise_floor.get("scenarios") or {}
    for case_id, metrics in sorted(scenarios.items()):
        if not isinstance(metrics, dict):
            continue
        for metric_name in REQUIRED_PHYSICAL_METRICS:
            metric = metrics.get(metric_name)
            if not isinstance(metric, dict):
                physical_missing.append(
                    {"case_id": case_id, "metric": metric_name}
                )
                continue
            base = _series(metric, "base")
            shadow = _series(metric, SHADOW_ARM)
            if len(base) < MINIMUM_REPEATS or len(shadow) < MINIMUM_REPEATS:
                physical_missing.append(
                    {"case_id": case_id, "metric": metric_name}
                )
                continue
            base_mean = statistics.fmean(base)
            shadow_mean = statistics.fmean(shadow)
            base_spread = max(base) - min(base)
            delta = shadow_mean - base_mean
            comparison = {
                "case_id": case_id,
                "metric": metric_name,
                "base_mean": round(base_mean, 9),
                "shadow_mean": round(shadow_mean, 9),
                "delta": round(delta, 9),
                "base_spread": round(base_spread, 9),
                "within": abs(delta) <= base_spread + 1e-12,
            }
            physical_comparisons.append(comparison)
            if not comparison["within"]:
                physical_breaches.append(comparison)

    gates = {
        "decision_invariance": {
            "passed": decision.get("passed") is True,
            "evidence": decision,
        },
        "reach": {
            "minimum_observed": MINIMUM_OBSERVED,
            "minimum_guarded_changes": MINIMUM_GUARDED_CHANGES,
            "observed": observed,
            "guarded_changes": guarded_changes,
            "passed": (
                observed >= MINIMUM_OBSERVED
                and guarded_changes >= MINIMUM_GUARDED_CHANGES
            ),
        },
        "attribute_safety": {
            "unrestricted_regressions": unrestricted_regressions,
            "blocked": blocked,
            "guarded_regressions": guarded_regressions,
            "passed": (
                guarded_regressions == 0
                and blocked == unrestricted_regressions
            ),
        },
        "physical_footprint": {
            "minimum_repeats": MINIMUM_REPEATS,
            "comparisons": physical_comparisons,
            "breaches": physical_breaches,
            "missing": physical_missing,
            "passed": bool(
                scenarios
                and physical_comparisons
                and not physical_breaches
                and not physical_missing
            ),
        },
    }
    return {
        "schema_version": 1,
        "protocol": "residual-affordance-shadow-negative-control-v2",
        "passed": all(gate["passed"] for gate in gates.values()),
        "gates": gates,
        "action_sequence_hash_role": "diagnostic_only",
    }


def render_markdown(report: dict[str, Any]) -> str:
    gates = report["gates"]
    lines = [
        "# Residual-affordance shadow gate v2",
        "",
        f"Overall: **{'PASS' if report['passed'] else 'FAIL'}**",
        "",
        "| gate | passed | detail |",
        "|---|---|---|",
    ]
    decision = gates["decision_invariance"]
    reach = gates["reach"]
    attribute = gates["attribute_safety"]
    physical = gates["physical_footprint"]
    lines += [
        f"| same-call decision invariance | {decision['passed']} "
        f"| {json.dumps(decision['evidence'], sort_keys=True)} |",
        f"| reach | {reach['passed']} | observed {reach['observed']}; "
        f"guarded changes {reach['guarded_changes']} |",
        f"| attribute safety | {attribute['passed']} | unrestricted "
        f"{attribute['unrestricted_regressions']}; blocked "
        f"{attribute['blocked']}; guarded {attribute['guarded_regressions']} |",
        f"| physical footprint | {physical['passed']} | comparisons "
        f"{len(physical['comparisons'])}; breaches "
        f"{len(physical['breaches'])}; missing {len(physical['missing'])} |",
        "",
        "Cross-process action hashes are diagnostic only because identical "
        "base episodes have already produced different hashes.",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--summary", type=pathlib.Path, required=True)
    parser.add_argument("--noise-floor", type=pathlib.Path, required=True)
    parser.add_argument("--output-json", type=pathlib.Path)
    parser.add_argument("--output-md", type=pathlib.Path)
    parser.add_argument("--require-pass", action="store_true")
    args = parser.parse_args()
    report = evaluate(
        json.loads(args.summary.read_text(encoding="utf-8")),
        json.loads(args.noise_floor.read_text(encoding="utf-8")),
    )
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
