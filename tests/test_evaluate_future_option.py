from __future__ import annotations

import unittest

from scripts.evaluate_future_option import action_hash, summarize


class EvaluateFutureOptionTests(unittest.TestCase):
    def test_action_hash_ignores_numpy_style_float_noise(self):
        base = {
            "item_idx": 1,
            "container_idx": 0,
            "orientation": 2,
            "place_pos": [0.1, 0.2, 0.3],
        }
        noisy = {**base, "place_pos": [0.10000001, 0.2, 0.3]}
        self.assertEqual(action_hash(base), action_hash(noisy))

    def test_summary_keeps_arm_action_instability_visible(self):
        rows = [
            {
                "arm": "off",
                "elapsed_seconds": 1.0,
                "action_hash": "a",
                "selected_item_index": 5,
            },
            {
                "arm": "off",
                "elapsed_seconds": 2.0,
                "action_hash": "b",
                "selected_item_index": 6,
            },
            {
                "arm": "future-option",
                "elapsed_seconds": 3.0,
                "action_hash": "c",
                "selected_item_index": 17,
            },
        ]

        result = summarize(rows)

        self.assertEqual(result["off"]["selected_items"], [5, 6])
        self.assertEqual(result["off"]["action_hashes"], ["a", "b"])
        self.assertEqual(result["future-option"]["elapsed_mean"], 3.0)


if __name__ == "__main__":
    unittest.main()
