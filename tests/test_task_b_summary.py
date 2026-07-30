from __future__ import annotations

import unittest

from scripts.summarize_task_b import (
    build_task_b_summary,
    task_b_result_rows,
)


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

    def test_records_coverage_and_starvation_failure_mode(self) -> None:
        payload = {
            "git_sha": "abc123",
            "simulator_validation": False,
            "simulator_execution_valid": True,
            "evaluation": {
                "task-b-k10": {
                    "status": "success",
                    "evaluation": {
                        "fill_score": 17.0,
                        "num_placed_items": 0.4,
                        "step_metrics": [
                            {
                                "step": 16,
                                "placed_count": 16,
                                "selected_item_index": 0,
                                "status": {"is_placed_safe": False},
                            }
                        ],
                    },
                    "time_results": {
                        "optimization": 0.0,
                        "policy": 6.5,
                    },
                }
            },
        }
        trace_events = [
            {
                "event": "decision",
                "step": 15,
                "action_source": "placement_core",
                "candidate_kind": "settled_candidate",
                "selected_item_index": 2,
                "coverage": {
                    "overall": {
                        "included_over_visible": 1.0,
                        "started_over_included": 0.5,
                        "generated_over_started": 0.7,
                    },
                    "by_class": {},
                },
                "item_lifecycle": [],
            },
            {
                "event": "decision",
                "step": 16,
                "action_source": "fixed_fallback",
                "candidate_kind": "fixed_fallback",
                "selected_item_index": 0,
                "coverage": {
                    "overall": {
                        "included_over_visible": 0.8,
                        "started_over_included": 0.75,
                        "generated_over_started": 0.5,
                    },
                    "by_class": {},
                },
                "item_lifecycle": [
                    {
                        "item_index": 0,
                        "selected_step": None,
                        "candidate_topk_steps": [14],
                    }
                ],
            }
        ]

        rows = task_b_result_rows(
            payload,
            look_ahead=10,
            selection_mode="weighted",
            coverage_mode="class_aware",
            replicate=2,
            trace_events=trace_events,
        )
        summary = build_task_b_summary(
            payload,
            look_ahead=10,
            selection_mode="weighted",
            coverage_mode="class_aware",
            replicate=2,
            trace_events=trace_events,
        )

        self.assertEqual(rows[0]["failure_mode"], "fixed_fallback")
        self.assertTrue(rows[0]["starvation_signal"])
        self.assertEqual(rows[0]["coverage"]["overall"]["c1"], 0.9)
        self.assertIn("r=2, weighted, class_aware", summary)
        self.assertIn(
            "| 90.0% | 62.5% | 60.0% | fixed_fallback | true |",
            summary,
        )


if __name__ == "__main__":
    unittest.main()
