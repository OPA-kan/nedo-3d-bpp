from __future__ import annotations

import unittest

from scripts.measure_uncapped_feasible_items import summarize_results


class UncappedFeasibleItemTests(unittest.TestCase):
    def test_aggregates_each_feasible_item_once_across_candidate_kinds(self):
        items = [
            {"index": 10, "length": 2, "width": 3, "height": 4,
             "is_prioritized": True, "is_soft": False},
            {"index": 11, "length": 1, "width": 2, "height": 3,
             "is_prioritized": False, "is_soft": True},
        ]
        results = [
            {"stable_item_index": 10, "is_placed_safe": False},
            {"stable_item_index": 10, "is_placed_safe": True},
            {"stable_item_index": 11, "is_placed_safe": True},
        ]
        report = summarize_results(items, results)
        self.assertEqual(report["candidate_action_count"], 3)
        self.assertEqual(report["feasible_visible_item_count"], 2)
        self.assertEqual(report["feasible_visible_item_volume"], 30.0)
        self.assertEqual(report["feasible_priority_count"], 1)
        self.assertEqual(report["feasible_soft_count"], 1)


if __name__ == "__main__":
    unittest.main()
