from __future__ import annotations

import copy
import pathlib
import subprocess
import sys
import unittest

from scripts.evaluate_residual_affordance_shadow_gate import (
    REQUIRED_PHYSICAL_METRICS,
)
from scripts.evaluate_residual_affordance_shadow_gate_v3 import evaluate_v3


def summary():
    return {
        "decision_invariance_negative_control": {"passed": True},
        "policy_trace_by_arm": {
            "residual_affordance_shadow": {
                "residual_affordance_observed_steps": 60,
                "residual_affordance_guarded_change_count": 12,
                "residual_affordance_attr_blocked_count": 3,
                "residual_affordance_contract_regression_count": 3,
                "residual_affordance_guarded_contract_regression_count": 0,
            }
        },
    }


def floor(base, shadow):
    return {
        "scenarios": {
            "b000-k20": {
                metric: {
                    "base": list(base),
                    "residual_affordance_shadow": list(shadow),
                }
                for metric in REQUIRED_PHYSICAL_METRICS
            }
        }
    }


def calibration():
    return [
        ("32380902237", floor((18.0, 18.0, 18.0), (999.0, 999.0, 999.0))),
        ("32381957502", floor((20.0, 20.0, 20.0), (999.0, 999.0, 999.0))),
        ("32435231411", floor((22.0, 22.0, 22.0), (999.0, 999.0, 999.0))),
    ]


class ResidualAffordanceShadowGateV3Tests(unittest.TestCase):
    def test_script_can_run_directly_like_the_workflow(self):
        root = pathlib.Path(__file__).resolve().parents[1]
        completed = subprocess.run(
            [
                sys.executable,
                str(
                    root
                    / "scripts"
                    / "evaluate_residual_affordance_shadow_gate_v3.py"
                ),
                "--help",
            ],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_external_base_floor_accepts_effect_inside_between_wave_spread(self):
        current = floor((20.0, 20.0, 20.0), (19.0, 19.0, 19.0))

        report = evaluate_v3(summary(), current, calibration())

        physical = report["gates"]["physical_footprint"]
        self.assertTrue(report["passed"])
        self.assertTrue(physical["passed"])
        self.assertEqual(physical["comparisons"][0]["reference_spread"], 4.0)
        self.assertEqual(physical["comparisons"][0]["effect"], -1.0)

    def test_calibration_ignores_every_shadow_value(self):
        current = floor((20.0, 20.0, 20.0), (19.0, 19.0, 19.0))
        controls = calibration()
        for _run_id, payload in controls:
            for metric in payload["scenarios"]["b000-k20"].values():
                metric["residual_affordance_shadow"] = [-1e9, 0.0, 1e9]

        report = evaluate_v3(summary(), current, controls)

        self.assertTrue(report["passed"])

    def test_effect_larger_than_external_base_spread_fails(self):
        current = floor((20.0, 20.0, 20.0), (30.0, 30.0, 30.0))

        report = evaluate_v3(summary(), current, calibration())

        physical = report["gates"]["physical_footprint"]
        self.assertFalse(report["passed"])
        self.assertEqual(
            len(physical["effect_breaches"]),
            len(REQUIRED_PHYSICAL_METRICS),
        )

    def test_current_base_outside_calibration_domain_invalidates_wave(self):
        current = floor((30.0, 30.0, 30.0), (30.0, 30.0, 30.0))

        report = evaluate_v3(summary(), current, calibration())

        physical = report["gates"]["physical_footprint"]
        self.assertFalse(report["passed"])
        self.assertEqual(
            len(physical["baseline_breaches"]),
            len(REQUIRED_PHYSICAL_METRICS),
        )

    def test_missing_calibration_metric_fails_closed(self):
        controls = copy.deepcopy(calibration())
        del controls[0][1]["scenarios"]["b000-k20"]["soft_clean_ratio"]
        current = floor((20.0, 20.0, 20.0), (20.0, 20.0, 20.0))

        report = evaluate_v3(summary(), current, controls)

        self.assertFalse(report["passed"])
        self.assertIn(
            {"case_id": "b000-k20", "metric": "soft_clean_ratio"},
            report["gates"]["physical_footprint"]["missing"],
        )

    def test_substituting_a_calibration_wave_fails_closed(self):
        controls = calibration()
        controls[0] = ("posthoc-wave", controls[0][1])
        current = floor((20.0, 20.0, 20.0), (20.0, 20.0, 20.0))

        report = evaluate_v3(summary(), current, controls)

        self.assertFalse(report["passed"])
        self.assertFalse(
            report["gates"]["physical_footprint"]["calibration_set_valid"]
        )


if __name__ == "__main__":
    unittest.main()
