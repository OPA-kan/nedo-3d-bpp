import unittest

from scripts.evaluate_self_play_policy_bootstrap import evaluate


def row(group, preferred_x):
    candidates = []
    for index, x in enumerate((-1.0, 1.0)):
        candidates.append({
            "candidate_id": str(index),
            "command_action": {
                "item_idx": index, "container_idx": 0,
                "place_pos": [x, 0.0, 0.0], "orientation": 0,
            },
            "visits": 9 if x == preferred_x else 1,
            "probability": 0.9 if x == preferred_x else 0.1,
            "search_q": None,
        })
    return {
        "trajectory_group": group,
        "policy_target_eligible": True,
        "policy_target": candidates,
        "game_features": {
            "player_to_move": 0, "block_length": 0, "handoff_count": 0,
        },
        "state": {
            "container_count": 1, "packed_item_count": 0,
            "visible_item_count": 2,
            "container_features": [
                "length", "width", "height", "cut_x", "cut_y",
                "thickness", "buffer", "shelf", "priority",
            ],
            "container_values": [[2, 1, 1, 0, 0, 0, 0, 0, 0]],
            "packed_item_features": ["container", "x", "y", "z"],
            "packed_item_values": [],
            "visible_item_features": ["length"],
            "visible_item_indices": [0, 1],
            "visible_item_values": [[1.0], [1.0]],
        },
    }


class SelfPlayPolicyBootstrapTests(unittest.TestCase):
    def test_group_holdout_detects_candidate_geometry_signal(self):
        rows = [row(f"g{index}", 1.0) for index in range(4)]

        result = evaluate(rows, alpha=0.01)

        self.assertEqual(result["trajectory_groups"], 4)
        self.assertTrue(result["policy_signal_observed"])
        self.assertGreater(
            result["metrics"]["candidate_geometry_ridge"]["top1_accuracy"],
            0.9,
        )
        self.assertFalse(result["deployment_ready"])


if __name__ == "__main__":
    unittest.main()
