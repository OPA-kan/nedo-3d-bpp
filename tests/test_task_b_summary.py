from __future__ import annotations

import unittest

from scripts.summarize_task_b import build_task_b_summary


class TaskBSummaryTests(unittest.TestCase):
    def test_builds_compact_case_table(self) -> None:
        payload = {
            "git_sha": "abc123",
            "simulator_mode": "benchmark",
            "simulator_validation": False,
            "simulator_execution_valid": True,
            "evaluation": {
                "task-b-k10": {
                    "status": "success",
                    "evaluation": {
                        "fill_score": 17.9481,
                        "num_placed_items": 18 / 42,
                        "step_metrics": [
                            {
                                "step": 18,
                                "placed_count": 18,
                                "selected_item_index": 0,
                                "status": {
                                    "is_placed_safe": False,
                                },
                            }
                        ],
                    },
                    "time_results": {
                        "optimization": 0.0,
                        "policy": 6.52,
                    },
                }
            },
        }

        summary = build_task_b_summary(
            payload,
            look_ahead=10,
            selection_mode="weighted",
        )

        self.assertIn("Task B benchmark: k=10, weighted", summary)
        self.assertIn("| task-b-k10 | 18/42 | 42.9% | 17.948", summary)
        self.assertIn("| 18 | 0 | false | 6.520 s |", summary)
        self.assertIn("Benchmark execution: `valid`", summary)
        self.assertIn("Full packing: `incomplete`", summary)


if __name__ == "__main__":
    unittest.main()
