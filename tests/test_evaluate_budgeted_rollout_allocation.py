import unittest

from scripts.evaluate_budgeted_rollout_allocation import (
    allocated_candidates,
    evaluate,
)


def vector(fill):
    return {
        "fill_gain": fill,
        "soft_violation_gain": 0.0,
        "priority_covered_gain": 0.0,
        "priority_misrouted_gain": 0.0,
        "surface_total_variation_delta": 0.0,
    }


class BudgetedRolloutAllocationTests(unittest.TestCase):
    def test_allocator_keeps_incumbent_and_highest_scoring_alternative(self):
        row = {
            "candidate_ids": ["a", "b", "c"],
            "candidate_scores": [0.1, 0.2, 0.7],
            "incumbent_index": 0,
        }
        self.assertEqual(allocated_candidates(row, budget=2), ["a", "c"])

    def test_physics_decides_within_oof_subset_and_scales_latency(self):
        checkpoint = {
            "contract": "bounded_physical_rollout_checkpoint_aggregate_v1",
            "continuation_caps": [2],
            "root_rows": [{
                "root_id": "root-1",
                "incumbent_candidate_id": "a",
                "terminal_selected_candidate_id": "c",
                "checkpoints": {"2": {
                    "search_seconds": 9.0,
                    "estimated_decision_seconds": 10.0,
                    "candidates": [
                        {"root_candidate_id": "a", "safe": True,
                         "checkpoint_vector": vector(1.0),
                         "physical_step_equivalents": 3},
                        {"root_candidate_id": "b", "safe": True,
                         "checkpoint_vector": vector(0.0),
                         "physical_step_equivalents": 3},
                        {"root_candidate_id": "c", "safe": True,
                         "checkpoint_vector": vector(2.0),
                         "physical_step_equivalents": 3},
                    ],
                }},
            }],
        }
        oof = {"candidate_allocator": {
            "contract": "rollout_candidate_allocator_group_oof_v1",
            "oof_rows": [{
                "root_id": "root-1",
                "candidate_ids": ["a", "b", "c"],
                "candidate_scores": [0.1, 0.2, 0.7],
                "incumbent_index": 0,
            }],
        }}
        report = evaluate(checkpoint, oof, budgets=[2])
        point = report["points"][0]
        self.assertEqual(point["terminal_action_recall"], 1.0)
        self.assertEqual(point["intervention_action_recall"], 1.0)
        self.assertAlmostEqual(point["mean_physical_work_fraction"], 2 / 3)
        self.assertAlmostEqual(point["estimated_mean_seconds"], 7.0)
        adaptive = report["adaptive_points"][0]
        self.assertEqual(adaptive["terminal_action_recall"], 1.0)
        self.assertEqual(adaptive["estimated_within_budget_rate"], 1.0)
        self.assertEqual(adaptive["depth_counts"], {"3": 1})


if __name__ == "__main__":
    unittest.main()
