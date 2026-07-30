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
                                "step": 15,
                                "placed_count": 15,
                                "settle_angle_deg": 45.0,
                                "settle_displacement_norm": 0.2,
                                "settle_aabb_dimensions": [0.3, 0.2, 0.4],
                                "status": {"is_placed_safe": True},
                            },
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
                "candidate_kind": "release_candidate",
                "candidate_diagnostics": {
                    "selected_release_risk": {
                        "mode": "enforce",
                        "passed": True,
                        "reasons": [],
                    }
                },
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
                "action_source": "unsafe_protocol_fallback",
                "candidate_kind": "unsafe_protocol_fallback",
                "candidate_diagnostics": {
                    "release_static_count": 4,
                    "release_gate_pass_count": 0,
                    "release_gate_reject_count": 4,
                    "release_all_rejected": True,
                    "release_risk_gate": {
                        "mode": "enforce",
                        "evaluated": 10,
                        "would_reject": 4,
                        "enforced_rejections": 4,
                    }
                },
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
            risk_gate_mode="enforce",
            replicate=2,
            trace_events=trace_events,
        )
        summary = build_task_b_summary(
            payload,
            look_ahead=10,
            selection_mode="weighted",
            coverage_mode="class_aware",
            risk_gate_mode="enforce",
            replicate=2,
            trace_events=trace_events,
        )

        self.assertEqual(
            rows[0]["failure_mode"],
            "unsafe_protocol_fallback",
        )
        self.assertTrue(rows[0]["starvation_signal"])
        self.assertEqual(rows[0]["coverage"]["overall"]["c1"], 0.9)
        self.assertEqual(rows[0]["release"]["gate_evaluated"], 10)
        self.assertEqual(rows[0]["release"]["gate_would_reject"], 4)
        self.assertEqual(rows[0]["release"]["release_static_count"], 4)
        self.assertEqual(rows[0]["release"]["release_gate_pass_count"], 0)
        self.assertEqual(rows[0]["release"]["release_all_rejected_count"], 1)
        self.assertEqual(rows[0]["release"]["protocol_fallback_count"], 1)
        self.assertEqual(rows[0]["release"]["selected_release_count"], 1)
        self.assertEqual(rows[0]["release"]["rotation_over_30_count"], 1)
        self.assertEqual(rows[0]["release"]["large_displacement_count"], 1)
        self.assertEqual(rows[0]["release"]["selected_gate_pass_count"], 1)
        self.assertEqual(
            rows[0]["release"]["gate_passing_release_failure_rate"],
            1.0,
        )
        self.assertIn(
            "r=2, weighted, class_aware, risk=enforce",
            summary,
        )
        self.assertIn(
            "| 90.0% | 62.5% | 60.0% | "
            "unsafe_protocol_fallback | true |",
            summary,
        )
        self.assertIn(
            "| task-b-k10 | enforce | 4 | 0 | 0.0% | 4 | 1 | "
            "100.0% | 1 | 10 | 4 |",
            summary,
        )

    def test_counts_shadow_rejection_that_physically_succeeds(self) -> None:
        payload = {
            "evaluation": {
                "case": {
                    "status": "success",
                    "evaluation": {
                        "fill_score": 1.0,
                        "num_placed_items": 1.0,
                        "step_metrics": [
                            {
                                "step": 0,
                                "placed_count": 1,
                                "settle_angle_deg": 0.1,
                                "settle_displacement_norm": 0.01,
                                "settle_aabb_dimensions": [0.2, 0.3, 0.4],
                                "status": {"is_placed_safe": True},
                            }
                        ],
                    },
                    "time_results": {"policy": 1.0},
                }
            }
        }
        trace_events = [
            {
                "event": "decision",
                "step": 0,
                "candidate_kind": "release_candidate",
                "action_source": "placement_core",
                "candidate_diagnostics": {
                    "selected_release_risk": {
                        "mode": "shadow",
                        "passed": False,
                        "reasons": ["support"],
                    }
                },
            }
        ]

        rows = task_b_result_rows(
            payload,
            look_ahead=20,
            selection_mode="weighted",
            risk_gate_mode="shadow",
            trace_events=trace_events,
        )

        self.assertEqual(
            rows[0]["release"]["shadow_rejected_but_safe_count"],
            1,
        )

    def test_trace_is_partitioned_by_init_for_each_case(self) -> None:
        payload = {
            "evaluation": {
                case_id: {
                    "status": "success",
                    "evaluation": {
                        "fill_score": 1.0,
                        "num_placed_items": 1.0,
                        "step_metrics": [
                            {
                                "step": 0,
                                "placed_count": 1,
                                "status": {"is_placed_safe": True},
                            }
                        ],
                    },
                    "time_results": {"policy": 1.0},
                }
                for case_id in ("case-a", "case-b")
            }
        }
        trace_events = [
            {"event": "init"},
            {
                "event": "decision",
                "step": 0,
                "action_source": "placement_core",
                "candidate_kind": "settled_candidate",
                "action_command": {
                    "item_idx": 0,
                    "container_idx": 0,
                    "place_pos": [0.0, 0.0, 0.1],
                    "orientation": 0,
                },
            },
            {"event": "init"},
            {
                "event": "decision",
                "step": 0,
                "action_source": "unsafe_protocol_fallback",
                "candidate_kind": "unsafe_protocol_fallback",
                "action_command": {
                    "item_idx": 0,
                    "container_idx": 0,
                    "place_pos": [0.0, 0.0, 0.25],
                    "orientation": 0,
                },
            },
        ]

        rows = task_b_result_rows(
            payload,
            look_ahead=20,
            selection_mode="weighted",
            trace_events=trace_events,
        )

        self.assertEqual(rows[0]["release"]["protocol_fallback_count"], 0)
        self.assertEqual(rows[1]["release"]["protocol_fallback_count"], 1)
        self.assertNotEqual(
            rows[0]["release"]["action_sequence_sha256"],
            rows[1]["release"]["action_sequence_sha256"],
        )


if __name__ == "__main__":
    unittest.main()
