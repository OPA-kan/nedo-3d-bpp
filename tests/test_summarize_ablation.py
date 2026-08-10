import unittest

from scripts.summarize_ablation import metrics


class SummarizeAblationTests(unittest.TestCase):
    def test_metrics_retains_full_proxy_vector_without_combining_it(self):
        case = {
            "placed_count": 18,
            "placed_fraction": 0.45,
            "fill_score": 22.0,
            "final_com_z": 0.64,
            "policy_seconds": 6.4,
            "is_included": True,
            "is_valid": True,
            "is_placed_safe": False,
            "attribute_placement": {
                "priority_clean_ratio": 0.75,
                "soft_clean_ratio": 1.0,
            },
            "shake_response": {
                "shake_items": 18,
                "shake_items_shifted": 3,
                "shake_items_toppled": 1,
                "shake_max_shift": 0.12,
                "shake_peak_kinetic_energy": 4.5,
            },
            "score_components": {
                "cog_score": 9.5,
                "stability_score": 12.0,
                "placement_score": 2.0,
                "soft_item_score": 4.0,
            },
        }

        result = metrics(case)

        self.assertAlmostEqual(result["shake_shifted_fraction"], 1.0 / 6.0)
        self.assertEqual(result["shake_peak_kinetic_energy"], 4.5)
        self.assertEqual(result["priority_clean_ratio"], 0.75)
        self.assertEqual(result["soft_clean_ratio"], 1.0)
        self.assertEqual(result["cog_score"], 9.5)
        self.assertEqual(result["terminal_included"], 1.0)
        self.assertEqual(result["terminal_valid"], 1.0)
        self.assertEqual(result["terminal_placed_safe"], 0.0)
        self.assertNotIn("weighted_total", result)


if __name__ == "__main__":
    unittest.main()
