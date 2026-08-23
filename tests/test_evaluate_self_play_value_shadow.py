import unittest

from scripts.evaluate_self_play_value_shadow import (
    compare_shadow_rows,
    summarize_leaf_calls,
    trajectory_group_for_root,
)


def signature(q, visit=None):
    return {"q_top": q, "visit_top": visit or q, "q_relations": {}}


class SelfPlayValueShadowTests(unittest.TestCase):
    def test_maps_root_to_the_same_whole_trajectory_group_as_training(self):
        self.assertEqual(
            trajectory_group_for_root({
                "source_manifest": "pair-a/mcts/manifest.json",
                "trajectory_id": "trajectory-7",
            }),
            "pair-a:trajectory-7",
        )

    def test_accepts_only_paired_deep_reference_improvement(self):
        rows = [
            {
                "reference_signature": signature("b"),
                "zero_signature": signature("a"),
                "value_signature": signature("b"),
                "leaf_value_summary": {"calls": 3, "normalized_clipped_calls": 0},
            },
            {
                "reference_signature": signature("a"),
                "zero_signature": signature("a"),
                "value_signature": signature("a"),
                "leaf_value_summary": {"calls": 2, "normalized_clipped_calls": 1},
            },
        ]

        result = compare_shadow_rows(rows)

        self.assertTrue(result["accepted"])
        self.assertEqual(result["zero_q_top_matches_reference"], 1)
        self.assertEqual(result["value_q_top_matches_reference"], 2)
        self.assertEqual(result["q_top_improved_roots"], 1)
        self.assertEqual(result["q_top_regressed_roots"], 0)
        self.assertEqual(result["leaf_value_calls"], 5)
        self.assertFalse(result["progressive_widening"])

    def test_rejects_equal_aggregate_with_paired_regression(self):
        rows = [
            {
                "reference_signature": signature("b"),
                "zero_signature": signature("a"),
                "value_signature": signature("b"),
                "leaf_value_summary": {"calls": 1, "normalized_clipped_calls": 0},
            },
            {
                "reference_signature": signature("a"),
                "zero_signature": signature("a"),
                "value_signature": signature("b"),
                "leaf_value_summary": {"calls": 1, "normalized_clipped_calls": 0},
            },
        ]

        result = compare_shadow_rows(rows)

        self.assertFalse(result["accepted"])
        self.assertEqual(result["q_top_improved_roots"], 1)
        self.assertEqual(result["q_top_regressed_roots"], 1)

    def test_uncertainty_is_reported_per_head_without_scalarization(self):
        summary = summarize_leaf_calls([{
            "normalized_player0_value": -0.5,
            "heads": {
                "return_to_go": {"mean": 4.0, "variance": 2.0},
                "fill_return": {"mean": 1.0, "variance": 8.0},
            },
        }])

        self.assertEqual(summary["heads"]["return_to_go"]["mean_prediction"], 4.0)
        self.assertEqual(summary["heads"]["fill_return"]["mean_epistemic_variance"], 8.0)
        self.assertNotIn("weighted_score", summary)


if __name__ == "__main__":
    unittest.main()
