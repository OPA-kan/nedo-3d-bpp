from __future__ import annotations

import unittest
from unittest import mock

from scripts.run_checks import (
    evaluation_completed,
    evaluation_passed,
    externalize_output,
    report_markdown,
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
                "CROSS_STEP_INCUMBENT_MODE": "shadow",
                "CROSS_STEP_INCUMBENT_PER_ITEM": "99",
                "RELEASE_RISK_GATE_MODE": "enforce",
                "KEEP_ME": "yes",
            },
            clear=True,
        ):
            env = unit_test_environment()
        self.assertNotIn("NEDO_POLICY_TRACE_PATH", env)
        self.assertNotIn("LOOKAHEAD_SELECTION_MODE", env)
        self.assertNotIn("ITEM_COVERAGE_MODE", env)
        self.assertNotIn("CROSS_STEP_INCUMBENT_MODE", env)
        self.assertNotIn("CROSS_STEP_INCUMBENT_PER_ITEM", env)
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

class CapturedOutputTests(unittest.TestCase):
    def test_externalize_moves_logs_out_of_the_payload(self) -> None:
        import pathlib
        import tempfile

        step = {
            "stdout": "\n".join(f"line {i}" for i in range(100)),
            "stderr": "boom",
            "returncode": 0,
            "seconds": 1.0,
            "command": ["python"],
        }
        with tempfile.TemporaryDirectory() as tmp:
            raw_dir = pathlib.Path(tmp) / "raw"
            with mock.patch("scripts.run_checks.ROOT", pathlib.Path(tmp)):
                externalize_output(step, "unit-tests", raw_dir)
            log = raw_dir / "unit-tests.log"
            self.assertTrue(log.exists())
            self.assertIn("line 0", log.read_text(encoding="utf-8"))
        self.assertEqual(step["stdout"], "")
        self.assertEqual(step["stderr"], "")
        self.assertIn("boom", step["log_tail"])
        self.assertNotIn("line 0", step["log_tail"])
        self.assertLessEqual(len(step["log_tail"].splitlines()), 30)
        self.assertEqual(step["log_path"], "raw/unit-tests.log")

    def test_markdown_uses_tail_and_points_at_the_log(self) -> None:
        payload = {
            "timestamp": "t",
            "git_sha": "sha",
            "environment": {
                "python": "3",
                "platform": "linux",
                "processor": "x",
            },
            "tests": {
                "returncode": 0,
                "seconds": 1.0,
                "command": ["python", "-m", "unittest"],
                "stdout": "",
                "stderr": "",
                "log_tail": "OK (tail only)",
                "log_path": "reports/raw/unit-tests.log",
            },
        }
        markdown = report_markdown(payload)
        self.assertIn("OK (tail only)", markdown)
        self.assertIn("reports/raw/unit-tests.log", markdown)

    def test_markdown_falls_back_to_inline_output(self) -> None:
        payload = {
            "timestamp": "t",
            "git_sha": "sha",
            "environment": {
                "python": "3",
                "platform": "linux",
                "processor": "x",
            },
            "tests": {
                "returncode": 0,
                "seconds": 1.0,
                "command": ["python"],
                "stdout": "inline output",
                "stderr": "",
            },
        }
        self.assertIn("inline output", report_markdown(payload))
