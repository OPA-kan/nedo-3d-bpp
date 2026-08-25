import unittest

from scripts.attach_trigger_candidate_actions import attach


class AttachTriggerCandidateActionsTests(unittest.TestCase):
    def test_attaches_actions_by_root_and_candidate_identity(self):
        dataset = {"contract": "terminal_rollout_trigger_dataset_v1", "rows": [{
            "root_id": "r", "candidates": [{"root_candidate_id": "a"}],
        }]}
        recovery = {
            "contract": "trigger_candidate_action_recovery_v1",
            "cell": "c", "actions": {"r": {"a": {"item_idx": 1}}},
        }
        result = attach(dataset, [recovery], expected_cells=1)
        self.assertEqual(
            result["rows"][0]["candidates"][0]["command_action"],
            {"item_idx": 1},
        )
        self.assertEqual(
            result["contract"],
            "terminal_rollout_trigger_dataset_with_actions_v1",
        )

    def test_rejects_incomplete_action_support(self):
        dataset = {"rows": [{
            "root_id": "r", "candidates": [{"root_candidate_id": "a"}],
        }]}
        recovery = {
            "contract": "trigger_candidate_action_recovery_v1",
            "cell": "c", "actions": {"r": {}},
        }
        with self.assertRaisesRegex(ValueError, "missing action"):
            attach(dataset, [recovery], expected_cells=1)


if __name__ == "__main__":
    unittest.main()
