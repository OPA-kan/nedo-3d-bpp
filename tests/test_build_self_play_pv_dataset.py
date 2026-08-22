import json
import pathlib
import tempfile
import unittest

from scripts.build_self_play_pv_dataset import build_rows


class SelfPlayPvDatasetTests(unittest.TestCase):
    def test_builds_geometry_pi_and_return_without_ranker_leakage(self):
        with tempfile.TemporaryDirectory() as directory:
            mcts = pathlib.Path(directory) / "pair" / "mcts"
            game_dir = mcts / "game-000"
            game_dir.mkdir(parents=True)
            snapshot = {
                "observation": {
                    "container_list": [{
                        "index": 0, "center": [0, 0, 0], "length": 2,
                        "width": 1, "height": 1, "packed_items": [],
                    }],
                    "pool_list": [{
                        "index": 7, "length": 0.5, "width": 0.4,
                        "height": 0.3, "mass": 2,
                    }],
                },
                "physics": {"packed_items": []},
                "self_play_game": {"block_length": 2, "handoff_count": 1},
            }
            (game_dir / "step-000-state.json").write_text(
                json.dumps(snapshot), encoding="utf-8"
            )
            candidate_set = [{
                "candidate_id": "a",
                "command_action": {
                    "item_idx": 7, "container_idx": 0,
                    "place_pos": [0.1, 0.2, 0.3], "orientation": 1,
                },
                "selection": {"rank": 0, "score": 999.0},
            }]
            manifest = {
                "case_id": "m-case", "policy_generation": "pi0-puct0",
                "games": [{
                    "trajectory_id": "trajectory-1",
                    "records": [{
                        "step": 0,
                        "candidate_set": candidate_set,
                        "search": {
                            "multi_head_branch_samples": [{
                                "root_candidate_id": "a",
                                "termination": "horizon",
                                "relative_action_prefix": [
                                    candidate_set[0]["command_action"]
                                ],
                                "leaf_model_visible_state_signature": "leaf-1",
                                "leaf_state": snapshot,
                                "replay_contract": {
                                    "future_stream_id": "stream-1",
                                    "action_prefix_id": "prefix-1",
                                },
                                "heads": {
                                    "fill_gain": {
                                        "value": 2.5,
                                        "target_eligible": True,
                                        "censor_reason": None,
                                    }
                                },
                            }]
                        },
                    }],
                    "captures": [{
                        "step": 0, "snapshot_path": "step-000-state.json",
                        "model_visible_state_signature": "model-1",
                        "game_state_signature": "game-1",
                    }],
                    "learning_targets": [{
                        "step": 0, "player_to_move": 1,
                        "policy_target_eligible": True,
                        "policy_target": [{
                            "candidate_id": "a", "rank": 0,
                            "prior": 0.9, "visits": 12,
                            "probability": 1.0, "q": 0.4,
                            "multi_head_target": {
                                "schema_version": 1,
                                "samples": 12,
                                "complete_samples": 8,
                                "censored_samples": 4,
                                "heads": {
                                    "fill_gain": {
                                        "eligible_count": 8,
                                        "censored_count": 4,
                                        "mean": 2.5,
                                        "min": 1.0,
                                        "max": 4.0,
                                        "objective": "maximize",
                                    }
                                },
                            },
                        }],
                        "value_target_eligible": True,
                        "return_to_go": -45.0,
                        "value_heads": {
                            "fill_return": {
                                "value": 7.0,
                                "target_eligible": True,
                                "censor_reason": None,
                            }
                        },
                    }],
                }],
            }
            (mcts / "manifest.json").write_text(
                json.dumps(manifest), encoding="utf-8"
            )

            rows, summary = build_rows(pathlib.Path(directory))

        self.assertEqual(summary["trajectory_groups"], 1)
        self.assertEqual(summary["policy_rows"], 1)
        self.assertEqual(summary["value_rows"], 1)
        self.assertEqual(summary["forbidden_heuristic_key_hits"], 0)
        self.assertEqual(rows[0]["return_to_go"], -45.0)
        self.assertEqual(rows[0]["value_heads"]["fill_return"]["value"], 7.0)
        branch_target = rows[0]["policy_target"][0]["multi_head_target"]
        self.assertEqual(branch_target["complete_samples"], 8)
        self.assertEqual(branch_target["heads"]["fill_gain"]["mean"], 2.5)
        self.assertEqual(summary["multi_head_policy_rows"], 1)
        self.assertEqual(summary["multi_head_branch_samples"], 1)
        self.assertEqual(
            rows[0]["bounded_branch_outcomes"][0][
                "leaf_model_visible_state_signature"
            ],
            "leaf-1",
        )
        self.assertNotIn("selection", json.dumps(rows[0]))
        self.assertNotIn('"prior"', json.dumps(rows[0]))
        self.assertNotIn('"rank"', json.dumps(rows[0]))


if __name__ == "__main__":
    unittest.main()
