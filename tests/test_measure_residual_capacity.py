import importlib.util
import pathlib
import sys
import unittest

import numpy as np


MODULE_PATH = (
    pathlib.Path(__file__).parents[1]
    / "scripts"
    / "measure_residual_capacity.py"
)
SPEC = importlib.util.spec_from_file_location(
    "measure_residual_capacity", MODULE_PATH
)
capacity_mod = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = capacity_mod
SPEC.loader.exec_module(capacity_mod)


class FakeAnchor:
    def __init__(self, center, size):
        self.center = tuple(center)
        self.size = tuple(size)

    @property
    def minimum(self):
        return tuple(
            c - s / 2.0 for c, s in zip(self.center, self.size)
        )

    @property
    def maximum(self):
        return tuple(
            c + s / 2.0 for c, s in zip(self.center, self.size)
        )


class FakeAgent:
    SETTLED_ITEM_CLEARANCE = 0.026


class RemainingClassesTests(unittest.TestCase):
    def test_classes_quantize_dims_and_count_multiplicity(self):
        items = [
            {"index": 0, "length": 0.4, "width": 0.3, "height": 0.2},
            {"index": 1, "length": 0.4, "width": 0.3, "height": 0.2},
            {"index": 2, "length": 0.6, "width": 0.5, "height": 0.4},
        ]
        classes = capacity_mod.remaining_classes(items, packed_indices={2})
        self.assertEqual(len(classes), 1)
        self.assertEqual(classes[0]["count"], 2)
        self.assertAlmostEqual(classes[0]["volume"], 0.4 * 0.3 * 0.2)

    def test_classes_sorted_by_volume_descending(self):
        items = [
            {"index": 0, "length": 0.2, "width": 0.2, "height": 0.2},
            {"index": 1, "length": 0.5, "width": 0.5, "height": 0.5},
        ]
        classes = capacity_mod.remaining_classes(items, packed_indices=set())
        self.assertGreater(classes[0]["volume"], classes[1]["volume"])


class ConflictTests(unittest.TestCase):
    def test_lateral_overlap_within_clearance_conflicts(self):
        a = FakeAnchor((0.0, 0.0, 0.1), (0.4, 0.4, 0.2))
        b = FakeAnchor((0.41, 0.0, 0.1), (0.4, 0.4, 0.2))
        self.assertTrue(capacity_mod.anchors_conflict(a, b, 0.026))

    def test_clear_separation_does_not_conflict(self):
        a = FakeAnchor((0.0, 0.0, 0.1), (0.4, 0.4, 0.2))
        b = FakeAnchor((0.5, 0.0, 0.1), (0.4, 0.4, 0.2))
        self.assertFalse(capacity_mod.anchors_conflict(a, b, 0.026))

    def test_vertical_stacking_does_not_conflict(self):
        a = FakeAnchor((0.0, 0.0, 0.1), (0.4, 0.4, 0.2))
        b = FakeAnchor((0.0, 0.0, 0.3), (0.4, 0.4, 0.2))
        self.assertFalse(capacity_mod.anchors_conflict(a, b, 0.026))


class GreedyPackTests(unittest.TestCase):
    def test_multiplicity_limits_class_usage(self):
        entry = {
            "signature": (0.4, 0.4, 0.2),
            "count": 1,
            "volume": 0.032,
        }
        anchors = [
            FakeAnchor((0.0, 0.0, 0.1), (0.4, 0.4, 0.2)),
            FakeAnchor((1.0, 0.0, 0.1), (0.4, 0.4, 0.2)),
        ]
        count, volume = capacity_mod.greedy_simultaneous_placements(
            FakeAgent, [entry], [anchors]
        )
        self.assertEqual(count, 1)
        self.assertAlmostEqual(volume, 0.032)

    def test_conflicting_anchors_yield_single_placement(self):
        entry = {
            "signature": (0.4, 0.4, 0.2),
            "count": 5,
            "volume": 0.032,
        }
        anchors = [
            FakeAnchor((0.0, 0.0, 0.1), (0.4, 0.4, 0.2)),
            FakeAnchor((0.01, 0.0, 0.1), (0.4, 0.4, 0.2)),
        ]
        count, _volume = capacity_mod.greedy_simultaneous_placements(
            FakeAgent, [entry], [anchors]
        )
        self.assertEqual(count, 1)

    def test_disjoint_anchors_both_taken(self):
        entry = {
            "signature": (0.4, 0.4, 0.2),
            "count": 5,
            "volume": 0.032,
        }
        anchors = [
            FakeAnchor((0.0, 0.0, 0.1), (0.4, 0.4, 0.2)),
            FakeAnchor((1.0, 0.0, 0.1), (0.4, 0.4, 0.2)),
        ]
        count, volume = capacity_mod.greedy_simultaneous_placements(
            FakeAgent, [entry], [anchors]
        )
        self.assertEqual(count, 2)
        self.assertAlmostEqual(volume, 0.064)


class ComponentTests(unittest.TestCase):
    def test_split_regions_are_separate_components(self):
        anchors = [
            FakeAnchor((0.0, 0.0, 0.1), (0.3, 0.3, 0.2)),
            FakeAnchor((0.1, 0.0, 0.1), (0.3, 0.3, 0.2)),
            FakeAnchor((2.0, 0.0, 0.1), (0.3, 0.3, 0.2)),
        ]
        components, largest = capacity_mod.anchor_components(anchors)
        self.assertEqual(components, 2)
        self.assertEqual(largest, 2)

    def test_empty_anchor_set(self):
        self.assertEqual(capacity_mod.anchor_components([]), (0, 0))


class RegressionTests(unittest.TestCase):
    def _rows(self):
        rows = []
        rng = np.random.default_rng(3)
        for index in range(12):
            capacity = float(rng.uniform(0.0, 0.2))
            rows.append(
                {
                    "snapshot_id": f"s{index}",
                    "case_source": "b000" if index % 2 else "b001",
                    "step": index,
                    "look_ahead": 20,
                    "occupied_volume_ratio": index / 12.0,
                    "settled_cap_volume": capacity,
                    "settled_simultaneous_volume": capacity * 2.0,
                    "release_cap_volume": capacity / 2.0,
                    "release_corridor_volume": capacity / 3.0,
                    "combined_simultaneous_count": index % 4,
                    "release_anchor_ht_total": 10.0 * (index % 4),
                    "placed_to_go": 12 - index,
                }
            )
        return rows

    def test_loso_regression_reports_finite_metrics(self):
        rows = self._rows()
        report = capacity_mod.loso_regression(
            rows, capacity_mod.BASELINE_FEATURES
        )
        self.assertEqual(report["n"], 12)
        self.assertTrue(np.isfinite(report["loso_mae"]))
        self.assertTrue(np.isfinite(report["loso_r2"]))

    def test_residual_correlations_cover_all_descriptors(self):
        report = capacity_mod.residual_correlations(self._rows())
        self.assertEqual(
            set(report), set(capacity_mod.DESCRIPTOR_FEATURES)
        )


class CaseRebuildTests(unittest.TestCase):
    def test_rebuild_case_items_parses_case_id(self):
        items, look_ahead = capacity_mod.rebuild_case_items("b000-k20")
        self.assertEqual(look_ahead, 20)
        self.assertEqual(len(items), 41)


if __name__ == "__main__":
    unittest.main()
