from __future__ import annotations

import copy
import unittest

from scripts.evaluate_residual_affordance_enforce_canary import evaluate


BASE = "base"
ENFORCE = "residual_affordance_enforce"


def arm_metrics():
    return {
        "placed": {"n": 15, "mean": 20.0},
        "fill": {"n": 15, "mean": 20.0},
        "steps": {"n": 15, "mean": 21.0},
        "priority_clean": {"n": 15, "mean": 1.0},
        "soft_clean": {"n": 15, "mean": 1.0},
        "shake_max_shift": {"n": 15, "mean": 1.0},
        "shake_peak_ke": {"n": 15, "mean": 1.0},
        "shake_shifted": {"n": 15, "mean": 1.0},
        "shake_toppled": {"n": 15, "mean": 1.0},
        "shake_shifted_fraction": {"n": 15, "mean": 1.0},
        "terminal_included": {"n": 15, "mean": 1.0},
        "terminal_valid": {"n": 15, "mean": 1.0},
        "terminal_placed_safe": {"n": 15, "mean": 1.0},
    }


def passing_summary():
    base = arm_metrics()
    enforce = copy.deepcopy(base)
    enforce["placed"]["mean"] = 21.0
    enforce["fill"]["mean"] = 21.0
    enforce["steps"]["mean"] = 22.0
    enforce["shake_max_shift"]["mean"] = 0.9
    return {
        "arms": {BASE: base, ENFORCE: enforce},
        "policy_trace_by_arm": {
            ENFORCE: {
                "residual_affordance_enforced_count": 8,
                "residual_affordance_guarded_contract_regression_count": 0,
            }
        },
    }


class ResidualAffordanceEnforceCanaryTests(unittest.TestCase):
    def test_all_independent_gates_pass(self):
        report = evaluate(passing_summary())

        self.assertTrue(report["passed"])
        self.assertTrue(all(gate["passed"] for gate in report["gates"].values()))

    def test_score_gain_cannot_hide_fill_regression(self):
        payload = passing_summary()
        payload["arms"][ENFORCE]["placed"]["mean"] = 30.0
        payload["arms"][ENFORCE]["fill"]["mean"] = 19.9

        report = evaluate(payload)

        self.assertFalse(report["gates"]["trajectory_value"]["passed"])

    def test_soft_regression_fails_without_weighted_compensation(self):
        payload = passing_summary()
        payload["arms"][ENFORCE]["soft_clean"]["mean"] = 0.99

        report = evaluate(payload)

        self.assertFalse(report["gates"]["attribute_safety"]["passed"])

    def test_any_shake_regression_vetoes_canary(self):
        payload = passing_summary()
        payload["arms"][ENFORCE]["shake_peak_ke"]["mean"] = 1.01

        report = evaluate(payload)

        self.assertFalse(report["gates"]["physical_safety"]["passed"])

    def test_missing_repeats_fail_closed(self):
        payload = passing_summary()
        payload["arms"][ENFORCE]["placed"]["n"] = 14

        report = evaluate(payload)

        self.assertFalse(report["passed"])
        self.assertIn(
            {"arm": ENFORCE, "metric": "placed"},
            report["missing"],
        )


if __name__ == "__main__":
    unittest.main()
