import unittest

from scripts.evaluate_provider_zero_rescue import evaluate, wilson_interval


def _state(board, occurrence, rescued):
    return {
        "board_fingerprint": board,
        "case_id": "m-single-empty-shelf",
        "occurrence_count": occurrence,
        "baseline_provider_confirmed_empty": True,
        "strategies": {
            "stride4": {
                "rescued": rescued,
                "proposal_count": 2,
                "generation_seconds": 1.0,
                "physical_filter_seconds": 2.0,
                "safe_candidates": ([{
                    "selection": {
                        "rank": 0,
                        "priority_routing_violation": 1,
                        "soft_violations_direct": 0,
                        "priority_violations_direct": 0,
                        "soft_violations_stack": 1,
                        "priority_violations_stack": 0,
                    }
                }] if rescued else []),
            }
        },
    }


class ProviderZeroRescueEvaluationTests(unittest.TestCase):
    def test_reports_board_and_node_weighted_recall_separately(self):
        payload = {"complete": True, "states": [
            _state("b1", 9, True),
            _state("b2", 1, False),
        ]}

        result = evaluate([payload])
        row = result["strategies"]["stride4"]

        self.assertEqual(row["board_recall"], 0.5)
        self.assertEqual(row["node_weighted_recall"], 0.9)
        self.assertEqual(row["safe_candidate_count"], 1)
        self.assertEqual(
            row["attribute_heads"]["soft_violations_stack_events"], 1
        )
        self.assertEqual(
            row["attribute_heads"]["priority_routing_violation_events"], 1
        )
        self.assertIn("stride4", result["promising_strategies_at_20pct_point_recall"])
        self.assertEqual(row["rank0_safe_boards"], 1)
        self.assertEqual(row["lazy_physical_checks_to_first_safe"], 3)
        self.assertEqual(row["clean_safe_candidate_count"], 0)

    def test_rejects_duplicate_boards_across_shards(self):
        first = {"complete": True, "states": [_state("b1", 1, True)]}
        second = {"complete": True, "states": [_state("b1", 1, False)]}
        with self.assertRaisesRegex(ValueError, "duplicate board"):
            evaluate([first, second])

    def test_wilson_interval_contains_observed_fraction(self):
        low, high = wilson_interval(5, 10)
        self.assertLess(low, 0.5)
        self.assertGreater(high, 0.5)


if __name__ == "__main__":
    unittest.main()
