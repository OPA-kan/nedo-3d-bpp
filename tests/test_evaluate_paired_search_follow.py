import unittest

from scripts.evaluate_paired_search_follow import aggregate_manifests


class PairedSearchFollowEvaluationTests(unittest.TestCase):
    def test_aggregate_separates_gate_quality_from_fresh_outcome(self):
        manifests = [
            {"gate": {"status": "hold", "reasons": ["view_disagreement"]}},
            {
                "gate": {"status": "follow", "reasons": []},
                "execution": {"valid": True},
                "comparison": {
                    "fill_delta": 2.0,
                    "placed_delta": 0.0,
                    "step_delta": 1,
                    "pareto_relation": "search_dominates",
                    "new_downstream_state_count": 2,
                },
            },
            {
                "gate": {"status": "follow", "reasons": []},
                "execution": {"valid": True},
                "comparison": {
                    "fill_delta": -1.0,
                    "placed_delta": -1.0,
                    "step_delta": -1,
                    "pareto_relation": "baseline_dominates",
                    "new_downstream_state_count": 1,
                },
            },
        ]

        result = aggregate_manifests(manifests)

        self.assertEqual(result["gate"]["followed"], 2)
        self.assertEqual(result["gate"]["held"], 1)
        self.assertEqual(result["fresh_outcome"]["fill_wins"], 1)
        self.assertEqual(result["fresh_outcome"]["fill_losses"], 1)
        self.assertEqual(result["fresh_outcome"]["search_pareto_wins"], 1)
        self.assertEqual(result["distribution"]["new_downstream_states"], 3)


if __name__ == "__main__":
    unittest.main()
