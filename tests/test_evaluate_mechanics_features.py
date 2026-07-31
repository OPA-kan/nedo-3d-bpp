from __future__ import annotations

import math
import unittest

from scripts.evaluate_mechanics_features import (
    convex_hull,
    load_agent_module,
    mechanics_features,
    within_snapshot_pair_accuracy,
)

import numpy as np


AGENT = load_agent_module()


def bare_container():
    return {
        "length": 2.0,
        "width": 1.4,
        "height": 1.6,
        "thickness": 0.04,
        "buffer": 0.0,
        "cut_x": 0.0,
        "cut_y": 0.0,
        "require_shelf": False,
        "center": [0.0, 0.0, 0.8],
        "packed_items": [],
    }


def packed_box(x, y, top, size=0.4, height=0.3):
    return {
        "index": 99,
        "length": size,
        "width": size,
        "height": height,
        "orientation": 0,
        "is_soft": False,
        "is_prioritized": False,
        "pos": [x, y, top - height / 2.0],
        "orn": [0.0, 0.0, 0.0, 1.0],
    }


class HullTests(unittest.TestCase):
    def test_rectangle_hull_is_ccw_with_four_vertices(self):
        points = [(0, 0), (1, 0), (1, 1), (0, 1), (0.5, 0.5)]
        hull = convex_hull(points)
        self.assertEqual(len(hull), 4)
        area2 = sum(
            hull[i][0] * hull[(i + 1) % 4][1]
            - hull[(i + 1) % 4][0] * hull[i][1]
            for i in range(4)
        )
        self.assertGreater(area2, 0)  # CCW

    def test_collinear_points_collapse(self):
        hull = convex_hull([(0, 0), (1, 0), (2, 0)])
        self.assertLessEqual(len(hull), 2)


class MechanicsFeatureTests(unittest.TestCase):
    def test_full_floor_support_gives_half_min_extent_margin(self):
        container = bare_container()
        dims = (0.4, 0.3, 0.2)
        floor_top = 0.04
        features = mechanics_features(
            AGENT, container, 0.0, 0.0, floor_top + 0.1 + 0.02, dims
        )
        self.assertAlmostEqual(features["d_min"], 0.15, places=6)
        self.assertAlmostEqual(
            features["theta_c_min"], math.atan2(0.15, 0.1), places=6
        )
        expected_barrier = math.sqrt(0.15**2 + 0.1**2) - 0.1
        self.assertAlmostEqual(features["B_min"], expected_barrier, places=6)
        self.assertAlmostEqual(features["drop_meters"], 0.02, places=6)
        self.assertFalse(features["degenerate_contact"])

    def test_offset_support_shrinks_margin_and_barrier(self):
        container = bare_container()
        # Support box under only the +x half of the footprint.
        container["packed_items"] = [packed_box(0.3, 0.0, top=0.34)]
        dims = (0.4, 0.3, 0.2)
        features = mechanics_features(
            AGENT, container, 0.1, 0.0, 0.6, dims
        )
        full = mechanics_features(
            AGENT, bare_container(), 0.1, 0.0, 0.6, dims
        )
        self.assertLess(features["d_min"], full["d_min"])
        self.assertLess(features["B_min"], full["B_min"])
        self.assertGreater(
            features["log1p_eta_max"], full["log1p_eta_max"]
        )

    def test_com_outside_support_gives_zero_barrier_and_capped_eta(self):
        container = bare_container()
        # Narrow pedestal fully to one side of the CoM.
        container["packed_items"] = [
            packed_box(0.28, 0.0, top=0.34, size=0.2)
        ]
        dims = (0.4, 0.3, 0.2)
        features = mechanics_features(
            AGENT, container, 0.0, 0.0, 0.6, dims
        )
        self.assertLessEqual(features["d_min"], 0.0)
        self.assertEqual(features["B_min"], 0.0)
        self.assertGreater(features["log1p_eta_max"], 10.0)

    def test_higher_drop_raises_eta_only(self):
        container = bare_container()
        dims = (0.4, 0.3, 0.2)
        low = mechanics_features(AGENT, container, 0.0, 0.0, 0.20, dims)
        high = mechanics_features(AGENT, container, 0.0, 0.0, 0.60, dims)
        self.assertAlmostEqual(low["d_min"], high["d_min"], places=9)
        self.assertAlmostEqual(low["B_min"], high["B_min"], places=9)
        self.assertLess(low["log1p_eta_max"], high["log1p_eta_max"])


class PairAccuracyTests(unittest.TestCase):
    def test_pairs_scored_within_snapshot_only(self):
        predictions = np.array([0.9, 0.1, 0.8, 0.2])
        labels = np.array([True, False, False, True])
        groups = ["s1", "s1", "s2", "s2"]
        report = within_snapshot_pair_accuracy(predictions, labels, groups)
        self.assertEqual(report["pairs"], 2)
        # s1 pair correct (0.9 > 0.1); s2 pair wrong (0.2 < 0.8).
        self.assertAlmostEqual(report["accuracy"], 0.5)

    def test_no_discordant_pairs_reports_none(self):
        report = within_snapshot_pair_accuracy(
            np.array([0.5, 0.6]), np.array([True, True]), ["s", "s"]
        )
        self.assertIsNone(report["accuracy"])


if __name__ == "__main__":
    unittest.main()
