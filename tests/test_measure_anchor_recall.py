import importlib.util
import pathlib
import sys
import unittest
from dataclasses import dataclass
from unittest import mock

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
        release = candidate(3, [0.1, 0.0, 0.2])
        release["kind"] = "release_candidate"
        diagnostics = {
            "candidate_audit": [
                {
                    "accepted_settled": [record],
                    "accepted_release": [release],
                },
                {
                    "accepted_settled": [dict(record)],
                    "accepted_release": [dict(release)],
                },
            ]
        }
        self.assertEqual(
            measure.extract_anytime_candidates(diagnostics),
            [record],
        )
        self.assertEqual(
            measure.extract_anytime_candidates(
                diagnostics,
                candidate_kind="release",
            ),
            [release],
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

    def test_release_oracle_enumerates_only_release_candidates(self):
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
            attempt_kind="release",
        )

        self.assertTrue(complete)
        self.assertTrue(records)
        self.assertEqual(
            {record["kind"] for record in records},
            {"release_candidate"},
        )
        self.assertEqual(stats["attempt_kind"], "release")
        self.assertNotIn("settled_units_started", stats)

    def test_oracle_forces_legacy_cartesian_generator(self):
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
        modes = []
        original = agent.CandidateGenerator.iter_attempts

        def recording_iterator(*args, **kwargs):
            modes.append(kwargs.get("generator_mode"))
            yield from original(*args, **kwargs)

        with mock.patch.object(
            agent.CandidateGenerator,
            "iter_attempts",
            side_effect=recording_iterator,
        ):
            measure.enumerate_oracle_candidates(agent, observation)

        self.assertTrue(modes)
        self.assertEqual(set(modes), {"cartesian"})

    def test_dual_oracle_deduplicates_and_records_generator_provenance(self):
        shared = candidate(3, [0.0, 0.0, 0.2])
        cartesian_only = candidate(3, [0.2, 0.0, 0.2])
        support_only = candidate(3, [0.4, 0.0, 0.2])

        def enumerate_mode(
            _agent,
            _observation,
            *,
            generator_mode,
            attempt_kind,
            max_candidates=None,
        ):
            self.assertEqual(attempt_kind, "settled")
            records = (
                [shared, cartesian_only]
                if generator_mode == "cartesian"
                else [dict(shared), support_only]
            )
            return records, True, {"attempts": len(records)}

        with mock.patch.object(
            measure,
            "enumerate_oracle_candidates",
            side_effect=enumerate_mode,
        ):
            records, complete, stats = (
                measure.enumerate_dual_settled_oracle(
                    object(),
                    {},
                )
            )

        by_center = {
            tuple(record["center"]): record for record in records
        }
        self.assertTrue(complete)
        self.assertEqual(len(records), 3)
        self.assertEqual(
            by_center[(0.0, 0.0, 0.2)]["oracle_generators"],
            ["cartesian", "support_plane"],
        )
        self.assertEqual(stats["overlap_count"], 1)
        self.assertEqual(stats["cartesian_only_count"], 1)
        self.assertEqual(stats["support_plane_only_count"], 1)

    def test_failure_classification_distinguishes_deadline_and_dead_end(self):
        base_log = {
            "action_source": "fixed_fallback",
            "accepted_settled_count": 0,
            "accepted_release_count": 0,
        }
        deadline = measure.classify_failure_state(
            base_log,
            settled_physical_safe_count=2,
            release_physical_safe_count=0,
            oracle_complete=True,
            physics_complete=True,
        )
        dead_end = measure.classify_failure_state(
            base_log,
            settled_physical_safe_count=0,
            release_physical_safe_count=0,
            oracle_complete=True,
            physics_complete=True,
        )
        release_only = measure.classify_failure_state(
            base_log,
            settled_physical_safe_count=0,
            release_physical_safe_count=1,
            oracle_complete=True,
            physics_complete=True,
        )
        invariant = measure.classify_failure_state(
            {
                **base_log,
                "accepted_settled_count": 1,
            },
            settled_physical_safe_count=0,
            release_physical_safe_count=0,
            oracle_complete=True,
            physics_complete=True,
        )

        self.assertEqual(deadline, "deadline_missed_safe_settled")
        self.assertEqual(dead_end, "no_safe_candidate_in_oracle_sets")
        self.assertEqual(release_only, "safe_release_only")
        self.assertEqual(invariant, "incumbent_invariant_violation")

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

            def spawn(self, client, initial_pos, initial_orn):
                self.pybullet_id = 91
                client.add_body()
                return self.pybullet_id

            def remove(self, client):
                if self.pybullet_id is not None:
                    client.remove_body()
                    self.pybullet_id = None

        class FakeClient:
            def __init__(self):
                self.next_state = 1
                self.body_count = 0
                self.state_body_counts = {}
                self.restored = []
                self.removed = []

            def add_body(self):
                self.body_count += 1

            def remove_body(self):
                self.body_count -= 1

            def saveState(self):
                state = self.next_state
                self.next_state += 1
                self.state_body_counts[state] = self.body_count
                return state

            def restoreState(self, stateId):
                expected = self.state_body_counts[stateId]
                if self.body_count != expected:
                    raise RuntimeError(
                        f"body count mismatch: "
                        f"{self.body_count} != {expected}"
                    )
                self.restored.append(stateId)

            def removeState(self, state):
                self.removed.append(state)
                self.state_body_counts.pop(state)

        class FakeValidator:
            def __init__(self, client):
                self.client = client
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
                stable = float(target[0]) < 0.15
                if not stable:
                    _probe.remove(self.client)
                return stable

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
                self.validator = FakeValidator(self.client)
                self.container_manager = FakeContainerManager()
                self.stream_manager = FakeStreamManager()

        stable = candidate(3, [0.1, 0.0, 0.2])
        unstable = candidate(3, [0.2, 0.0, 0.2])
        stable_after_failure = candidate(3, [0.12, 0.0, 0.2])
        env = FakeEnv()
        results, complete, _elapsed = measure.validate_candidates(
            env,
            [stable, unstable, stable_after_failure],
        )

        self.assertTrue(complete)
        self.assertTrue(
            results[measure.candidate_key(stable)]["is_physically_valid"]
        )
        self.assertFalse(
            results[measure.candidate_key(unstable)]["is_physically_valid"]
        )
        self.assertTrue(
            results[
                measure.candidate_key(stable_after_failure)
            ]["is_physically_valid"]
        )
        self.assertEqual(env.client.body_count, 0)


if __name__ == "__main__":
    unittest.main()
