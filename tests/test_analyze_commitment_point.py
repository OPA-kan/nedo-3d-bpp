from __future__ import annotations

import unittest

from scripts.analyze_commitment_point import _freezing_step, _mechanism


def _row(step: int, decided: int) -> dict:
    return {"step": step, "decided_pairs": decided}


def _branch(q: float, placed: float, delta: float, *, control=False) -> dict:
    return {
        "q": q, "is_control": control,
        "support_ledger": {
            "supporter_overlap": {"plain": 0.0, "soft": 0.0, "priority": 0.0},
            "delta_usable_support": delta,
            "footprint_area": 0.04, "base_z": 0.1, "on_floor": True,
            "item_is_soft": False, "item_is_prioritized": False,
        },
        "placed": placed, "fill": placed * 10.0,
    }


class FreezingStepTests(unittest.TestCase):
    def test_earliest_step_of_terminal_invariant_suffix(self) -> None:
        rows = [_row(4, 3), _row(6, 0), _row(8, 2), _row(10, 0), _row(12, 0)]
        self.assertEqual(_freezing_step(rows), 10)

    def test_no_freeze_when_last_step_still_decides(self) -> None:
        rows = [_row(4, 0), _row(6, 1)]
        self.assertIsNone(_freezing_step(rows))

    def test_frozen_from_start(self) -> None:
        rows = [_row(4, 0), _row(6, 0)]
        self.assertEqual(_freezing_step(rows), 4)


class MechanismTests(unittest.TestCase):
    def test_better_branch_higher_delta_counts_toward_mechanism(self) -> None:
        states = [{
            "step": 4,
            "branches": [
                _branch(1.0, 0.6, 0.02),
                _branch(2.0, 0.4, -0.03, control=True),
            ],
        }]
        result = _mechanism(states, "placed")
        self.assertEqual(result["delta_usable_support"]["decided_pairs"], 1)
        self.assertEqual(result["delta_usable_support"]["better_branch_higher"], 1)
        self.assertEqual(result["q"]["better_branch_higher"], 0)


if __name__ == "__main__":
    unittest.main()
