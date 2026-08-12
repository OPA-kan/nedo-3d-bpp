from __future__ import annotations

import unittest

from scripts.build_counterfactual_teacher_pairs import build_teacher_corpus


class CounterfactualTeacherPairTests(unittest.TestCase):
    def test_keeps_axes_separate_and_holds_out_late_roots(self):
        pair = {
            "source_node_id": "root",
            "source_depth": 0,
            "score_gap": 0.2,
            "equal_immediate_score": False,
            "lower_stable_item_index": 1,
            "higher_stable_item_index": 2,
            "comparisons": {
                "fill_score_proxy": {
                    "lower_range": [10.0, 12.0],
                    "higher_range": [10.0, 11.0],
                },
                "com_z": {
                    "lower_range": [0.6, 0.7],
                    "higher_range": [0.5, 0.7],
                },
            },
        }
        signal = {"run_id": "1", "commits": ["abc"], "graphs": [{
            "graph_id": "g", "case_id": "case", "root_step": 15,
            "scenario_axes": {}, "sibling_pairs": [pair],
        }]}

        manifest, buckets = build_teacher_corpus(signal)

        self.assertEqual(manifest["late_holdout_rows"], 1)
        self.assertEqual(buckets["discovery"], [])
        labels = buckets["late_holdout"][0]["labels"]
        self.assertEqual(
            labels["fill_score_proxy"]["relation"],
            "lower_immediate_score_better",
        )
        self.assertEqual(
            labels["com_z"]["relation"],
            "higher_immediate_score_better",
        )

    def test_exact_score_pair_is_an_uninformative_control(self):
        pair = {
            "source_node_id": "n", "source_depth": 1, "score_gap": 0.0,
            "equal_immediate_score": True, "lower_stable_item_index": 1,
            "higher_stable_item_index": 2,
            "comparisons": {"placed_count": {
                "lower_range": [3, 3], "higher_range": [3, 3],
            }},
        }
        signal = {"graphs": [{
            "graph_id": "g", "case_id": "c", "root_step": 6,
            "scenario_axes": {}, "sibling_pairs": [pair],
        }]}

        manifest, buckets = build_teacher_corpus(signal)

        self.assertEqual(manifest["informative_pair_rows"], 0)
        self.assertFalse(manifest["model_training_ready"])
        self.assertEqual(len(buckets["controls"]), 1)


if __name__ == "__main__":
    unittest.main()
