from __future__ import annotations

import unittest
from unittest import mock

from scripts.run_checks import (
    evaluation_completed,
    evaluation_passed,
    simulator_result_passed,
    unit_test_environment,
)


class EvaluationStatusTests(unittest.TestCase):
    def test_unit_tests_do_not_pollute_simulator_policy_trace(self) -> None:
        with mock.patch.dict(
            "os.environ",
            {
                "NEDO_POLICY_TRACE_PATH": "reports/raw/policy-trace.jsonl",
                "LOOKAHEAD_SELECTION_MODE": "depth2",
                "ITEM_COVERAGE_MODE": "legacy",
                "RELEASE_RISK_GATE_MODE": "enforce",
                "KEEP_ME": "yes",
            },
            clear=True,
        ):
            env = unit_test_environment()
        self.assertNotIn("NEDO_POLICY_TRACE_PATH", env)
        self.assertNotIn("LOOKAHEAD_SELECTION_MODE", env)
        self.assertNotIn("ITEM_COVERAGE_MODE", env)
        self.assertNotIn("RELEASE_RISK_GATE_MODE", env)
        self.assertEqual(env["KEEP_ME"], "yes")

    def test_valid_safe_cases_pass(self) -> None:
        evaluation = {
            "000": {
                "status": "success",
                "place_states": {
                    "is_included": True,
                    "is_valid": True,
                    "is_placed_safe": True,
                },
            }
        }
        self.assertTrue(evaluation_passed(evaluation))

    def test_process_success_does_not_hide_physics_failure(self) -> None:
        evaluation = {
            "000": {
                "status": "success",
                "evaluation": {
                    "fill_score": 10.0,
                    "num_placed_items": 0.5,
                    "step_metrics": [],
                },
                "place_states": {
                    "is_included": True,
                    "is_valid": False,
                    "is_placed_safe": False,
                },
                "time_results": {
                    "optimization": 0.0,
                    "policy": 6.5,
                },
            }
        }
        self.assertFalse(evaluation_passed(evaluation))
        self.assertTrue(evaluation_completed(evaluation))
        self.assertFalse(
            simulator_result_passed(
                simulator_returncode=0,
                evaluation=evaluation,
                mode="strict",
            )
        )
        self.assertTrue(
            simulator_result_passed(
                simulator_returncode=0,
                evaluation=evaluation,
                mode="benchmark",
            )
        )

    def test_missing_or_empty_evaluation_fails(self) -> None:
        self.assertFalse(evaluation_passed(None))
        self.assertFalse(evaluation_passed({}))
        self.assertFalse(evaluation_completed(None))
        self.assertFalse(evaluation_completed({}))

    def test_benchmark_does_not_hide_process_or_result_failure(self) -> None:
        malformed = {
            "000": {
                "status": "format_error",
                "evaluation": None,
                "place_states": {},
                "time_results": {},
            }
        }
        self.assertFalse(
            simulator_result_passed(
                simulator_returncode=1,
                evaluation=malformed,
                mode="benchmark",
            )
        )
        self.assertFalse(
            simulator_result_passed(
                simulator_returncode=0,
                evaluation=malformed,
                mode="benchmark",
            )
        )

    def test_benchmark_rejects_incomplete_score_schema(self) -> None:
        incomplete = {
            "000": {
                "status": "success",
                "evaluation": {},
                "place_states": {
                    "is_included": True,
                    "is_valid": False,
                    "is_placed_safe": False,
                },
                "time_results": {
                    "optimization": 0.0,
                    "policy": 6.5,
                },
            }
        }
        self.assertFalse(evaluation_completed(incomplete))
        self.assertFalse(
            simulator_result_passed(
                simulator_returncode=0,
                evaluation=incomplete,
                mode="strict",
            )
        )


if __name__ == "__main__":
    unittest.main()
