"""Adjudicate the externally calibrated residual-affordance shadow v3 gates."""
from __future__ import annotations

import argparse
import json
import pathlib
import statistics
from typing import Any

try:
    from scripts.evaluate_residual_affordance_shadow_gate import (
        MINIMUM_REPEATS,
        REQUIRED_PHYSICAL_METRICS,
        SHADOW_ARM,
        _series,
        evaluate,
    )
except ModuleNotFoundError:  # Direct execution: python scripts/<file>.py
    from evaluate_residual_affordance_shadow_gate import (
        MINIMUM_REPEATS,
        REQUIRED_PHYSICAL_METRICS,
        SHADOW_ARM,
        _series,
        evaluate,
    )


MINIMUM_CALIBRATION_WAVES = 3
REQUIRED_CALIBRATION_RUN_IDS = (
    "32380902237",
    "32381957502",
    "32435231411",
)
EPSILON = 1e-12


def evaluate_v3(
    summary: dict[str, Any],
    current_noise_floor: dict[str, Any],
    calibrations: list[tuple[str, dict[str, Any]]],
) -> dict[str, Any]:
    """Evaluate a prospective wave against base-only historical calibration."""
    report = evaluate(summary, current_noise_floor)
    scenarios = current_noise_floor.get("scenarios") or {}
    comparisons: list[dict[str, Any]] = []
    effect_breaches: list[dict[str, Any]] = []
    baseline_breaches: list[dict[str, Any]] = []
    missing: list[dict[str, str]] = []
    calibration_run_ids = [run_id for run_id, _ in calibrations]
    calibration_set_valid = (
        len(calibration_run_ids) == MINIMUM_CALIBRATION_WAVES
        and set(calibration_run_ids) == set(REQUIRED_CALIBRATION_RUN_IDS)
    )

    for case_id, metrics in sorted(scenarios.items()):
        if not isinstance(metrics, dict):
            continue
        for metric_name in REQUIRED_PHYSICAL_METRICS:
            current_metric = metrics.get(metric_name)
            current_base = (
                _series(current_metric, "base")
                if isinstance(current_metric, dict)
                else []
            )
            current_shadow = (
                _series(current_metric, SHADOW_ARM)
                if isinstance(current_metric, dict)
                else []
            )
            calibration_base: list[float] = []
            calibration_complete = calibration_set_valid
            for _run_id, calibration in calibrations:
                calibration_metric = (
                    ((calibration.get("scenarios") or {}).get(case_id) or {}).get(
                        metric_name
                    )
                )
                values = (
                    _series(calibration_metric, "base")
                    if isinstance(calibration_metric, dict)
                    else []
                )
                if len(values) < MINIMUM_REPEATS:
                    calibration_complete = False
                calibration_base.extend(values)

            if (
                len(current_base) < MINIMUM_REPEATS
                or len(current_shadow) < MINIMUM_REPEATS
                or not calibration_complete
            ):
                missing.append({"case_id": case_id, "metric": metric_name})
                continue

            reference_center = statistics.fmean(calibration_base)
            reference_spread = max(calibration_base) - min(calibration_base)
            current_base_mean = statistics.fmean(current_base)
            current_shadow_mean = statistics.fmean(current_shadow)
            effect = current_shadow_mean - current_base_mean
            comparison = {
                "case_id": case_id,
                "metric": metric_name,
                "reference_center": round(reference_center, 9),
                "reference_spread": round(reference_spread, 9),
                "current_base_mean": round(current_base_mean, 9),
                "current_shadow_mean": round(current_shadow_mean, 9),
                "effect": round(effect, 9),
                "baseline_within_calibration": (
                    abs(current_base_mean - reference_center)
                    <= reference_spread + EPSILON
                ),
                "effect_within_calibration": (
                    abs(effect) <= reference_spread + EPSILON
                ),
            }
            comparisons.append(comparison)
            if not comparison["baseline_within_calibration"]:
                baseline_breaches.append(comparison)
            if not comparison["effect_within_calibration"]:
                effect_breaches.append(comparison)

    physical = {
        "minimum_repeats": MINIMUM_REPEATS,
        "minimum_calibration_waves": MINIMUM_CALIBRATION_WAVES,
        "required_calibration_run_ids": list(REQUIRED_CALIBRATION_RUN_IDS),
        "calibration_run_ids": calibration_run_ids,
        "calibration_set_valid": calibration_set_valid,
        "calibration_arms": ["base"],
        "comparisons": comparisons,
        "baseline_breaches": baseline_breaches,
        "effect_breaches": effect_breaches,
        "missing": missing,
        "passed": bool(
            scenarios
            and comparisons
            and calibration_set_valid
            and not baseline_breaches
            and not effect_breaches
            and not missing
        ),
    }
    report["schema_version"] = 2
    report["protocol"] = "residual-affordance-shadow-negative-control-v3"
    report["gates"]["physical_footprint"] = physical
    report["passed"] = all(gate["passed"] for gate in report["gates"].values())
    report["calibration_policy"] = (
        "historical base arms only; all calibration shadow values ignored"
    )
    return report


def render_markdown(report: dict[str, Any]) -> str:
    gates = report["gates"]
    decision = gates["decision_invariance"]
    reach = gates["reach"]
    attribute = gates["attribute_safety"]
    physical = gates["physical_footprint"]
    lines = [
        "# Residual-affordance shadow gate v3",
        "",
        f"Overall: **{'PASS' if report['passed'] else 'FAIL'}**",
        "",
        "Calibration runs: " + ", ".join(physical["calibration_run_ids"]),
        "Calibration arms: `base` only (calibration shadow values are ignored).",
        "",
        "| gate | passed | detail |",
        "|---|---|---|",
        f"| same-call decision invariance | {decision['passed']} | "
        f"{json.dumps(decision['evidence'], sort_keys=True)} |",
        f"| reach | {reach['passed']} | observed {reach['observed']}; "
        f"guarded changes {reach['guarded_changes']} |",
        f"| attribute safety | {attribute['passed']} | unrestricted "
        f"{attribute['unrestricted_regressions']}; blocked "
        f"{attribute['blocked']}; guarded {attribute['guarded_regressions']} |",
        f"| physical footprint | {physical['passed']} | comparisons "
        f"{len(physical['comparisons'])}; baseline breaches "
        f"{len(physical['baseline_breaches'])}; effect breaches "
        f"{len(physical['effect_breaches'])}; missing "
        f"{len(physical['missing'])} |",
        "",
        "The prospective effect is the current shadow mean minus its simultaneous "
        "base mean. The tolerance is the full spread of historical base-only runs.",
        "Cross-process action hashes remain diagnostic only.",
    ]
    return "\n".join(lines) + "\n"


def _parse_calibration(value: str) -> tuple[str, pathlib.Path]:
    run_id, separator, path = value.partition("=")
    if not separator or not run_id or not path:
        raise argparse.ArgumentTypeError("expected RUN_ID=PATH")
    return run_id, pathlib.Path(path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--summary", type=pathlib.Path, required=True)
    parser.add_argument("--noise-floor", type=pathlib.Path, required=True)
    parser.add_argument(
        "--calibration-noise-floor",
        type=_parse_calibration,
        action="append",
        required=True,
        metavar="RUN_ID=PATH",
    )
    parser.add_argument("--output-json", type=pathlib.Path)
    parser.add_argument("--output-md", type=pathlib.Path)
    parser.add_argument("--require-pass", action="store_true")
    args = parser.parse_args()
    calibrations = [
        (run_id, json.loads(path.read_text(encoding="utf-8")))
        for run_id, path in args.calibration_noise_floor
    ]
    report = evaluate_v3(
        json.loads(args.summary.read_text(encoding="utf-8")),
        json.loads(args.noise_floor.read_text(encoding="utf-8")),
        calibrations,
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
