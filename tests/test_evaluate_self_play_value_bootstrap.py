import unittest

from scripts.evaluate_self_play_value_bootstrap import evaluate


def row(group, packed, target):
    return {
        "trajectory_group": group,
        "value_target_eligible": True,
        "return_to_go": target,
        "game_features": {
            "player_to_move": 0, "block_length": 0, "handoff_count": 0,
        },
        "state": {
            "container_count": 1, "packed_item_count": 1,
            "visible_item_count": 1,
            "container_features": ["length"],
            "container_values": [[1.0]],
            "packed_item_features": ["signal"],
            "packed_item_values": [[packed]],
            "visible_item_features": ["mass"],
            "visible_item_values": [[1.0]],
        },
    }


class SelfPlayValueBootstrapTests(unittest.TestCase):
    def test_group_holdout_detects_board_signal(self):
        rows = [
            row(f"g{index}", value, 10.0 * value)
            for index, value in enumerate((-2.0, -1.0, 1.0, 2.0))
        ]

        result = evaluate(rows, alpha=0.01)

        self.assertEqual(result["trajectory_groups"], 4)
        self.assertTrue(result["board_signal_observed"])
        self.assertLess(
            result["metrics"]["board_set_summary_ridge"]["rmse"],
            result["metrics"]["phase_count_ridge"]["rmse"],
        )
        self.assertFalse(result["deployment_ready"])


if __name__ == "__main__":
    unittest.main()
