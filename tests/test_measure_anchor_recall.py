import importlib.util
import pathlib
import sys
import unittest
from dataclasses import dataclass

import numpy as np


SCRIPT_PATH = (
    pathlib.Path(__file__).parents[1]
    / "scripts"
    / "measure_anchor_recall.py"
)
SPEC = importlib.util.spec_from_file_location(
    "measure_anchor_recall",
    SCRIPT_PATH,
)
measure = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = measure
SPEC.loader.exec_module(measure)


def candidate(
    item_index,
    center,
    *,
    pool_index=0,
    score=0.0,
    elapsed_seconds=None,
):
    record = {
        "item_index": item_index,
        "pool_index": pool_index,
        "container_index": 0,
        "orientation": 0,
        "kind": "candidate",
        "center": list(center),
        "size": [0.2, 0.2, 0.2],
        "action_center": list(center),
        "score": score,
    }
    if elapsed_seconds is not None:
        record["elapsed_seconds"] = elapsed_seconds
    return record


class AnchorRecallMeasurementTests(unittest.TestCase):
    def test_candidate_key_is_stable_across_transport_precision(self):
        first = candidate(3, [0.1, 0.2, 0.3])
        second = candidate(
            3,
            [
                float(np.float32(0.1)),
                float(np.float32(0.2)),
                float(np.float32(0.3)),
            ],
        )
        self.assertEqual(
            measure.candidate_key(first),
            measure.candidate_key(second),
        )

    def test_summary_uses_physically_valid_oracle_candidates_as_denominator(
        self,
    ):
        first = candidate(
            3,
            [0.0, 0.0, 0.2],
            score=9.0,
            elapsed_seconds=0.4,
        )
        second = candidate(3, [0.2, 0.0, 0.2], score=7.0)
        unsafe = candidate(3, [0.4, 0.0, 0.2], score=20.0)
        oracle = [first, second, unsafe]
        anytime = [second]
        physical = {
            measure.candidate_key(first): {"is_physically_valid": True},
            measure.candidate_key(second): {"is_physically_valid": True},
            measure.candidate_key(unsafe): {"is_physically_valid": False},
        }

        summary = measure.summarize_recall(
            oracle,
            anytime,
            physical,
            oracle_complete=True,
            physics_complete=True,
        )

        self.assertEqual(summary["oracle_settled_count"], 3)
        self.assertEqual(summary["oracle_physical_settled_count"], 2)
        self.assertEqual(summary["anytime_physical_settled_count"], 1)
        self.assertEqual(summary["physical_recall"], 0.5)
        self.assertEqual(summary["best_score_regret"], 2.0)
        self.assertEqual(
            summary["classification"],
            "anytime_missed_physical_settled",
        )

    def test_partial_physics_never_reports_a_recall_value(self):
        oracle = [candidate(3, [0.0, 0.0, 0.2])]
        summary = measure.summarize_recall(
            oracle,
            [],
            {},
            oracle_complete=True,
            physics_complete=False,
        )
        self.assertIsNone(summary["physical_recall"])
        self.assertEqual(summary["classification"], "incomplete")

    def test_extract_anytime_candidates_deduplicates_searches(self):
        record = candidate(3, [0.0, 0.0, 0.2])
        diagnostics = {
            "candidate_audit": [
                {"accepted_settled": [record]},
                {"accepted_settled": [dict(record)]},
            ]
        }
        self.assertEqual(
            measure.extract_anytime_candidates(diagnostics),
            [record],
        )

    def test_unlimited_oracle_enumerates_settled_candidates(self):
        agent = measure.load_agent_module()
        observation = {
            "pool_list": [
                {
                    "index": 4,
                    "length": 0.2,
                    "width": 0.2,
                    "height": 0.2,
                    "mass": 2.0,
                    "is_soft": False,
                    "is_prioritized": False,
                }
            ],
            "container_list": [
                {
                    "index": 0,
                    "length": 2.0,
                    "width": 1.45,
                    "height": 1.61,
                    "thickness": 0.04,
                    "buffer": 0.0,
                    "cut_x": 0.0,
                    "center": [0.0, 0.0, 0.0],
                    "shelf": False,
                    "is_prioritized": False,
                    "packed_items": [],
                }
            ],
        }
        records, complete, stats = measure.enumerate_oracle_candidates(
            agent,
            observation,
        )
        self.assertTrue(complete)
        self.assertTrue(records)
        self.assertTrue(
            all(record["kind"] == "candidate" for record in records)
        )
        self.assertEqual(
            stats["settled_units_started"],
            stats["settled_units_total"],
        )

    def test_json_safe_preserves_snapshot_quaternion_values(self):
        payload = {
            "orn": np.asarray([0.0, 0.0, 0.0, 1.0]),
            "position": (np.float32(0.1), 0.2, 0.3),
        }
        safe = measure.json_safe(payload)
        self.assertEqual(safe["orn"], [0.0, 0.0, 0.0, 1.0])
        self.assertAlmostEqual(safe["position"][0], 0.1, places=6)

    def test_physics_validation_restores_state_between_candidates(self):
        @dataclass
        class FakeItem:
            index: int
            pybullet_id: int | None = None

            def spawn(self, _client, initial_pos, initial_orn):
                self.pybullet_id = 91
                return self.pybullet_id

        class FakeClient:
            def __init__(self):
                self.next_state = 1
                self.restored = []
                self.removed = []

            def saveState(self):
                state = self.next_state
                self.next_state += 1
                return state

            def restoreState(self, stateId):
                self.restored.append(stateId)

            def removeState(self, state):
                self.removed.append(state)

        class FakeValidator:
            def __init__(self):
                self.last_settle_metrics = None

            def check_inclusion(
                self,
                _container,
                _probe,
                _target,
                _orientation,
            ):
                return True

            def place_item(self, _probe, target, _orientation):
                self.last_settle_metrics = {
                    "settle_displacement_norm": abs(float(target[0]))
                }
                return float(target[0]) < 0.15

        class FakeContainer:
            @staticmethod
            def local_to_global(target):
                return target

        class FakeContainerManager:
            @staticmethod
            def get_container(_index):
                return FakeContainer()

        class FakeStreamManager:
            def __init__(self):
                self.item = FakeItem(index=3)

            def get_item(self, _index):
                return self.item

        class FakeEnv:
            def __init__(self):
                self.client = FakeClient()
                self.validator = FakeValidator()
                self.container_manager = FakeContainerManager()
                self.stream_manager = FakeStreamManager()

        stable = candidate(3, [0.1, 0.0, 0.2])
        unstable = candidate(3, [0.2, 0.0, 0.2])
        env = FakeEnv()
        results, complete, _elapsed = measure.validate_candidates(
            env,
            [stable, unstable],
        )

        self.assertTrue(complete)
        self.assertTrue(
            results[measure.candidate_key(stable)]["is_physically_valid"]
        )
        self.assertFalse(
            results[measure.candidate_key(unstable)]["is_physically_valid"]
        )
        self.assertGreaterEqual(env.client.restored.count(2), 2)
        self.assertEqual(set(env.client.removed), {1, 2})


if __name__ == "__main__":
    unittest.main()
