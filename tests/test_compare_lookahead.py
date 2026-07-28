from __future__ import annotations

import unittest

from scripts.compare_lookahead import (
    comparison_markdown,
    summarize_evaluation,
)


class LookaheadComparisonTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = {
            "000": {"item_stream": {"item_list": [{} for _ in range(10)]}},
            "001": {"item_stream": {"item_list": [{} for _ in range(8)]}},
        }

    def test_summary_extracts_score_count_flags_and_runtime(self) -> None:
        evaluation = {
            "000": {
                "status": "success",
                "evaluation": {
                    "fill_score": 12.5,
                    "num_placed_items": 0.7,
                },
                "place_states": {
                    "is_included": True,
                    "is_valid": False,
                    "is_placed_safe": False,
                },
                "time_results": {
                    "optimization": 149.0,
                    "policy": 4.2,
                },
            }
        }

        summary = summarize_evaluation(evaluation, self.config)

        self.assertEqual(summary["cases"]["000"]["placed_count"], 7)
        self.assertEqual(summary["cases"]["000"]["total_items"], 10)
        self.assertEqual(summary["cases"]["000"]["fill_score"], 12.5)
        self.assertFalse(summary["cases"]["000"]["is_valid"])
        self.assertFalse(summary["all_physics_valid"])
        self.assertEqual(summary["total_placed_count"], 7)
        self.assertEqual(summary["max_policy_seconds"], 4.2)

    def test_comparison_history_keeps_modes_and_interpretation_together(self) -> None:
        payload = {
            "timestamp": "2026-07-28T12:00:00+09:00",
            "git_sha": "abc123",
            "config": "sample_config.json",
            "modes": {
                "weighted": {
                    "process_returncode": 0,
                    "summary": {
                        "cases": {
                            "000": {
                                "fill_score": 10.0,
                                "placed_count": 5,
                                "total_items": 10,
                                "is_included": True,
                                "is_valid": False,
                                "is_placed_safe": False,
                                "optimization_seconds": 1.0,
                                "policy_seconds": 2.0,
                            }
                        },
                        "all_physics_valid": False,
                        "total_placed_count": 5,
                        "mean_fill_score": 10.0,
                        "max_policy_seconds": 2.0,
                    },
                },
                "depth2": {
                    "process_returncode": 0,
                    "summary": {
                        "cases": {},
                        "all_physics_valid": True,
                        "total_placed_count": 6,
                        "mean_fill_score": 11.0,
                        "max_policy_seconds": 2.5,
                    },
                },
            },
        }

        markdown = comparison_markdown(payload)

        self.assertIn("weighted", markdown)
        self.assertIn("depth2", markdown)
        self.assertIn("physical validity failed", markdown)
        self.assertIn("abc123", markdown)
        self.assertIn("not a SIGNATE leaderboard score", markdown)


if __name__ == "__main__":
    unittest.main()
