from __future__ import annotations

import importlib.util
import pathlib
import sys
import unittest

import numpy as np


MODULE_PATH = (
    pathlib.Path(__file__).parents[1]
    / "simulator"
    / "src"
    / "ground_handling"
    / "diagnostics.py"
)
SPEC = importlib.util.spec_from_file_location("diagnostics", MODULE_PATH)
diagnostics = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = diagnostics
SPEC.loader.exec_module(diagnostics)


class SettledMetricTests(unittest.TestCase):
    def test_volume_center_of_mass_and_residual_capacity_are_direct(self):
        containers = [
            {
                "length": 1.0,
                "width": 1.0,
                "height": 1.0,
                "thickness": 0.0,
                "cut_x": 0.0,
                "volume": 1.0,
                "packed_items": [
                    {
                        "index": 0,
                        "mass": 1.0,
                        "volume": 0.1,
                        "pos": [0.0, 0.0, 0.2],
                        "aabb_min": [-0.1, -0.1, 0.1],
                        "aabb_max": [0.1, 0.1, 0.3],
                    },
                    {
                        "index": 1,
                        "mass": 3.0,
                        "volume": 0.2,
                        "pos": [0.2, 0.0, 0.6],
                        "aabb_min": [0.1, -0.1, 0.5],
                        "aabb_max": [0.3, 0.1, 0.7],
                    },
                ],
            }
        ]

        result = diagnostics.calculate_settled_metrics(
            containers,
            grid_size=0.1,
        )

        self.assertEqual(result["placed_count"], 2)
        self.assertAlmostEqual(result["placed_mass"], 4.0)
        self.assertAlmostEqual(result["placed_volume"], 0.3)
        self.assertAlmostEqual(result["fill_percent_proxy"], 30.0)
        self.assertAlmostEqual(result["center_of_mass_z"], 0.5)
        self.assertAlmostEqual(result["remaining_volume_ratio"], 0.7)

    def test_surface_metrics_are_explicit_proxies(self):
        containers = [
            {
                "length": 1.0,
                "width": 1.0,
                "height": 1.0,
                "thickness": 0.0,
                "cut_x": 0.0,
                "volume": 1.0,
                "packed_items": [
                    {
                        "mass": 1.0,
                        "volume": 0.1,
                        "pos": [0.0, 0.0, 0.2],
                        "aabb_min": [-0.5, -0.5, 0.0],
                        "aabb_max": [0.0, 0.5, 0.4],
                    }
                ],
            }
        ]

        result = diagnostics.calculate_settled_metrics(
            containers,
            grid_size=0.1,
        )

        self.assertGreater(result["surface_height_std"], 0.0)
        self.assertGreater(result["surface_total_variation"], 0.0)
        self.assertGreaterEqual(result["flat_support_edge_ratio"], 0.0)
        self.assertLessEqual(result["flat_support_edge_ratio"], 1.0)

    def test_depth_profile_distinguishes_door_side_from_back_side(self):
        base = {
            "length": 1.0,
            "width": 1.0,
            "height": 1.0,
            "thickness": 0.0,
            "cut_x": 0.0,
            "volume": 1.0,
        }
        front = {
            **base,
            "packed_items": [
                {
                    "mass": 1.0,
                    "volume": 0.04,
                    "pos": [0.0, -0.35, 0.1],
                    "aabb_min": [-0.1, -0.45, 0.0],
                    "aabb_max": [0.1, -0.25, 0.2],
                }
            ],
        }
        back = {
            **base,
            "packed_items": [
                {
                    "mass": 1.0,
                    "volume": 0.04,
                    "pos": [0.0, 0.35, 0.1],
                    "aabb_min": [-0.1, 0.25, 0.0],
                    "aabb_max": [0.1, 0.45, 0.2],
                }
            ],
        }

        front_result = diagnostics.calculate_settled_metrics(
            [front],
            depth_bins=10,
        )
        back_result = diagnostics.calculate_settled_metrics(
            [back],
            depth_bins=10,
        )

        self.assertLess(front_result["occupied_depth_center_normalized"], 0.0)
        self.assertGreater(back_result["occupied_depth_center_normalized"], 0.0)
        self.assertGreater(
            front_result["front_depth_occupancy_mean"],
            front_result["back_depth_occupancy_mean"],
        )
        self.assertGreater(
            back_result["back_depth_occupancy_mean"],
            back_result["front_depth_occupancy_mean"],
        )
        self.assertEqual(len(front_result["depth_occupancy_profile"]), 10)

    def test_settle_motion_records_position_and_orientation_change(self):
        half_angle = np.deg2rad(15.0)

        result = diagnostics.settle_motion_metrics(
            target_position=[0.0, 0.0, 0.5],
            target_quaternion=[0.0, 0.0, 0.0, 1.0],
            final_position=[0.03, 0.04, 0.4],
            final_quaternion=[
                0.0,
                0.0,
                np.sin(half_angle),
                np.cos(half_angle),
            ],
            final_aabb=([-0.1, -0.1, 0.2], [0.1, 0.1, 0.6]),
        )

        self.assertAlmostEqual(
            result["settle_displacement_norm"],
            np.sqrt(0.03**2 + 0.04**2 + 0.1**2),
        )
        np.testing.assert_allclose(
            result["settle_displacement_xyz"],
            [0.03, 0.04, -0.1],
        )
        self.assertAlmostEqual(result["settle_angle_deg"], 30.0)
        self.assertEqual(result["settle_final_position"], [0.03, 0.04, 0.4])
        np.testing.assert_allclose(
            result["settle_aabb_dimensions"],
            [0.2, 0.2, 0.4],
        )


if __name__ == "__main__":
    unittest.main()
