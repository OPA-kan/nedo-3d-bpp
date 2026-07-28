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
                        "mean_predicted_feasible_remaining_ratio": 0.5,
                        "mean_final_center_of_mass_z": 0.4,
                        "mean_final_surface_total_variation": 0.1,
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
                        "mean_predicted_feasible_remaining_ratio": 0.6,
                        "mean_final_center_of_mass_z": 0.3,
                        "mean_final_surface_total_variation": 0.08,
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

    def test_step_metrics_and_policy_trace_are_merged_by_case(self) -> None:
        evaluation = {
            "000": {
                "status": "success",
                "evaluation": {
                    "fill_score": 10.0,
                    "num_placed_items": 0.1,
                    "step_metrics": [
                        {
                            "step": 0,
                            "placed_count": 1,
                            "placed_volume": 0.25,
                            "center_of_mass_z": 0.3,
                            "surface_total_variation": 0.04,
                            "surface_height_std": 0.05,
                            "flat_support_edge_ratio": 0.8,
                            "remaining_volume_ratio": 0.75,
                            "status": {
                                "is_included": True,
                                "is_valid": True,
                                "is_placed_safe": True,
                            },
                        }
                    ],
                },
                "place_states": {
                    "is_included": True,
                    "is_valid": True,
                    "is_placed_safe": True,
                },
                "time_results": {"optimization": 0.0, "policy": 1.0},
            }
        }
        policy_trace = {
            "000": [
                {
                    "feasible_remaining_items": 1,
                    "evaluated_remaining_items": 2,
                    "feasible_remaining_ratio": 0.5,
                    "immediate_score": 3.0,
                }
            ]
        }

        summary = summarize_evaluation(
            evaluation,
            self.config,
            policy_trace=policy_trace,
        )

        case = summary["cases"]["000"]
        self.assertEqual(case["final_placed_volume"], 0.25)
        self.assertEqual(case["final_center_of_mass_z"], 0.3)
        self.assertEqual(
            case["metric_history"][0][
                "predicted_feasible_remaining_ratio"
            ],
            0.5,
        )


if __name__ == "__main__":
    unittest.main()
