from __future__ import annotations

import math
import unittest

import numpy as np

from scripts.evaluate_slide_equivariant import (
    frame_row,
    ray_hull_margin,
    ridge_loso,
    support_centroid,
)
from scripts.evaluate_mechanics_features import load_agent_module


AGENT = load_agent_module()

SQUARE = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]


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


def release_row(x, y, z, dims, disp_xy):
    return {
        "center": [x, y, z],
        "size": list(dims),
        "snapshot_id": "s1",
        "case_id": "b000-k20",
        "phi_modelling": {
            "support_ratio": 0.5,
            "com_margin": 0.1,
            "drop_normalized": 0.1,
            "support_imbalance": 0.0,
            "left_right_imbalance": 0.0,
            "front_back_imbalance": 0.0,
        },
        "physical": {
            "settle_metrics": {
                "settle_displacement_xyz": [disp_xy[0], disp_xy[1], 0.0]
            }
        },
        "_item": {
            "length": dims[0],
            "width": dims[1],
            "height": dims[2],
            "mass": 2.0,
            "lateralFriction": 0.4,
            "is_soft": False,
        },
    }


class GeometryTests(unittest.TestCase):
    def test_centroid_area_weighted(self):
        patches = [
            {"corners": [(0, 0), (0, 1), (2, 0), (2, 1)], "top": 0.0},
            {"corners": [(2, 0), (2, 1), (3, 0), (3, 1)], "top": 0.0},
        ]
        cx, cy = support_centroid(patches)
        # Areas 2 and 1, centers x=1 and x=2.5 -> (2*1 + 1*2.5)/3 = 1.5
        self.assertAlmostEqual(cx, 1.5)
        self.assertAlmostEqual(cy, 0.5)

    def test_ray_margin_inside_square(self):
        self.assertAlmostEqual(
            ray_hull_margin(SQUARE, (0.5, 0.5), (1.0, 0.0)), 0.5
        )
        self.assertAlmostEqual(
            ray_hull_margin(SQUARE, (0.2, 0.5), (-1.0, 0.0)), 0.2
        )
        diagonal = ray_hull_margin(
            SQUARE, (0.5, 0.5), (1 / math.sqrt(2), 1 / math.sqrt(2))
        )
        self.assertAlmostEqual(diagonal, math.sqrt(2) / 2, places=6)

    def test_ray_margin_degenerate_hull_is_zero(self):
        self.assertEqual(
            ray_hull_margin([(0, 0), (1, 0)], (0.5, 0.0), (1.0, 0.0)),
            0.0,
        )


class FrameTests(unittest.TestCase):
    def _framed(self, x_sign):
        container = bare_container()
        # Support box offset toward +x only: CoM offset direction is +x
        # for the unmirrored scene, -x for the mirrored one.
        # Item at x=0.15 rests on the box (patch x in [0.1, 0.35],
        # centroid 0.225): the CoM offset -- and so downhill -- points
        # toward -x, where the footprint overhangs the box edge.
        container["packed_items"] = [packed_box(0.3 * x_sign, 0.0, 0.34)]
        row = release_row(
            0.15 * x_sign,
            0.0,
            0.6,
            (0.4, 0.3, 0.2),
            (-0.2 * x_sign, 0.07),
        )
        return frame_row(AGENT, row, container)

    def test_mirror_invariance_of_features_and_longitudinal(self):
        plus = self._framed(1)
        minus = self._framed(-1)
        self.assertIsNotNone(plus)
        self.assertIsNotNone(minus)
        for key, value in plus["features"].items():
            self.assertAlmostEqual(
                value, minus["features"][key], places=9, msg=key
            )
        # Longitudinal component is mirror-invariant; transverse flips.
        self.assertAlmostEqual(plus["d_long"], minus["d_long"], places=9)
        self.assertAlmostEqual(
            plus["d_trans"], -minus["d_trans"], places=9
        )

    def test_downhill_displacement_gives_positive_longitudinal(self):
        framed = self._framed(1)
        self.assertGreater(framed["d_long"], 0.0)
        self.assertGreater(framed["features"]["com_offset"], 0.0)

    def test_degenerate_frame_flagged_for_centered_support(self):
        container = bare_container()
        row = release_row(0.0, 0.0, 0.3, (0.4, 0.3, 0.2), (0.0, 0.0))
        framed = frame_row(AGENT, row, container)
        self.assertTrue(framed["degenerate_frame"])


class RidgeTests(unittest.TestCase):
    def test_loso_recovers_linear_signal(self):
        rng = np.random.default_rng(0)
        features = rng.normal(size=(200, 3))
        targets = 2.0 * features[:, 0] - features[:, 2]
        groups = [f"g{i % 10}" for i in range(200)]
        predictions = ridge_loso(features, targets, groups)
        correlation = np.corrcoef(predictions, targets)[0, 1]
        self.assertGreater(correlation, 0.99)


if __name__ == "__main__":
    unittest.main()
