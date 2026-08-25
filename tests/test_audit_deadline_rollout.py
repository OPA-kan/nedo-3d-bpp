import unittest

from scripts.audit_deadline_rollout import (
    choose_from_checkpoint,
    ranker_order_candidates,
)
from scripts.deadline_rollout_summary import summarize


def candidate(candidate_id, fill):
    return {
        "root_candidate_id": candidate_id,
        "safe": True,
        "checkpoint_vector": {
            "fill_gain": fill,
            "soft_violation_gain": 0.0,
            "priority_covered_gain": 0.0,
            "priority_misrouted_gain": 0.0,
            "surface_total_variation_delta": 0.0,
        },
    }


class AuditDeadlineRolloutTests(unittest.TestCase):
    def test_physics_switches_only_when_incumbent_is_dominated(self):
        selected, frontier = choose_from_checkpoint(
            ["a", "b"], incumbent="a",
            candidates=[candidate("a", 1.0), candidate("b", 2.0)],
        )
        self.assertEqual(selected, "b")
        self.assertEqual(frontier, ["b"])

    def test_ranker_next_ignores_scores_and_keeps_rank_order(self):
        oof_row = {
            "candidate_ids": ["a", "b", "c"],
            "candidate_scores": [0.1, 0.2, 0.9],
            "incumbent_index": 0,
        }
        self.assertEqual(
            ranker_order_candidates(oof_row, budget=2), ["a", "b"]
        )
        self.assertEqual(
            ranker_order_candidates(oof_row, budget=1), ["a"]
        )
        self.assertEqual(
            ranker_order_candidates(oof_row, budget=3), ["a", "b", "c"]
        )

    def test_summary_reports_actual_budget_compliance(self):
        rows = [
            {
                "incumbent_candidate_id": "a",
                "terminal_selected_candidate_id": "b",
                "terminal_selected_available": True,
                "matches_terminal_action": True,
                "decision_seconds": 9.0,
                "search": {"deadline_met": True, "common_total_depth": 3},
            },
            {
                "incumbent_candidate_id": "a",
                "terminal_selected_candidate_id": "a",
                "terminal_selected_available": True,
                "matches_terminal_action": True,
                "decision_seconds": 11.0,
                "search": {"deadline_met": False, "common_total_depth": 1},
            },
        ]
        result = summarize(rows)
        self.assertEqual(result["terminal_action_recall"], 1.0)
        self.assertEqual(result["intervention_action_recall"], 1.0)
        self.assertEqual(result["within_10s_rate"], 0.5)
        self.assertEqual(result["depth_counts"], {"1": 1, "3": 1})


if __name__ == "__main__":
    unittest.main()
