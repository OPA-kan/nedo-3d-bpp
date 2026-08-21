from __future__ import annotations

import unittest

from scripts.evaluate_residual_affordance_shadow_gate import evaluate


def summary(*, invariant_passed=True, guarded_changes=12):
    return {
        "decision_invariance_negative_control": {
            "passed": invariant_passed,
        },
        "policy_trace_by_arm": {
            "residual_affordance_shadow": {
                "residual_affordance_observed_steps": 60,
                "residual_affordance_guarded_change_count": guarded_changes,
                "residual_affordance_attr_blocked_count": 3,
                "residual_affordance_contract_regression_count": 3,
                "residual_affordance_guarded_contract_regression_count": 0,
            }
        },
    }


def noise_floor(*, shadow_placed=(19.0, 20.0, 21.0)):
    metrics = {
        "placed": {
            "base": [18.0, 20.0, 22.0],
            "residual_affordance_shadow": list(shadow_placed),
        },
        "fill": {
            "base": [20.0, 22.0, 24.0],
            "residual_affordance_shadow": [21.0, 22.0, 23.0],
        },
        "policy_seconds": {
            "base": [6.2, 6.4, 6.6],
            "residual_affordance_shadow": [6.3, 6.4, 6.5],
        },
        "priority_clean_ratio": {
            "base": [0.8, 0.9, 1.0],
            "residual_affordance_shadow": [0.85, 0.9, 0.95],
        },
        "soft_clean_ratio": {
            "base": [1.0, 1.0, 1.0],
            "residual_affordance_shadow": [1.0, 1.0, 1.0],
        },
    }
    for name in (
        "shake_max_shift",
        "shake_peak_kinetic_energy",
        "shake_items_shifted",
        "shake_items_toppled",
        "shake_shifted_fraction",
        "terminal_included",
        "terminal_valid",
        "terminal_placed_safe",
    ):
        metrics[name] = {
            "base": [1.0, 2.0, 3.0],
            "residual_affordance_shadow": [1.0, 2.0, 3.0],
        }
    return {"scenarios": {"b000-k20": metrics}}


class ResidualAffordanceShadowGateTests(unittest.TestCase):
    def test_passes_same_call_attribute_reach_and_physical_footprint(self):
        report = evaluate(summary(), noise_floor())

        self.assertTrue(report["passed"])
        self.assertTrue(report["gates"]["decision_invariance"]["passed"])
        self.assertTrue(report["gates"]["attribute_safety"]["passed"])
        self.assertTrue(report["gates"]["reach"]["passed"])
        self.assertTrue(report["gates"]["physical_footprint"]["passed"])

    def test_physical_footprint_fails_when_mean_clears_base_spread(self):
        report = evaluate(
            summary(), noise_floor(shadow_placed=(30.0, 31.0, 32.0))
        )

        physical = report["gates"]["physical_footprint"]
        self.assertFalse(report["passed"])
        self.assertFalse(physical["passed"])
        self.assertEqual(physical["breaches"][0]["metric"], "placed")

    def test_missing_required_metric_fails_instead_of_disappearing(self):
        floor = noise_floor()
        del floor["scenarios"]["b000-k20"]["soft_clean_ratio"]

        report = evaluate(summary(), floor)

        self.assertFalse(report["passed"])
        self.assertIn(
            {"case_id": "b000-k20", "metric": "soft_clean_ratio"},
            report["gates"]["physical_footprint"]["missing"],
        )

    def test_attribute_gate_requires_every_regression_to_be_blocked(self):
        payload = summary()
        trace = payload["policy_trace_by_arm"][
            "residual_affordance_shadow"
        ]
        trace["residual_affordance_attr_blocked_count"] = 2

        report = evaluate(payload, noise_floor())

        self.assertFalse(report["gates"]["attribute_safety"]["passed"])


if __name__ == "__main__":
    unittest.main()
