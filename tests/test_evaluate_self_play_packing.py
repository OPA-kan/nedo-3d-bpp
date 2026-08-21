import unittest

from scripts.evaluate_self_play_packing import summarize


class SelfPlayPackingEvaluationTests(unittest.TestCase):
    def test_summary_checks_game_validity_and_state_diversity(self):
        result = summarize({
            "games": [
                {
                    "steps": 7, "handoff_count": 1,
                    "completed_block_lengths": [3],
                    "terminal_reason": "no_retained_candidate",
                    "winner": 1, "rewards": [-50.0, 50.0],
                    "new_attribute_violations": 0,
                    "non_rank0_action_count": 1,
                    "captures": [{
                        "board_fingerprint": "a",
                        "model_visible_state_signature": "x",
                        "game_state_signature": "gx",
                        "is_handoff_state": True,
                    }],
                },
                {
                    "steps": 8, "handoff_count": 1,
                    "completed_block_lengths": [4],
                    "terminal_reason": "stream_exhausted",
                    "winner": None, "rewards": [5.0, -5.0],
                    "new_attribute_violations": 1,
                    "non_rank0_action_count": 2,
                    "captures": [{
                        "board_fingerprint": "b",
                        "model_visible_state_signature": "y",
                        "game_state_signature": "gy",
                        "is_handoff_state": False,
                    }],
                },
            ]
        })

        self.assertTrue(result["validity"]["zero_sum"])
        self.assertEqual(result["validity"]["training_eligible_games"], 2)
        self.assertEqual(result["validity"]["outcome_target_eligible_games"], 0)
        self.assertTrue(result["validity"]["minimum_block_respected"])
        self.assertEqual(result["behavior"]["mean_episode_length"], 7.5)
        self.assertEqual(result["distribution"]["unique_board_fingerprints"], 2)
        self.assertEqual(result["distribution"]["unique_game_state_signatures"], 2)
        self.assertEqual(result["distribution"]["captured_decision_states"], 2)
        self.assertEqual(result["distribution"]["captured_handoff_states"], 1)
        self.assertEqual(result["degeneracy"]["selected_action_failure_rate"], 0.0)


if __name__ == "__main__":
    unittest.main()
