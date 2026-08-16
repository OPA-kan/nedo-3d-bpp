from __future__ import annotations

import types
import unittest

from scripts.build_branch_labels import (
    _top_candidate_decisions,
    support_ledger,
)


def _observation(packed: list[dict]) -> dict:
    return {"container_list": [{"packed_items": packed}]}


def _packed(*, x=0.0, y=0.0, top=0.4, size=0.4, soft=False, priority=False) -> dict:
    return {
        "pos": (x, y, top - 0.1), "orn": (0.0, 0.0, 0.0, 1.0),
        "length": size, "width": size, "height": 0.2,
        "is_soft": soft, "is_prioritized": priority,
    }


def _decision(score: float, *, x=0.0, y=0.0, orientation=0, container=0):
    return types.SimpleNamespace(
        score=score,
        action={
            "item_idx": 0, "container_idx": container,
            "place_pos": (x, y, 0.1), "orientation": orientation,
        },
    )


class SupportLedgerTests(unittest.TestCase):
    def test_soft_item_on_plain_top_burns_usable_surface(self) -> None:
        ledger = support_ledger(
            _observation([_packed()]), 0, {"is_soft": True},
            (0.0, 0.0, 0.5), (0.2, 0.2, 0.2),
        )
        self.assertFalse(ledger["on_floor"])
        self.assertAlmostEqual(ledger["supporter_overlap"]["plain"], 0.04)
        self.assertAlmostEqual(ledger["delta_usable_support"], -0.04)

    def test_plain_item_on_plain_top_is_surface_neutral(self) -> None:
        ledger = support_ledger(
            _observation([_packed()]), 0, {},
            (0.0, 0.0, 0.5), (0.2, 0.2, 0.2),
        )
        self.assertAlmostEqual(ledger["delta_usable_support"], 0.0)

    def test_floor_placement_of_soft_item_consumes_floor(self) -> None:
        ledger = support_ledger(
            _observation([]), 0, {"is_soft": True},
            (0.0, 0.0, 0.1), (0.2, 0.2, 0.2),
        )
        self.assertTrue(ledger["on_floor"])
        self.assertAlmostEqual(ledger["delta_usable_support"], -0.04)

    def test_soft_supporter_is_booked_separately(self) -> None:
        ledger = support_ledger(
            _observation([_packed(soft=True)]), 0, {},
            (0.0, 0.0, 0.5), (0.2, 0.2, 0.2),
        )
        self.assertAlmostEqual(ledger["supporter_overlap"]["soft"], 0.04)
        self.assertAlmostEqual(ledger["delta_usable_support"], 0.04)


class TopCandidateSiblingTests(unittest.TestCase):
    def test_near_duplicate_poses_are_skipped(self) -> None:
        selected = _top_candidate_decisions([
            _decision(3.0, x=0.0), _decision(2.9, x=0.01),
            _decision(2.0, x=0.5), _decision(1.0, x=1.0),
        ], 3)
        self.assertEqual([d.score for d in selected], [3.0, 2.0, 1.0])

    def test_orientation_change_counts_as_distinct(self) -> None:
        selected = _top_candidate_decisions([
            _decision(3.0, x=0.0), _decision(2.9, x=0.0, orientation=1),
        ], 2)
        self.assertEqual(len(selected), 2)


if __name__ == "__main__":
    unittest.main()
