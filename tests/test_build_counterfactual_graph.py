from __future__ import annotations

import unittest

from scripts.build_counterfactual_graph import (
    cumulative_metrics,
    transition_outcomes,
)


class PhysicalOutcomeTests(unittest.TestCase):
    def test_records_all_score_proxies_without_collapsing_them(self):
        class Container:
            packed_items = [object(), object()]

        class Evaluator:
            def settled_snapshot(self, _containers):
                return {
                    "placed_count": 2,
                    "placed_volume": 0.8,
                    "fill_percent_proxy": 20.0,
                    "center_of_mass_z": 0.42,
                    "com_z": 0.42,
                    "surface_total_variation": 0.07,
                    "priority_items": 1,
                    "priority_misrouted": 0,
                    "soft_items": 1,
                    "soft_covered_by_other": 1,
                }

        class ContainerManager:
            containers = [Container()]

        class Env:
            evaluator = Evaluator()
            container_manager = ContainerManager()
            step_metrics = [
                {
                    "settle_angle_deg": 12.0,
                    "settle_displacement_norm": 0.03,
                }
            ]

        metrics = cumulative_metrics(Env())
        self.assertEqual(metrics["placed_count"], 2)
        self.assertEqual(metrics["fill_score_proxy"], 20.0)
        self.assertEqual(metrics["com_z"], 0.42)
        self.assertEqual(metrics["priority_misrouted"], 0)
        self.assertEqual(metrics["soft_covered_by_other"], 1)

        immediate, cumulative = transition_outcomes(
            Env(),
            {
                "status": {
                    "is_included": True,
                    "is_valid": True,
                    "is_placed_safe": True,
                }
            },
            {
                "placed_count": 1,
                "placed_volume": 0.5,
                "fill_score_proxy": 12.5,
                "com_z": 0.35,
            },
        )
        self.assertEqual(immediate["placed_count_delta"], 1.0)
        self.assertAlmostEqual(immediate["placed_volume_delta"], 0.3)
        self.assertAlmostEqual(immediate["com_z_delta"], 0.07)
        self.assertEqual(immediate["settle_angle_deg"], 12.0)
        self.assertTrue(immediate["is_placed_safe"])
        self.assertEqual(cumulative["soft_covered_by_other"], 1)


if __name__ == "__main__":
    unittest.main()
