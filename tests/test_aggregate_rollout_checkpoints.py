import unittest

from scripts.aggregate_rollout_checkpoints import aggregate


def cell(name, root_id, selected):
    root = {
        "root_id": root_id,
        "incumbent_candidate_id": "inc",
        "terminal_selected_candidate_id": selected,
        "checkpoints": {
            "0": {
                "selected_candidate_id": "inc",
                "estimated_decision_seconds": 3.0,
            },
            "2": {
                "selected_candidate_id": selected,
                "estimated_decision_seconds": 8.0,
            },
        },
    }
    return {
        "contract": "bounded_physical_rollout_checkpoint_oracle_v1",
        "cell": name,
        "continuation_caps": [0, 2],
        "roots": [root],
        "summary": {},
    }


class AggregateRolloutCheckpointsTests(unittest.TestCase):
    def test_aggregates_cells_without_losing_intervention_recall(self):
        report = aggregate(
            [cell("a", "r1", "alt"), cell("b", "r2", "inc")],
            expected_cells=2,
        )
        self.assertEqual(report["roots"], 2)
        self.assertEqual(report["interventions"], 1)
        self.assertEqual(
            report["summary"]["2"]["intervention_action_recall"], 1.0
        )

    def test_rejects_missing_cell(self):
        with self.assertRaisesRegex(ValueError, "expected 2 cells"):
            aggregate([cell("a", "r1", "alt")], expected_cells=2)


if __name__ == "__main__":
    unittest.main()
