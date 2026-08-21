import json
import pathlib
import tempfile
import unittest

from scripts.evaluate_self_play_puct_matrix import markdown, summarize


def game(*, seed, fill, actions, search=False, violations=0):
    records = []
    for step, candidate in enumerate(actions):
        record = {"step": step, "selected_candidate_id": candidate}
        if search:
            record["search"] = {
                "simulations": 12,
                "policy_target": [
                    {"candidate_id": "a", "visits": 7, "q": 0.5},
                    {"candidate_id": "b", "visits": 3, "q": 0.0},
                    {"candidate_id": "c", "visits": 2, "q": -0.5},
                ],
            }
        records.append(record)
    targets = [
        {
            "step": step,
            "policy_target_eligible": step < len(actions),
            "value_target_eligible": True,
        }
        for step in range(len(actions) + 1)
    ]
    return {
        "environment_seed": seed,
        "handoff_seed": 11,
        "policy_seed": 12,
        "terminal_reason": "no_retained_candidate",
        "training_eligible": True,
        "outcome_target_eligible": True,
        "steps": len(actions),
        "placements": len(actions),
        "rewards": [50.0 - 5.0 * violations, -50.0 + 5.0 * violations],
        "new_attribute_violations": violations,
        "records": records,
        "captures": [
            {
                "step": step,
                "model_visible_state_signature": f"model-state-{step}",
            }
            for step in range(len(actions) + 1)
        ],
        "learning_targets": targets,
        "evaluation": {
            "fill_score": fill,
            "terminal_step_metrics": {
                "placed_count": len(actions),
                "fill_percent_proxy": fill + 2.0,
                "com_z": 0.5,
            },
            "shake_response": {"shake_peak_kinetic_energy": 2.0},
        },
    }


class PuctMatrixEvaluationTests(unittest.TestCase):
    def _write_pair(self, root, label, *, seed, rank0_fill, mcts_fill):
        for arm, payload in (
            ("rank0", game(seed=seed, fill=rank0_fill, actions=["a", "b"])),
            ("mcts", game(
                seed=seed, fill=mcts_fill, actions=["a", "c"], search=True,
            )),
        ):
            path = pathlib.Path(root) / label / arm / "manifest.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({
                "case_id": "m-case", "games": [payload],
            }), encoding="utf-8")
        matched_path = pathlib.Path(root) / label / "matched-shake.json"
        matched_path.write_text(json.dumps({
            "matched_placed_count": 2,
            "delta_mcts_minus_rank0": {
                "peak_kinetic_energy": 0.4,
                "peak_kinetic_energy_per_item": 0.2,
                "peak_kinetic_energy_per_mass": 0.1,
                "shifted_fraction": 0.0,
                "toppled_fraction": 0.0,
                "max_shift": 0.01,
                "mean_shift": 0.005,
                "max_rotation_deg": 0.2,
            },
        }), encoding="utf-8")

    def test_aggregates_paired_deltas_search_signal_and_target_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            self._write_pair(
                directory, "case-seed-42", seed=42,
                rank0_fill=9.0, mcts_fill=10.0,
            )
            self._write_pair(
                directory, "case-seed-137", seed=137,
                rank0_fill=10.0, mcts_fill=9.5,
            )

            result = summarize(pathlib.Path(directory))

        self.assertEqual(result["aggregate"]["pair_count"], 2)
        self.assertEqual(result["aggregate"]["unique_rank0_trajectories"], 1)
        self.assertEqual(result["aggregate"]["unique_mcts_trajectories"], 1)
        self.assertEqual(result["aggregate"]["diverged_pairs"], 2)
        self.assertEqual(result["aggregate"]["fill_wins"], 1)
        self.assertEqual(result["aggregate"]["fill_losses"], 1)
        self.assertEqual(
            result["aggregate"]["mean_delta_mcts_minus_rank0"]["fill_score"],
            0.25,
        )
        self.assertEqual(result["aggregate"]["search_decisions"], 4)
        self.assertEqual(result["aggregate"]["search_simulations"], 48)
        self.assertEqual(result["aggregate"]["nonuniform_roots"], 4)
        self.assertEqual(result["aggregate"]["policy_targets"], 4)
        self.assertEqual(result["aggregate"]["value_targets"], 6)
        self.assertEqual(result["aggregate"]["unique_model_visible_states"], 3)
        self.assertEqual(result["aggregate"]["unique_policy_states"], 2)
        self.assertEqual(
            result["aggregate"]["unique_informative_policy_states"], 2,
        )
        self.assertEqual(result["aggregate"]["unique_value_states"], 3)
        self.assertEqual(
            result["aggregate"]["unique_value_discriminating_policy_states"],
            2,
        )
        self.assertEqual(result["aggregate"]["matched_shake_pairs"], 2)
        self.assertEqual(
            result["aggregate"]
            ["matched_shake_mean_delta_mcts_minus_rank0"]
            ["peak_kinetic_energy_per_item"],
            0.2,
        )
        self.assertTrue(result["gates"]["data_contract_ready"])
        self.assertTrue(result["gates"]["policy_contract_ready"])
        self.assertTrue(result["gates"]["value_contract_ready"])
        self.assertTrue(result["gates"]["safety_noninferior"])
        self.assertTrue(result["gates"]["score_improvement_observed"])
        self.assertFalse(result["gates"]["score_improvement_established"])
        self.assertIn("1 / 0 / 1", markdown(result))

    def test_rejects_unpaired_environment_seeds(self):
        with tempfile.TemporaryDirectory() as directory:
            self._write_pair(
                directory, "case-seed-42", seed=42,
                rank0_fill=9.0, mcts_fill=10.0,
            )
            mcts_path = (
                pathlib.Path(directory) / "case-seed-42" / "mcts"
                / "manifest.json"
            )
            manifest = json.loads(mcts_path.read_text(encoding="utf-8"))
            manifest["games"][0]["environment_seed"] = 99
            mcts_path.write_text(json.dumps(manifest), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "environment seed mismatch"):
                summarize(pathlib.Path(directory))

    def test_censored_game_keeps_policy_gate_and_fails_value_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            self._write_pair(
                directory, "case-seed-42", seed=42,
                rank0_fill=9.0, mcts_fill=10.0,
            )
            mcts_path = (
                pathlib.Path(directory) / "case-seed-42" / "mcts"
                / "manifest.json"
            )
            manifest = json.loads(mcts_path.read_text(encoding="utf-8"))
            item = manifest["games"][0]
            item["terminal_reason"] = "max_steps"
            item["outcome_target_eligible"] = False
            for target in item["learning_targets"]:
                target["value_target_eligible"] = False
            mcts_path.write_text(json.dumps(manifest), encoding="utf-8")

            result = summarize(pathlib.Path(directory))

        self.assertTrue(result["gates"]["policy_contract_ready"])
        self.assertFalse(result["gates"]["value_contract_ready"])
        self.assertFalse(result["gates"]["data_contract_ready"])


if __name__ == "__main__":
    unittest.main()
