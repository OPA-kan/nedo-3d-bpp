import unittest

from scripts.evaluate_one_step_paired_shake import (
    build_changed_action_pairs,
    compare_shake_arms,
)


def _root():
    def action(item_idx):
        return {
            "item_idx": item_idx,
            "container_idx": 0,
            "place_pos": [0.0, 0.0, 0.1],
            "orientation": 0,
        }

    return {
        "root_id": "root-a",
        "case_id": "m-case",
        "step": 7,
        "record": {
            "candidate_set": [
                {"candidate_id": "old", "command_action": action(1)},
                {"candidate_id": "new", "command_action": action(2)},
            ]
        },
    }


class OneStepPairedShakeTests(unittest.TestCase):
    def test_selects_only_reference_q_top_changes_and_resolves_actions(self):
        baseline = {"roots": [{
            "root_id": "root-a", "reference_signature": {"q_top": "old"},
        }]}
        rescue = {"roots": [{
            "root_id": "root-a", "reference_signature": {"q_top": "new"},
        }]}

        pairs = build_changed_action_pairs([_root()], baseline, rescue)

        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0]["baseline_candidate_id"], "old")
        self.assertEqual(pairs[0]["rescue_candidate_id"], "new")
        self.assertEqual(pairs[0]["baseline_action"]["item_idx"], 1)
        self.assertEqual(pairs[0]["rescue_action"]["item_idx"], 2)

    def test_rejects_candidate_ids_missing_from_frozen_root_support(self):
        baseline = {"roots": [{
            "root_id": "root-a", "reference_signature": {"q_top": "old"},
        }]}
        rescue = {"roots": [{
            "root_id": "root-a", "reference_signature": {"q_top": "missing"},
        }]}

        with self.assertRaisesRegex(ValueError, "missing from frozen root"):
            build_changed_action_pairs([_root()], baseline, rescue)

    def test_compares_peak_energy_and_post_shake_attributes_separately(self):
        baseline = {
            "peak_kinetic_energy": 10.0,
            "peak_kinetic_energy_per_item": 2.0,
            "peak_kinetic_energy_per_mass": 0.5,
            "max_shift": 0.1,
            "toppled_fraction": 0.0,
            "post_shake_soft_covered_by_other": 1,
            "post_shake_priority_covered_by_other": 0,
        }
        rescue = {
            "peak_kinetic_energy": 14.0,
            "peak_kinetic_energy_per_item": 2.8,
            "peak_kinetic_energy_per_mass": 0.7,
            "max_shift": 0.08,
            "toppled_fraction": 0.2,
            "post_shake_soft_covered_by_other": 1,
            "post_shake_priority_covered_by_other": 1,
        }

        result = compare_shake_arms(baseline, rescue)

        self.assertEqual(result["peak_kinetic_energy"], 4.0)
        self.assertAlmostEqual(result["peak_kinetic_energy_per_item"], 0.8)
        self.assertAlmostEqual(result["max_shift"], -0.02)
        self.assertEqual(result["toppled_fraction"], 0.2)
        self.assertEqual(result["post_shake_soft_covered_by_other"], 0.0)
        self.assertEqual(result["post_shake_priority_covered_by_other"], 1.0)
        self.assertNotIn("weighted_score", result)


if __name__ == "__main__":
    unittest.main()
