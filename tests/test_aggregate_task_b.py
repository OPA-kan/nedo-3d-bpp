from __future__ import annotations

import unittest

from scripts.aggregate_task_b import aggregate_rows, build_aggregate_markdown


class TaskBAggregateTests(unittest.TestCase):
    def test_aggregates_replicates_and_failure_counts(self) -> None:
        rows = [
            {
                "look_ahead": 10,
                "selection_mode": "weighted",
                "coverage_mode": "class_aware",
                "replicate": 1,
                "placed_count": 18,
                "fill_score": 20.0,
                "failure_mode": "fixed_fallback",
                "starvation_signal": True,
                "coverage": {
                    "overall": {"c1": 0.8, "c2": 0.9, "c3": 0.5},
                    "by_class": {},
                },
            },
            {
                "look_ahead": 10,
                "selection_mode": "weighted",
                "coverage_mode": "class_aware",
                "replicate": 2,
                "placed_count": 20,
                "fill_score": 24.0,
                "failure_mode": "release_failure",
                "starvation_signal": False,
                "coverage": {
                    "overall": {"c1": 1.0, "c2": 0.8, "c3": 0.6},
                    "by_class": {},
                },
            },
            {
                "look_ahead": 10,
                "selection_mode": "weighted",
                "coverage_mode": "class_aware",
                "replicate": 3,
                "placed_count": 16,
                "fill_score": 22.0,
                "failure_mode": "fixed_fallback",
                "starvation_signal": False,
                "coverage": {
                    "overall": {"c1": 0.9, "c2": 1.0, "c3": 0.4},
                    "by_class": {},
                },
            },
        ]

        aggregates = aggregate_rows(rows)
        markdown = build_aggregate_markdown(aggregates)

        result = aggregates[0]
        self.assertEqual(result["runs"], 3)
        self.assertEqual(result["placed"]["mean"], 18.0)
        self.assertEqual(result["placed"]["median"], 18.0)
        self.assertAlmostEqual(result["placed"]["stddev"], 2.0)
        self.assertEqual(result["placed"]["min"], 16)
        self.assertEqual(result["placed"]["max"], 20)
        self.assertEqual(
            result["failure_modes"],
            {"fixed_fallback": 2, "release_failure": 1},
        )
        self.assertEqual(result["starvation_signal_count"], 1)
        self.assertAlmostEqual(
            result["coverage"]["overall"]["c1"]["mean"],
            0.9,
        )
        self.assertIn("fixed_fallback=2", markdown)
