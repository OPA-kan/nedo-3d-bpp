from __future__ import annotations

import unittest

from scripts.run_checks import evaluation_passed


class EvaluationStatusTests(unittest.TestCase):
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
                "place_states": {
                    "is_included": True,
                    "is_valid": False,
                    "is_placed_safe": False,
                },
            }
        }
        self.assertFalse(evaluation_passed(evaluation))

    def test_missing_or_empty_evaluation_fails(self) -> None:
        self.assertFalse(evaluation_passed(None))
        self.assertFalse(evaluation_passed({}))


if __name__ == "__main__":
    unittest.main()
