from __future__ import annotations

import unittest

from scripts.analyze_phase_structure import classify, detector_fires


def _state(*, union=100, sp=20, accepted=0, done=6, total=12) -> dict:
    return {
        "oracle_union": union, "support_plane": sp, "cartesian": union - sp,
        "accepted_settled": accepted, "accepted_release": 0,
        "units_completed": done, "units_total": total,
        "deadline_reached": True,
    }


class PhaseClassificationTests(unittest.TestCase):
    def test_four_phases(self) -> None:
        self.assertEqual(classify(_state(union=0, sp=0)), "P3_true_empty")
        self.assertEqual(classify(_state(sp=0)), "P2_generator_hole")
        self.assertEqual(classify(_state(accepted=0)), "P1_deadline_miss")
        self.assertEqual(classify(_state(accepted=5)), "P0_found")


class TrueEmptyDetectorTests(unittest.TestCase):
    def test_fires_on_completed_empty_scan(self) -> None:
        self.assertTrue(detector_fires(_state(union=0, sp=0, done=5)))

    def test_silent_while_drowning(self) -> None:
        self.assertFalse(detector_fires(_state(accepted=0, done=1, total=120)))

    def test_silent_when_settled_found(self) -> None:
        self.assertFalse(detector_fires(_state(accepted=3, done=12)))

    def test_none_without_telemetry(self) -> None:
        state = _state()
        state["units_completed"] = None
        self.assertIsNone(detector_fires(state))


if __name__ == "__main__":
    unittest.main()
