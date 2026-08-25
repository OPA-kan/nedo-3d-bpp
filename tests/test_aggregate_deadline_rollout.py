import unittest

from scripts.aggregate_deadline_rollout import aggregate


def cell(name, root_id):
    return {
        "contract": "deadline_rollout_hard_state_audit_v1",
        "cell": name,
        "candidate_budget": 2,
        "decision_budget_seconds": 10.0,
        "live_action_reserve_seconds": 0.25,
        "max_continuation_steps": 2,
        "safety_factor": 1.35,
        "summary": {},
        "roots": [{
            "root_id": root_id,
            "incumbent_candidate_id": "a",
            "terminal_selected_candidate_id": "a",
            "terminal_selected_available": True,
            "matches_terminal_action": True,
            "decision_seconds": 5.0,
            "search": {"deadline_met": True, "common_total_depth": 3},
        }],
    }


class AggregateDeadlineRolloutTests(unittest.TestCase):
    def test_aggregates_actual_deadline_metrics(self):
        report = aggregate([cell("x", "r1"), cell("y", "r2")], expected_cells=2)
        self.assertEqual(report["summary"]["roots"], 2)
        self.assertEqual(report["summary"]["within_10s_rate"], 1.0)
        self.assertEqual(report["max_total_depth"], 3)

    def test_rejects_setting_drift(self):
        rows = [cell("x", "r1"), cell("y", "r2")]
        rows[1]["candidate_budget"] = 3
        with self.assertRaisesRegex(ValueError, "settings differ"):
            aggregate(rows, expected_cells=2)


if __name__ == "__main__":
    unittest.main()
