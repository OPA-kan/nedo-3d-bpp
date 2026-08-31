"""Feature extraction, telescoped returns, and the rank correlation."""

from __future__ import annotations

import pathlib
import sys
import unittest

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.probe_value_rankability import (  # noqa: E402
    board_features,
    item_volume,
    spearman,
)


class SpearmanTests(unittest.TestCase):
    def test_perfect_agreement_is_one(self):
        self.assertAlmostEqual(spearman([1, 2, 3, 4], [10, 20, 30, 40]), 1.0)

    def test_perfect_reversal_is_minus_one(self):
        self.assertAlmostEqual(spearman([1, 2, 3, 4], [40, 30, 20, 10]), -1.0)

    def test_it_ranks_rather_than_calibrates(self):
        """A value function for search needs the order, not the scale --
        a wildly miscalibrated but correctly ordered predictor scores 1."""
        self.assertAlmostEqual(
            spearman([1, 2, 3, 4], [1e6, 2e6, 3e6, 4e6]), 1.0,
        )

    def test_ties_do_not_explode(self):
        self.assertIsNotNone(spearman([1, 1, 2, 3], [5, 6, 7, 8]))

    def test_too_few_points_returns_none_rather_than_a_number(self):
        self.assertIsNone(spearman([1, 2], [3, 4]))

    def test_a_constant_predictor_is_undefined_not_zero(self):
        self.assertIsNone(spearman([7, 7, 7, 7], [1, 2, 3, 4]))


class BoardFeatureTests(unittest.TestCase):
    def _observation(self, depth, height=2.0, packed=1, pool=1):
        return {
            "depth_map": np.asarray(depth, dtype=float),
            "container_list": [{
                "height": height,
                "packed_items": [{"index": i} for i in range(packed)],
            }],
            "pool_list": [
                {"length": 1.0, "width": 2.0, "height": 0.5}
            ] * pool,
        }

    def test_a_live_ndarray_depth_map_does_not_raise(self):
        """`or []` on an ndarray raises ValueError -- the probe hit this
        on its first real run, because a stub dict had hidden it."""
        features = board_features(self._observation([[[0.0, 0.0], [0.0, 0.0]]]))
        self.assertIn("free_height_sum", features)

    def test_a_missing_depth_map_degrades_instead_of_raising(self):
        features = board_features({
            "container_list": [], "pool_list": [],
        })
        self.assertEqual(features["placed_count"], 0.0)
        self.assertNotIn("free_height_sum", features)

    def test_a_flat_board_has_no_total_variation(self):
        features = board_features(self._observation([[[1.0, 1.0], [1.0, 1.0]]]))
        self.assertAlmostEqual(features["surface_total_variation"], 0.0)

    def test_a_stepped_board_has_total_variation(self):
        features = board_features(self._observation([[[0.0, 1.0], [0.0, 1.0]]]))
        self.assertGreater(features["surface_total_variation"], 0.0)

    def test_free_height_falls_as_the_board_fills(self):
        empty = board_features(self._observation([[[0.0, 0.0], [0.0, 0.0]]]))
        full = board_features(self._observation([[[2.0, 2.0], [2.0, 2.0]]]))
        self.assertGreater(empty["free_height_sum"], full["free_height_sum"])
        self.assertAlmostEqual(full["free_height_sum"], 0.0)

    def test_counts_come_from_the_containers_and_the_pool(self):
        features = board_features(self._observation(
            [[[0.0, 0.0], [0.0, 0.0]]], packed=5, pool=3,
        ))
        self.assertEqual(features["placed_count"], 5.0)
        self.assertEqual(features["visible_pool_count"], 3.0)
        self.assertAlmostEqual(features["visible_pool_volume"], 3.0)


class ItemVolumeTests(unittest.TestCase):
    OBSERVATION = {"pool_list": [
        {"length": 1.0, "width": 2.0, "height": 3.0},
        {"length": 1.0, "width": 1.0, "height": 1.0},
    ]}

    def test_reads_the_acted_on_item(self):
        self.assertAlmostEqual(
            item_volume(self.OBSERVATION, {"item_idx": 0}), 6.0,
        )
        self.assertAlmostEqual(
            item_volume(self.OBSERVATION, {"item_idx": 1}), 1.0,
        )

    def test_an_out_of_range_index_is_zero_not_an_exception(self):
        self.assertEqual(item_volume(self.OBSERVATION, {"item_idx": 9}), 0.0)


class TelescopedReturnTests(unittest.TestCase):
    def test_the_return_is_the_suffix_sum_of_rewards(self):
        """V(s_t) = sum of r_k for k >= t, which is the gamma=1 return the
        n-step TD target would use."""
        states = [{"reward": r} for r in (3.0, 2.0, 5.0)]
        tail = 0.0
        for row in reversed(states):
            tail += row["reward"]
            row["rule_alpha_return"] = tail
        self.assertEqual(
            [row["rule_alpha_return"] for row in states], [10.0, 7.0, 5.0],
        )


if __name__ == "__main__":
    unittest.main()
