"""Physical truth-table check for soft/priority coverage.

This is the missing boundary between the pure 16-combination contract test
and real settled geometry: the agent predicate is evaluated before placement,
two bodies are settled by PyBullet, and the bundled final-state diagnostic is
then evaluated from PyBullet's own AABBs.
"""

from __future__ import annotations

import importlib.util
import os
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
AGENT_PATH = ROOT / "agent" / "agent.py"
DIAGNOSTICS_PATH = (
    ROOT / "simulator" / "src" / "ground_handling" / "diagnostics.py"
)

PYBULLET_AVAILABLE = importlib.util.find_spec("pybullet") is not None

_AGENT_SPEC = importlib.util.spec_from_file_location(
    "attribute_e2e_agent", AGENT_PATH
)
agent = importlib.util.module_from_spec(_AGENT_SPEC)
sys.modules[_AGENT_SPEC.name] = agent
_AGENT_SPEC.loader.exec_module(agent)

_DIAGNOSTICS_SPEC = importlib.util.spec_from_file_location(
    "attribute_e2e_diagnostics", DIAGNOSTICS_PATH
)
diagnostics = importlib.util.module_from_spec(_DIAGNOSTICS_SPEC)
_DIAGNOSTICS_SPEC.loader.exec_module(diagnostics)


class PyBulletAttributeTruthTableTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not PYBULLET_AVAILABLE:
            if os.environ.get("NEDO_REQUIRE_INTEGRATION") == "1":
                raise RuntimeError(
                    "NEDO_REQUIRE_INTEGRATION=1 but pybullet is unavailable"
                )
            raise unittest.SkipTest(
                "pybullet not installed; integration CI must run this test "
                "without skip"
            )
        import pybullet

        cls.p = pybullet
        cls.client = pybullet.connect(pybullet.DIRECT)

    @classmethod
    def tearDownClass(cls):
        cls.p.disconnect(cls.client)

    def _settled_pair(self, lower_flags, upper_flags):
        p = self.p
        p.resetSimulation(physicsClientId=self.client)
        p.setPhysicsEngineParameter(
            deterministicOverlappingPairs=1,
            physicsClientId=self.client,
        )
        p.setGravity(0.0, 0.0, -9.8, physicsClientId=self.client)

        floor_shape = p.createCollisionShape(
            p.GEOM_BOX,
            halfExtents=[1.0, 1.0, 0.025],
            physicsClientId=self.client,
        )
        p.createMultiBody(
            baseMass=0.0,
            baseCollisionShapeIndex=floor_shape,
            basePosition=[0.0, 0.0, -0.025],
            physicsClientId=self.client,
        )
        box_shape = p.createCollisionShape(
            p.GEOM_BOX,
            halfExtents=[0.1, 0.1, 0.1],
            physicsClientId=self.client,
        )
        lower_id = p.createMultiBody(
            baseMass=1.0,
            baseCollisionShapeIndex=box_shape,
            basePosition=[0.0, 0.0, 0.1],
            physicsClientId=self.client,
        )
        upper_id = p.createMultiBody(
            baseMass=1.0,
            baseCollisionShapeIndex=box_shape,
            basePosition=[0.0, 0.0, 0.3],
            physicsClientId=self.client,
        )
        for body in (lower_id, upper_id):
            p.changeDynamics(
                body,
                -1,
                lateralFriction=0.8,
                rollingFriction=0.0,
                spinningFriction=0.0,
                restitution=0.0,
                physicsClientId=self.client,
            )
        for _ in range(300):
            p.stepSimulation(physicsClientId=self.client)

        self.assertTrue(
            p.getContactPoints(
                bodyA=lower_id,
                bodyB=upper_id,
                physicsClientId=self.client,
            ),
            "the physical fixture did not produce the required contact",
        )

        def item(index, body_id, flags):
            pos, _orn = p.getBasePositionAndOrientation(
                body_id, physicsClientId=self.client
            )
            aabb_min, aabb_max = p.getAABB(
                body_id, physicsClientId=self.client
            )
            return {
                "index": index,
                "mass": 1.0,
                "volume": 0.2 ** 3,
                "pos": list(pos),
                "aabb_min": list(aabb_min),
                "aabb_max": list(aabb_max),
                "is_soft": bool(flags[0]),
                "is_prioritized": bool(flags[1]),
            }

        snapshot = [{
            "index": 0,
            "volume": 8.0,
            "is_prioritized": False,
            "packed_items": [
                item(0, lower_id, lower_flags),
                item(1, upper_id, upper_flags),
            ],
        }]
        return diagnostics.calculate_attribute_placement(snapshot)

    def test_all_sixteen_attribute_pairs_match_the_published_rule(self):
        combinations = (
            (False, False),
            (True, False),
            (False, True),
            (True, True),
        )
        for lower_soft, lower_priority in combinations:
            for upper_soft, upper_priority in combinations:
                with self.subTest(
                    lower=(lower_soft, lower_priority),
                    upper=(upper_soft, upper_priority),
                ):
                    measured = self._settled_pair(
                        (lower_soft, lower_priority),
                        (upper_soft, upper_priority),
                    )
                    expected_soft = int(lower_soft and not upper_soft)
                    expected_priority = int(
                        lower_priority and not upper_priority
                    )
                    self.assertEqual(
                        measured["soft_covered_by_other"], expected_soft
                    )
                    self.assertEqual(
                        measured["priority_covered_by_other"],
                        expected_priority,
                    )

                    mover = {
                        "is_soft": upper_soft,
                        "is_prioritized": upper_priority,
                    }
                    preaction_legal = agent.attribute_rest_is_legal(
                        mover, lower_soft, lower_priority
                    )
                    self.assertEqual(
                        preaction_legal,
                        not bool(expected_soft or expected_priority),
                    )


if __name__ == "__main__":
    unittest.main()
