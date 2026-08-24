import json
import pathlib
import tempfile
import unittest

from scripts.build_single_agent_value_dataset import build_rows


def _leaf(value):
    return {
        "container_features": ["length"], "container_values": [[2.0]],
        "packed_item_features": ["mass"], "packed_item_values": [[value]],
        "visible_item_features": ["mass"], "visible_item_values": [[1.0]],
    }


class SingleAgentValueDatasetTests(unittest.TestCase):
    def test_recovers_next_played_state_without_game_or_ranker_features(self):
        with tempfile.TemporaryDirectory() as directory:
            cell = pathlib.Path(directory) / "cell-a"
            cell.mkdir()
            records = []
            targets = []
            for step in range(3):
                records.append({
                    "step": step, "selected_candidate_id": f"a{step}",
                    "measurement_samples": [{
                        "root_candidate_id": f"a{step}", "physical_safe": True,
                        "leaf_state": _leaf(step + 1),
                    }],
                })
                targets.append({
                    "step": step,
                    "value_target_semantics": "V^pi_behavior_observed_suffix_not_V_star",
                    "value_target_eligible": True,
                    "value_heads": {"fill_return": {
                        "value": 3 - step, "target_eligible": True,
                    }},
                })
            (cell / "manifest.json").write_text(json.dumps({
                "behavior_contract": "single_agent_v1", "case_id": "m-a",
                "environment_seed": 42, "episodes": [{
                    "behavior_contract": "single_agent_v1",
                    "records": records, "value_targets": targets,
                }],
            }), encoding="utf-8")

            rows, summary = build_rows(pathlib.Path(directory))

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["step"], 1)
        self.assertEqual(rows[0]["state"]["packed_item_values"], [[1]])
        self.assertNotIn("game_features", rows[0])
        self.assertNotIn("return_to_go", rows[0])
        self.assertEqual(summary["initial_states_omitted"], 1)
        self.assertEqual(summary["forbidden_heuristic_key_hits"], 0)

    def test_rejects_selected_action_without_safe_leaf_state(self):
        with tempfile.TemporaryDirectory() as directory:
            cell = pathlib.Path(directory) / "cell-a"
            cell.mkdir()
            (cell / "manifest.json").write_text(json.dumps({
                "behavior_contract": "single_agent_v1", "episodes": [{
                    "behavior_contract": "single_agent_v1",
                    "records": [{
                        "step": 0, "selected_candidate_id": "a",
                        "measurement_samples": [],
                    }],
                    "value_targets": [{"step": 0}],
                }],
            }), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "no safe leaf state"):
                build_rows(pathlib.Path(directory))


if __name__ == "__main__":
    unittest.main()
