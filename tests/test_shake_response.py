"""
The pure half of the local stability proxy.

The driving half needs PyBullet; this half is where the arithmetic and the
accounting decisions live, so it is tested without a physics engine. The
decisions worth pinning are what happens to an item that leaves the
simulation, and that nothing here is called a score.
"""
import importlib.util
import math
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]

# By path, not via sys.path: simulator/agent.py is the synced submission and
# shadows this repository's `agent` package for later test modules.
_SPEC = importlib.util.spec_from_file_location(
    "_ground_handling_diagnostics_shake",
    ROOT / "simulator" / "src" / "ground_handling" / "diagnostics.py",
)
_D = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_D)
shake_response_metrics = _D.shake_response_metrics


IDENTITY = [0.0, 0.0, 0.0, 1.0]


def pose(index, x=0.0, y=0.0, z=0.0, orn=None):
    return {"index": index, "pos": [x, y, z], "orn": list(orn or IDENTITY)}


def yaw(degrees):
    half = math.radians(degrees) / 2.0
    return [0.0, 0.0, math.sin(half), math.cos(half)]


class DisplacementTests(unittest.TestCase):
    def test_a_board_that_does_not_move_scores_zero_everywhere(self):
        poses = [pose(0), pose(1, x=0.5)]

        result = shake_response_metrics(poses, poses, 0.0)

        self.assertEqual(result["shake_max_shift"], 0.0)
        self.assertEqual(result["shake_max_rotation_deg"], 0.0)
        self.assertEqual(result["shake_items_shifted"], 0)
        self.assertEqual(result["shake_items_toppled"], 0)

    def test_shift_is_the_euclidean_distance_from_the_pre_shake_pose(self):
        before = [pose(0)]
        after = [pose(0, x=0.3, y=0.4)]

        result = shake_response_metrics(before, after, 0.0)

        self.assertAlmostEqual(result["shake_max_shift"], 0.5, places=9)

    def test_only_shifts_past_the_threshold_are_counted(self):
        before = [pose(0), pose(1, x=1.0)]
        after = [pose(0, x=0.001), pose(1, x=1.5)]

        result = shake_response_metrics(before, after, 0.0)

        self.assertEqual(result["shake_items_shifted"], 1)
        self.assertGreater(result["shake_mean_shift"], 0.0)


class RotationTests(unittest.TestCase):
    def test_rotation_is_read_off_the_quaternion(self):
        before = [pose(0)]
        after = [pose(0, orn=yaw(90.0))]

        result = shake_response_metrics(before, after, 0.0)

        self.assertAlmostEqual(result["shake_max_rotation_deg"], 90.0, places=4)

    def test_a_small_rotation_is_not_a_topple(self):
        before = [pose(0)]
        after = [pose(0, orn=yaw(5.0))]

        result = shake_response_metrics(before, after, 0.0)

        self.assertEqual(result["shake_items_toppled"], 0)

    def test_the_quaternion_sign_does_not_invent_a_rotation(self):
        """
        q and -q are the same orientation. Without the absolute value this
        reads as a 360 degree topple, which would make the metric depend on
        which representative the solver happened to return.
        """
        before = [pose(0)]
        after = [pose(0, orn=[0.0, 0.0, 0.0, -1.0])]

        result = shake_response_metrics(before, after, 0.0)

        self.assertAlmostEqual(result["shake_max_rotation_deg"], 0.0, places=6)


class LostItemTests(unittest.TestCase):
    def test_an_item_that_leaves_is_charged_as_both_a_shift_and_a_topple(self):
        """
        No lid is added, so an item can exit through the opening. Dropping
        it from the averages would make the worst possible outcome improve
        the score.
        """
        before = [pose(0), pose(1, x=1.0)]
        after = [pose(0)]

        result = shake_response_metrics(before, after, 0.0)

        self.assertEqual(result["shake_items_lost"], 1)
        self.assertEqual(result["shake_items_shifted"], 1)
        self.assertEqual(result["shake_items_toppled"], 1)

    def test_an_empty_container_is_reported_rather_than_failing(self):
        result = shake_response_metrics([], [], 0.0)

        self.assertEqual(result["shake_items"], 0)
        self.assertEqual(result["shake_max_shift"], 0.0)


class ContractTests(unittest.TestCase):
    def test_kinetic_energy_is_passed_through(self):
        result = shake_response_metrics([pose(0)], [pose(0)], 12.5)

        self.assertEqual(result["shake_peak_kinetic_energy"], 12.5)

    def test_no_field_is_named_score(self):
        """
        The protocol behind stability_score is undisclosed, so nothing here
        may pass for the official number.
        """
        result = shake_response_metrics([pose(0)], [pose(0)], 0.0)

        self.assertFalse([key for key in result if "score" in key])


if __name__ == "__main__":
    unittest.main()
