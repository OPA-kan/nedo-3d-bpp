from __future__ import annotations

import unittest

from scripts.analyze_deviation_trigger import (
    FEATURE_NAMES,
    rank_auc,
    state_features,
    state_label,
)


def _branch(q: float, placed: float, *, control=False, soft=False) -> dict:
    return {
        "q": q, "is_control": control, "kind": "candidate",
        "support_ledger": {
            "item_is_soft": soft, "item_is_prioritized": False,
            "footprint_area": 0.04, "base_z": 0.2, "on_floor": False,
            "supporter_overlap": {"plain": 0.04, "soft": 0.0, "priority": 0.0},
            "delta_usable_support": 0.0,
        },
        "placed": placed, "fill": placed * 40.0,
    }


class DeviationTriggerTests(unittest.TestCase):
    def test_rank_auc_orders_separable_scores(self) -> None:
        self.assertEqual(rank_auc([3.0, 2.0, 1.0], [True, False, False]), 1.0)
        self.assertEqual(rank_auc([1.0, 2.0], [True, False]), 0.0)
        self.assertIsNone(rank_auc([1.0], [True]))

    def test_state_features_match_declared_names(self) -> None:
        state = {"step": 6, "branches": [
            _branch(1.0, 0.5, control=True), _branch(0.9, 0.6),
        ]}
        features = state_features(state)
        self.assertEqual(len(features), len(FEATURE_NAMES))
        self.assertEqual(features[0], 6.0)
        self.assertEqual(features[1], 2.0)

    def test_avoidable_label_requires_a_strictly_better_sibling(self) -> None:
        state = {"step": 6, "branches": [
            _branch(1.0, 0.5, control=True), _branch(0.9, 0.6),
        ]}
        avoidable, gap = state_label(state, "placed")
        self.assertTrue(avoidable)
        self.assertAlmostEqual(gap, 0.1)
        tied = {"step": 6, "branches": [
            _branch(1.0, 0.5, control=True), _branch(0.9, 0.4),
        ]}
        avoidable, gap = state_label(tied, "placed")
        self.assertFalse(avoidable)
        self.assertAlmostEqual(gap, 0.0)


if __name__ == "__main__":
    unittest.main()
