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
                    "candidate_proposals": 10,
                    "legal_candidates": 8,
                    "prefilter_rejections": 2,
                    "records": [{
                        "search": {
                            "simulations": 4, "expanded_nodes": 3,
                            "search_prefilter_rejections": 1,
                            "policy_target": [
                                {"probability": 0.75}, {"probability": 0.25},
                            ],
                        },
                    }],
                    "learning_targets": [{
                        "policy_target_eligible": True,
                        "value_target_eligible": True,
                    }],
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
                    "candidate_proposals": 12,
                    "legal_candidates": 11,
                    "prefilter_rejections": 1,
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
        self.assertEqual(result["degeneracy"]["candidate_proposals"], 22)
        self.assertEqual(result["degeneracy"]["legal_candidates"], 19)
        self.assertEqual(result["degeneracy"]["prefilter_rejections"], 3)
        self.assertAlmostEqual(
            result["degeneracy"]["proposal_rejection_rate"], 3 / 22
        )
        self.assertEqual(result["learning"]["search_decisions"], 1)
        self.assertEqual(result["learning"]["search_simulations"], 4)
        self.assertEqual(result["learning"]["expanded_search_nodes"], 3)
        self.assertEqual(result["learning"]["policy_targets"], 1)
        self.assertEqual(result["learning"]["value_targets"], 1)


if __name__ == "__main__":
    unittest.main()
