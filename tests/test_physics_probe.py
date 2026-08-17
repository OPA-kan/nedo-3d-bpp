import importlib.util
import math
import pathlib
import sys
import unittest

AGENT_PATH = pathlib.Path(__file__).parents[1] / "agent" / "agent.py"
SPEC = importlib.util.spec_from_file_location("physics_probe_agent", AGENT_PATH)
agent = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = agent
SPEC.loader.exec_module(agent)

SIMULATOR_UTILS_PATH = (
    pathlib.Path(__file__).parents[1]
    / "simulator"
    / "src"
    / "ground_handling"
    / "utils.py"
)

PYBULLET_AVAILABLE = importlib.util.find_spec("pybullet") is not None


def container(packed=()):
    return {
        "length": 2.0,
        "width": 1.4,
        "height": 1.6,
        "thickness": 0.04,
        "buffer": 0.0,
        "cut_x": 0.0,
        "cut_y": 0.0,
        "shelf": False,
        "is_prioritized": False,
        "center": [0.0, 0.0, 0.0],
        "packed_items": list(packed),
    }


def decision_for(place_pos, orientation=0, item_idx=0, container_idx=0):
    candidate = agent.AABB(
        center=tuple(place_pos),
        size=(0.4, 0.4, 0.4),
        name="settled_candidate",
    )
    return agent.PlacementDecision(
        action={
            "item_idx": item_idx,
            "container_idx": container_idx,
            "place_pos": list(place_pos),
            "orientation": orientation,
        },
        candidate=candidate,
        score=1.0,
    )


class KnobTests(unittest.TestCase):
    def test_default_is_off(self):
        self.assertEqual(agent.PHYSICS_PROBE_SHADOW, "")

    def test_official_constants_are_preregistered(self):
        self.assertEqual(agent.PHYSICS_PROBE_SETTLE_STEPS, 300)
        self.assertEqual(agent.PHYSICS_PROBE_DISPLACEMENT_THRESHOLD, 0.3)
        self.assertEqual(agent.PHYSICS_PROBE_ANGLE_THRESHOLD_DEG, 30.0)


class OrientationTableTests(unittest.TestCase):
    def test_orns_table_matches_the_simulator(self):
        spec = importlib.util.spec_from_file_location(
            "ground_handling_utils", SIMULATOR_UTILS_PATH
        )
        utils = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(utils)
        self.assertEqual(len(agent.SIMULATOR_ORNS), len(utils.ORNS))
        for index, (ours, theirs) in enumerate(
            zip(agent.SIMULATOR_ORNS, utils.ORNS)
        ):
            with self.subTest(orientation=index):
                self.assertEqual(len(ours), 3)
                for a, b in zip(ours, theirs):
                    self.assertAlmostEqual(float(a), float(b), places=12)


class GracefulDegradationTests(unittest.TestCase):
    def test_forced_import_failure_disables_the_probe(self):
        state = agent._PHYSICS_PROBE_STATE
        saved = dict(state)
        try:
            state["module"] = None
            state["client"] = None
            state["import_failed"] = True
            self.assertFalse(agent.physics_probe_available())
            observation = {
                "pool_list": [
                    {"length": 0.4, "width": 0.4, "height": 0.4, "mass": 1.0}
                ],
                "container_list": [container()],
            }
            self.assertIsNone(
                agent.physics_probe_settle(
                    observation, decision_for((0.0, 0.0, 0.24))
                )
            )
        finally:
            state.update(saved)

    def test_probe_returns_none_for_missing_decision(self):
        self.assertIsNone(agent.physics_probe_settle({}, None))


@unittest.skipIf(
    not PYBULLET_AVAILABLE,
    "pybullet not installed in this interpreter; run under a pybullet "
    "environment for the physical assertions",
)
class ProbePhysicsTests(unittest.TestCase):
    def test_floor_level_candidate_settles_in_place(self):
        packed = {
            "pos": [0.5, 0.0, 0.24],
            "dims": [0.4, 0.4, 0.4],
            "mass": 2.0,
            "is_soft": False,
        }
        observation = {
            "pool_list": [
                {"length": 0.4, "width": 0.4, "height": 0.4, "mass": 1.0}
            ],
            "container_list": [container(packed=[packed])],
        }
        # Floor top sits at thickness + buffer = 0.04; a 0.4 cube resting
        # on it has its center at 0.24.
        result = agent.physics_probe_settle(
            observation, decision_for((-0.5, 0.0, 0.24))
        )
        self.assertIsNotNone(result)
        self.assertEqual(
            set(result),
            {
                "angle_deg",
                "displacement",
                "predicted_safe",
                "scene_bodies",
                "elapsed_seconds",
            },
        )
        # floor + 4 walls + 1 packed + candidate
        self.assertEqual(result["scene_bodies"], 7)
        self.assertLess(result["displacement"], 0.05)
        self.assertLess(result["angle_deg"], 5.0)
        self.assertTrue(result["predicted_safe"])
        self.assertGreater(result["elapsed_seconds"], 0.0)

    def test_floating_candidate_predicts_the_drop(self):
        observation = {
            "pool_list": [
                {"length": 0.4, "width": 0.4, "height": 0.4, "mass": 1.0}
            ],
            "container_list": [container()],
        }
        # Half a metre of free fall: the settle displacement must exceed
        # the official displacement threshold.
        result = agent.physics_probe_settle(
            observation, decision_for((0.0, 0.0, 0.74))
        )
        self.assertIsNotNone(result)
        self.assertGreater(result["displacement"], 0.3)
        self.assertFalse(result["predicted_safe"])

    def test_repeated_calls_do_not_leak_bodies(self):
        observation = {
            "pool_list": [
                {"length": 0.4, "width": 0.4, "height": 0.4, "mass": 1.0}
            ],
            "container_list": [container()],
        }
        first = agent.physics_probe_settle(
            observation, decision_for((0.0, 0.0, 0.24))
        )
        second = agent.physics_probe_settle(
            observation, decision_for((0.0, 0.0, 0.24))
        )
        self.assertEqual(first["scene_bodies"], second["scene_bodies"])
        self.assertAlmostEqual(
            first["displacement"], second["displacement"], places=6
        )
        self.assertAlmostEqual(
            first["angle_deg"], second["angle_deg"], places=6
        )

    def test_rotated_orientation_uses_the_simulator_euler_table(self):
        observation = {
            "pool_list": [
                {"length": 0.6, "width": 0.4, "height": 0.2, "mass": 1.0}
            ],
            "container_list": [container()],
        }
        # Orientation 1 rotates about X: dims become [l, h, w], so the
        # resting center height is width/2 = 0.2 above the 0.04 floor.
        result = agent.physics_probe_settle(
            observation, decision_for((0.0, 0.0, 0.24), orientation=1)
        )
        self.assertIsNotNone(result)
        self.assertLess(result["displacement"], 0.05)
        self.assertLess(result["angle_deg"], 5.0)
        self.assertTrue(result["predicted_safe"])


if __name__ == "__main__":
    unittest.main()
