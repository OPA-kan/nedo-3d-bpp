import unittest

from scripts.attach_trigger_candidate_actions import attach


class AttachTriggerCandidateActionsTests(unittest.TestCase):
    def test_attaches_actions_by_cell_root_and_candidate_identity(self):
        dataset = {"contract": "terminal_rollout_trigger_dataset_v1", "rows": [{
            "cell": "c", "root_id": "r",
            "candidates": [{"root_candidate_id": "a"}],
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
            "cell": "c", "root_id": "r",
            "candidates": [{"root_candidate_id": "a"}],
        }]}
        recovery = {
            "contract": "trigger_candidate_action_recovery_v1",
            "cell": "c", "actions": {"r": {}},
        }
        with self.assertRaisesRegex(ValueError, "missing action"):
            attach(dataset, [recovery], expected_cells=1)

    def test_same_root_id_in_two_cells_never_cross_wires(self):
        # Board fingerprints ignore container geometry, so two scenarios
        # sharing a stream produce the same root_id for the all-empty
        # board while their candidate sets differ. Wave-4's 100-cell run
        # hit exactly this: a flat root_id map let one cell's recovery
        # shadow the other's and the attach step died on a candidate
        # that was recovered all along.
        dataset = {"contract": "terminal_rollout_trigger_dataset_v1", "rows": [
            {"cell": "dual", "root_id": "r",
             "candidates": [{"root_candidate_id": "dual-a"}]},
            {"cell": "single", "root_id": "r",
             "candidates": [{"root_candidate_id": "single-a"}]},
        ]}
        recoveries = [
            {"contract": "trigger_candidate_action_recovery_v1",
             "cell": "dual",
             "actions": {"r": {"dual-a": {"item_idx": 1}}}},
            {"contract": "trigger_candidate_action_recovery_v1",
             "cell": "single",
             "actions": {"r": {"single-a": {"item_idx": 2}}}},
        ]
        result = attach(dataset, recoveries, expected_cells=2)
        self.assertEqual(
            result["rows"][0]["candidates"][0]["command_action"],
            {"item_idx": 1},
        )
        self.assertEqual(
            result["rows"][1]["candidates"][0]["command_action"],
            {"item_idx": 2},
        )


if __name__ == "__main__":
    unittest.main()
