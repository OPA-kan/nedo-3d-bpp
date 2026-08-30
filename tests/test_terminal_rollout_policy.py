import pathlib
import tempfile
import unittest
from unittest import mock

from scripts.run_terminal_rollout_policy import (
    add_exact_agent_candidate,
    add_current_agent_candidate,
    choose_root_candidate,
    exact_agent_action,
    pair_fork_winner,
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

    def test_current_agent_executes_its_exact_action_even_outside_safe_union(self):
        exact = candidate("exact", 99)
        chosen, audit = choose_root_candidate(
            self.candidates + [exact],
            search_result(frontier=[], safe=("a", "b", "c")),
            policy="current-agent",
            forced_candidate_id="exact",
        )

        self.assertEqual(chosen["candidate_id"], "exact")
        self.assertEqual(audit["reason"], "current_agent_policy")
        self.assertFalse(audit["selected_safe"])

    def test_current_agent_action_is_union_added_and_deduplicated(self):
        observation = {"pool_list": [{"index": 70}]}
        exact = {
            "item_idx": 0, "container_idx": 0,
            "place_pos": [0.5, 0.25, 0.75], "orientation": 1,
        }
        expanded, candidate_id, hit = add_current_agent_candidate(
            self.candidates, exact, observation,
        )
        self.assertFalse(hit)
        self.assertEqual(len(expanded), len(self.candidates) + 1)
        self.assertEqual(expanded[-1].candidate_id, candidate_id)
        self.assertEqual(
            expanded[-1].selection["provider"],
            "exact_current_agent_policy",
        )
        repeated, repeated_id, repeated_hit = add_current_agent_candidate(
            expanded, exact, observation,
        )
        self.assertTrue(repeated_hit)
        self.assertEqual(repeated_id, candidate_id)
        self.assertEqual(len(repeated), len(expanded))

    def test_exact_agent_decline_is_preserved_instead_of_canonicalized(self):
        solver = mock.Mock()
        solver.policy.return_value = None

        self.assertIsNone(exact_agent_action(solver, {"state": 1}))
        solver.policy.assert_called_once_with({"state": 1})

    def test_rule_alpha_action_is_union_added_with_distinct_provenance(self):
        observation = {"pool_list": [{"index": 70}]}
        exact = {
            "item_idx": 0, "container_idx": 0,
            "place_pos": [0.5, 0.25, 0.75], "orientation": 1,
        }
        expanded, candidate_id, hit = add_exact_agent_candidate(
            self.candidates, exact, observation, policy="rule-alpha",
        )
        self.assertFalse(hit)
        self.assertEqual(expanded[-1].candidate_id, candidate_id)
        self.assertEqual(
            expanded[-1].selection["provider"],
            "exact_rule_alpha_policy",
        )

        chosen, audit = choose_root_candidate(
            expanded,
            {
                "root_candidates": [
                    {"root_candidate_id": "a", "safe": True},
                    {"root_candidate_id": candidate_id, "safe": True},
                ]
            },
            policy="rule-alpha", forced_candidate_id=candidate_id,
        )
        self.assertEqual(chosen.candidate_id, candidate_id)
        self.assertEqual(audit["reason"], "rule_alpha_policy")

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

    def test_learned_mode_executes_the_ensemble_argmax(self):
        seen = {}

        def scorer(incumbent_id):
            seen["incumbent"] = incumbent_id
            return {"a": 0.2, "b": 0.7, "c": 0.1}

        chosen, audit = choose_root_candidate(
            self.candidates,
            search_result(frontier=[]),
            policy="learned",
            learned_scorer=scorer,
        )

        self.assertEqual(seen["incumbent"], "a")
        self.assertEqual(chosen["candidate_id"], "b")
        self.assertEqual(audit["reason"], "learned_argmax_switch")
        self.assertTrue(audit["switched"])
        self.assertEqual(audit["learned_scores"]["b"], 0.7)

    def test_learned_mode_keeps_incumbent_when_it_scores_highest(self):
        chosen, audit = choose_root_candidate(
            self.candidates,
            search_result(frontier=[]),
            policy="learned",
            learned_scorer=lambda _incumbent: {"a": 0.9, "b": 0.05, "c": 0.05},
        )

        self.assertEqual(chosen["candidate_id"], "a")
        self.assertEqual(audit["reason"], "learned_argmax_keep_incumbent")
        self.assertFalse(audit["switched"])

    def test_learned_mode_fails_safe_to_incumbent_without_scores(self):
        chosen, audit = choose_root_candidate(
            self.candidates,
            search_result(frontier=[]),
            policy="learned",
            learned_scorer=lambda _incumbent: {},
        )

        self.assertEqual(chosen["candidate_id"], "a")
        self.assertEqual(audit["reason"], "learned_scores_missing")
        self.assertFalse(audit["switched"])

    def test_learned_mode_requires_a_scorer(self):
        with self.assertRaises(ValueError):
            choose_root_candidate(
                self.candidates,
                search_result(frontier=[]),
                policy="learned",
            )

    def test_learned_mode_only_considers_safe_candidates(self):
        chosen, audit = choose_root_candidate(
            self.candidates,
            search_result(frontier=[], safe=("a", "c")),
            policy="learned",
            learned_scorer=lambda _incumbent: {
                "a": 0.2, "b": 0.9, "c": 0.4,
            },
        )

        self.assertEqual(chosen["candidate_id"], "c")
        self.assertEqual(audit["reason"], "learned_argmax_switch")

    def test_online_mode_scores_like_learned_and_requires_a_scorer(self):
        chosen, audit = choose_root_candidate(
            self.candidates,
            search_result(frontier=[]),
            policy="online",
            learned_scorer=lambda _incumbent: {"a": 0.2, "b": 0.7, "c": 0.1},
        )
        self.assertEqual(chosen["candidate_id"], "b")
        self.assertEqual(audit["reason"], "learned_argmax_switch")
        with self.assertRaises(ValueError):
            choose_root_candidate(
                self.candidates, search_result(frontier=[]), policy="online",
            )

    def _rule_candidates(self):
        rows = []
        cands = []
        for name, rank, pos, orientation, com, fill in (
            # a: off-grid, central, low CoM delta
            ("a", 0, [0.11, 0.07, 0.5], 1, 0.10, 0.5),
            # b: exactly on the 0.25 lattice, mid-distance, high CoM
            ("b", 1, [0.25, -0.50, 0.5], 0, 0.90, 0.5),
            # c: far corner hugger, mid CoM
            ("c", 2, [0.95, 0.90, 0.5], 1, 0.40, 0.5),
        ):
            row = candidate(name, rank)
            row["command_action"]["place_pos"] = pos
            row["command_action"]["orientation"] = orientation
            cands.append(row)
            rows.append({
                "root_candidate_id": name, "safe": True,
                "one_step_vector": {
                    "center_of_mass_z_delta": com, "fill_gain": fill,
                    "soft_violation_gain": 0.0,
                    "priority_covered_gain": 0.0,
                    "priority_misrouted_gain": 0.0,
                },
            })
        return cands, {"root_candidates": rows}

    def test_rule_grid_snaps_to_the_lattice(self):
        cands, search = self._rule_candidates()
        chosen, audit = choose_root_candidate(
            cands, search, policy="rule-grid",
        )
        self.assertEqual(chosen["candidate_id"], "b")
        self.assertEqual(audit["reason"], "rule_heuristic_argmin")

    def test_rule_lowcog_minimizes_center_of_mass_delta(self):
        cands, search = self._rule_candidates()
        chosen, _audit = choose_root_candidate(
            cands, search, policy="rule-lowcog",
        )
        self.assertEqual(chosen["candidate_id"], "a")

    def test_rule_edge_hugs_the_perimeter(self):
        cands, search = self._rule_candidates()
        chosen, _audit = choose_root_candidate(
            cands, search, policy="rule-edge",
        )
        self.assertEqual(chosen["candidate_id"], "c")

    def test_rule_heuristics_break_ties_away_from_violations(self):
        from scripts.run_terminal_rollout_policy import rule_heuristic_key

        action = {"place_pos": [0.25, 0.25, 0.5], "orientation": 0}
        clean = rule_heuristic_key(
            "rule-grid", action,
            {"center_of_mass_z_delta": 0.5, "fill_gain": 0.5,
             "soft_violation_gain": 0.0},
        )
        dirty = rule_heuristic_key(
            "rule-grid", action,
            {"center_of_mass_z_delta": 0.5, "fill_gain": 0.5,
             "soft_violation_gain": 1.0},
        )
        self.assertLess(clean, dirty)

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
    def test_episode_executes_stateful_exact_current_agent_action(
        self, fresh_env, provider_builder, vector_search, metrics,
        _snapshot, _exact, _policy_observation, _symmetry,
    ):
        exact_action = {
            "item_idx": 0, "container_idx": 0,
            "place_pos": [0.5, 0.25, 0.75], "orientation": 1,
        }

        class Solver:
            initialized = False

            def __init__(self, _module_path):
                pass

            def get_init_states(self, init_states):
                self.initialized = init_states == {"containers": 1}

            def policy(self, _observation):
                if not self.initialized:
                    raise AssertionError("current agent was not initialized")
                return exact_action

        class AgentModule:
            Agent = Solver

        class Env:
            def __init__(self):
                self.actions = []

            def reset_settings(self):
                pass

            def get_init_states(self):
                return {"containers": 1}

            def reset_item_stream(self):
                pass

            def reset(self, seed):
                return {"pool_list": [{"index": 70}]}, {}

            def step(self, action):
                self.actions.append(action)
                return {}, 0.0, True, False, {"status": {
                    "is_included": True,
                    "is_valid": True,
                    "is_placed_safe": True,
                }}

            def evaluate(self):
                return {"shake_response": {}}

            def close(self):
                pass

        env = Env()
        fresh_env.return_value = env
        provider_builder.return_value = lambda *_args: [self.candidates[0]]

        def measured_root(*_args, root_candidates, **_kwargs):
            rows = [
                {
                    "root_candidate_id": (
                        row["candidate_id"] if isinstance(row, dict)
                        else row.candidate_id
                    ),
                    "safe": True,
                }
                for row in root_candidates
            ]
            return {
                "root_candidates": rows,
                "terminal_truth_complete": False,
                "terminal_pareto_candidates": [],
                "leaf_eval": "measured",
                "physical_steps": len(rows),
                "terminal_rollout_physical_steps": 0,
                "physical_step_equivalents": len(rows),
                "terminal_rollout_physical_step_equivalents": 0,
                "terminal_rollout_legal_filter_symmetry_reused": 0,
                "item_symmetry_cache_shadow": {},
                "item_symmetry_terminal_cache": {},
            }

        vector_search.side_effect = measured_root
        metrics.side_effect = [
            {"fill_score_proxy": 0.0},
            {"fill_score_proxy": 1.0},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            episode = run_episode(
                AgentModule, {}, case_id="case", environment_seed=42,
                attempt_budget=1, top_k=3, rollout_top_k=3,
                rollout_max_steps=10, max_steps=1,
                policy="current-agent", output_dir=pathlib.Path(tmp),
            )

        self.assertEqual(env.actions, [exact_action])
        self.assertEqual(episode["current_agent_support_misses"], 1)
        self.assertEqual(
            episode["records"][0]["selection"]["reason"],
            "current_agent_policy",
        )


class PairForkWinnerTests(unittest.TestCase):
    """A pair verdict needs BOTH sides to have reached a genuine terminal."""

    PAIR = {"actor", "champ"}

    def fork(self, **overrides):
        base = {
            "terminal_truth_complete": True,
            "terminal_eligible_candidates": ["actor", "champ"],
            "terminal_pareto_candidates": ["actor"],
        }
        base.update(overrides)
        return base

    def test_strict_winner_is_read_when_both_sides_are_eligible(self):
        self.assertEqual(pair_fork_winner(self.fork(), self.PAIR), "actor")

    def test_one_horse_race_is_not_a_verdict(self):
        """The Cup 006 rule-alpha defect, at its source.

        build_resurrection_audit builds its comparison set from
        physically SAFE root candidates, so a side whose action turns out
        unsafe inside the fork leaves the set instead of being censored:
        the survivor stands alone on a one-candidate frontier and
        terminal_truth_complete stays True. Reading a winner off that
        scored a one-horse race as strict dominance.
        """
        self.assertIsNone(pair_fork_winner(self.fork(
            terminal_eligible_candidates=["champ"],
            terminal_pareto_candidates=["champ"],
        ), self.PAIR))

    def test_censored_truth_is_not_a_verdict(self):
        self.assertIsNone(pair_fork_winner(
            self.fork(terminal_truth_complete=False), self.PAIR
        ))

    def test_a_tied_frontier_is_not_a_verdict(self):
        self.assertIsNone(pair_fork_winner(
            self.fork(terminal_pareto_candidates=["actor", "champ"]),
            self.PAIR,
        ))

    def test_a_winner_outside_the_pair_is_rejected(self):
        self.assertIsNone(pair_fork_winner(self.fork(
            terminal_eligible_candidates=["actor", "champ", "other"],
            terminal_pareto_candidates=["other"],
        ), self.PAIR))


if __name__ == "__main__":
    unittest.main()
