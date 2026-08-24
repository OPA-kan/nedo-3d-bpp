import pathlib
import tempfile
import unittest
from unittest import mock

from scripts.run_terminal_rollout_policy import (
    choose_root_candidate,
    run_episode,
)


def candidate(name, rank):
    return {
        "candidate_id": name,
        "command_action": {
            "item_idx": rank,
            "container_idx": 0,
            "place_pos": [0.0, 0.0, 0.0],
            "orientation": 0,
        },
        "selection": {"rank": rank, "stable_item_index": rank},
        "proposal_provenance": {"source": "test"},
    }


def search_result(*, frontier, complete=True, safe=("a", "b", "c")):
    return {
        "terminal_truth_complete": complete,
        "terminal_pareto_candidates": list(frontier),
        "root_candidates": [
            {"root_candidate_id": name, "safe": name in safe}
            for name in ("a", "b", "c")
        ],
    }


class TerminalRolloutPolicyTests(unittest.TestCase):
    def setUp(self):
        self.candidates = [
            candidate("a", 0), candidate("b", 1), candidate("c", 2)
        ]

    def test_legacy_mode_keeps_lowest_rank_safe_candidate(self):
        chosen, audit = choose_root_candidate(
            self.candidates,
            search_result(frontier=["c"], safe=("b", "c")),
            policy="legacy",
        )

        self.assertEqual(chosen["candidate_id"], "b")
        self.assertEqual(audit["reason"], "legacy_rank0")

    def test_rollout_switches_only_when_incumbent_is_dominated(self):
        chosen, audit = choose_root_candidate(
            self.candidates,
            search_result(frontier=["b", "c"]),
            policy="terminal-rollout",
        )

        self.assertEqual(chosen["candidate_id"], "b")
        self.assertEqual(audit["reason"], "terminal_dominance_switch")
        self.assertTrue(audit["switched"])

    def test_rollout_keeps_incumbent_when_it_is_terminal_pareto(self):
        chosen, audit = choose_root_candidate(
            self.candidates,
            search_result(frontier=["a", "c"]),
            policy="terminal-rollout",
        )

        self.assertEqual(chosen["candidate_id"], "a")
        self.assertEqual(audit["reason"], "incumbent_terminal_pareto")
        self.assertFalse(audit["switched"])

    def test_rollout_fails_safe_when_terminal_truth_is_censored(self):
        chosen, audit = choose_root_candidate(
            self.candidates,
            search_result(frontier=["b"], complete=False),
            policy="terminal-rollout",
        )

        self.assertEqual(chosen["candidate_id"], "a")
        self.assertEqual(audit["reason"], "terminal_truth_censored")

    def test_no_safe_candidate_returns_none(self):
        chosen, audit = choose_root_candidate(
            self.candidates,
            search_result(frontier=[], safe=()),
            policy="terminal-rollout",
        )

        self.assertIsNone(chosen)
        self.assertEqual(audit["reason"], "no_safe_candidate")

    @mock.patch(
        "scripts.run_terminal_rollout_policy.item_symmetry_board_fingerprint",
        return_value="symmetry",
    )
    @mock.patch(
        "scripts.run_terminal_rollout_policy.policy_observation",
        side_effect=lambda _env, observation: observation,
    )
    @mock.patch(
        "scripts.run_terminal_rollout_policy.board_fingerprint",
        return_value="exact",
    )
    @mock.patch(
        "scripts.run_terminal_rollout_policy.state_snapshot",
        return_value={},
    )
    @mock.patch("scripts.run_terminal_rollout_policy.cumulative_metrics")
    @mock.patch("scripts.run_terminal_rollout_policy.vector_search_root")
    @mock.patch("scripts.run_terminal_rollout_policy.build_candidate_provider")
    @mock.patch("scripts.run_terminal_rollout_policy._fresh_env")
    def test_episode_executes_a_proven_terminal_dominance_switch(
        self, fresh_env, provider_builder, vector_search, metrics,
        _snapshot, _exact, _policy_observation, _symmetry,
    ):
        class Env:
            def __init__(self):
                self.actions = []

            def reset_settings(self):
                pass

            def reset_item_stream(self):
                pass

            def reset(self, seed):
                return {}, {}

            def step(self, action):
                self.actions.append(action)
                return {}, 0.0, True, False, {
                    "status": {
                        "is_included": True,
                        "is_valid": True,
                        "is_placed_safe": True,
                    }
                }

            def evaluate(self):
                return {"shake_response": {}}

            def close(self):
                pass

        env = Env()
        fresh_env.return_value = env
        provider_builder.return_value = lambda *_args: self.candidates
        vector_search.return_value = {
            **search_result(frontier=["b"]),
            "leaf_eval": "rollout",
            "physical_steps": 3,
            "terminal_rollout_physical_steps": 12,
            "physical_step_equivalents": 6,
            "terminal_rollout_physical_step_equivalents": 30,
            "terminal_rollout_legal_filter_symmetry_reused": 4,
            "item_symmetry_cache_shadow": {},
            "item_symmetry_terminal_cache": {
                "hits": 1,
                "saved_physical_steps": 4,
                "saved_physical_step_equivalents": 10,
            },
        }
        metrics.side_effect = [
            {"fill_score_proxy": 0.0},
            {"fill_score_proxy": 5.0},
        ]

        with tempfile.TemporaryDirectory() as tmp:
            episode = run_episode(
                object(), {}, case_id="case", environment_seed=42,
                attempt_budget=1, top_k=3, rollout_top_k=3,
                rollout_max_steps=10, max_steps=1,
                policy="terminal-rollout", output_dir=pathlib.Path(tmp),
            )

        self.assertEqual(env.actions[0]["item_idx"], 1)
        self.assertEqual(episode["terminal_dominance_switches"], 1)
        self.assertEqual(episode["terminal_rollout_physical_steps"], 12)
        self.assertEqual(episode["terminal_symmetry_cache_hits"], 1)
        self.assertEqual(
            episode[
                "terminal_symmetry_cache_saved_physical_step_equivalents"
            ],
            10,
        )
        self.assertEqual(
            episode["terminal_rollout_legal_filter_symmetry_reused"], 4
        )
        self.assertTrue(vector_search.call_args.kwargs[
            "item_symmetry_terminal_cache"
        ])
        timing = episode["records"][0]["timing"]
        self.assertEqual(timing["contract"], "decision_wall_clock_v1")
        for phase in (
            "state_capture_seconds", "provider_seconds", "search_seconds",
            "selection_seconds", "live_action_seconds",
            "decision_total_seconds",
        ):
            self.assertGreaterEqual(timing[phase], 0.0)
        self.assertIn("timing", episode["records"][0]["search"])
        self.assertEqual(episode["termination"], "stream_exhausted")


if __name__ == "__main__":
    unittest.main()
