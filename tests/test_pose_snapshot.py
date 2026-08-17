"""
NEDO_POSE_SNAPSHOT: the log-only per-step pose snapshot trace event.

The knob exists so measure_post_shake.py --from-snapshots can rebuild
the pre-shake world from the agent's own observations (each
observation's packed_items carry CURRENT poses, refreshed by the env
after every safe placement) instead of from stale placement-step
records. These tests pin the event's exact shape -- what packed_items
actually carry is pos (world position) AND orn (world quaternion), and
the event must record both verbatim -- and that the knob is off by
default.
"""
import importlib.util
import json
import os
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

AGENT_PATH = pathlib.Path(__file__).parents[1] / "agent" / "agent.py"


def load_agent(module_name, env):
    """Fresh agent module under the given environment overlay.

    NEDO_POSE_SNAPSHOT is read at import time, so the module must be
    loaded (not just patched) per configuration.
    """
    with mock.patch.dict(os.environ, env, clear=False):
        os.environ.pop("NEDO_POSE_SNAPSHOT", None)
        os.environ.update(env)
        spec = importlib.util.spec_from_file_location(
            module_name, AGENT_PATH
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
    return module


def snapshot_container():
    return {
        "index": 0,
        "length": 2.0,
        "width": 1.45,
        "height": 1.61,
        "thickness": 0.04,
        "buffer": 0.0,
        "cut_x": 0.0,
        "require_shelf": False,
        "is_prioritized": False,
        "center": [0.0, 0.0, 0.0],
        "packed_items": [
            {
                # Item.get_info() shape: pos AND orn (quaternion) are
                # both present, refreshed by the env each safe step.
                "index": 3,
                "length": 0.4,
                "width": 0.3,
                "height": 0.2,
                "mass": 2.0,
                "is_prioritized": False,
                "is_soft": True,
                "belongs_to": 0,
                "pos": (0.1, 0.2, 0.15),
                "orn": (0.0, 0.0, 0.7071, 0.7071),
            },
            {
                # Never spawned: the env reports null pose; recorded
                # verbatim, never invented.
                "index": 5,
                "length": 0.3,
                "width": 0.25,
                "height": 0.2,
                "mass": 1.0,
                "is_prioritized": True,
                "is_soft": False,
                "belongs_to": None,
                "pos": None,
                "orn": None,
            },
        ],
    }


def pool_item():
    return {
        "index": 9,
        "length": 0.3,
        "width": 0.25,
        "height": 0.2,
        "mass": 5,
        "is_soft": False,
        "is_prioritized": False,
    }


def run_one_policy_step(agent, trace_path):
    container = snapshot_container()
    observation = {
        "pool_list": [pool_item()],
        "container_list": [container],
    }
    with (
        mock.patch.dict(
            os.environ,
            {"NEDO_POLICY_TRACE_PATH": str(trace_path)},
        ),
        # Force the cheap unsafe_protocol_fallback exit: the snapshot
        # must fire on every step regardless of how the step ends.
        mock.patch.object(
            agent.PlacementCore, "top_candidates", return_value=[]
        ),
        mock.patch.object(agent.PlacementCore, "choose", return_value=None),
    ):
        solver = agent.Agent("")
        solver.get_init_states(
            {
                "optimize": False,
                "lookahead_k": 1,
                "container_list": [container],
            }
        )
        solver.policy(observation)
    return [
        json.loads(line)
        for line in trace_path.read_text(encoding="utf-8").splitlines()
    ]


class PoseSnapshotEventTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.agent = load_agent(
            "pose_snapshot_agent_on", {"NEDO_POSE_SNAPSHOT": "1"}
        )

    def test_event_records_current_poses_verbatim(self):
        with tempfile.TemporaryDirectory() as directory:
            trace_path = pathlib.Path(directory) / "policy.jsonl"
            events = run_one_policy_step(self.agent, trace_path)

        snapshots = [
            event for event in events if event["event"] == "pose_snapshot"
        ]
        self.assertEqual(len(snapshots), 1)
        snapshot = snapshots[0]
        self.assertEqual(snapshot["step"], 0)
        self.assertEqual(len(snapshot["containers"]), 1)
        container = snapshot["containers"][0]
        self.assertEqual(container["container_index"], 0)
        packed = container["packed_items"]
        self.assertEqual(len(packed), 2)

        posed = packed[0]
        self.assertEqual(posed["index"], 3)
        self.assertEqual(posed["pos"], [0.1, 0.2, 0.15])
        self.assertEqual(posed["orn"], [0.0, 0.0, 0.7071, 0.7071])
        self.assertEqual(posed["dims"], [0.4, 0.3, 0.2])
        self.assertTrue(posed["is_soft"])
        self.assertFalse(posed["is_prioritized"])

        unspawned = packed[1]
        self.assertEqual(unspawned["index"], 5)
        self.assertIsNone(unspawned["pos"])
        self.assertIsNone(unspawned["orn"])
        self.assertTrue(unspawned["is_prioritized"])

    def test_snapshot_precedes_the_decision_event(self):
        with tempfile.TemporaryDirectory() as directory:
            trace_path = pathlib.Path(directory) / "policy.jsonl"
            events = run_one_policy_step(self.agent, trace_path)
        kinds = [event["event"] for event in events]
        self.assertLess(
            kinds.index("pose_snapshot"), kinds.index("decision")
        )


class PoseSnapshotDefaultOffTest(unittest.TestCase):
    def test_no_event_without_the_knob(self):
        agent = load_agent("pose_snapshot_agent_off", {})
        self.assertEqual(agent.NEDO_POSE_SNAPSHOT, "")
        with tempfile.TemporaryDirectory() as directory:
            trace_path = pathlib.Path(directory) / "policy.jsonl"
            events = run_one_policy_step(agent, trace_path)
        self.assertNotIn(
            "pose_snapshot", [event["event"] for event in events]
        )


if __name__ == "__main__":
    unittest.main()
