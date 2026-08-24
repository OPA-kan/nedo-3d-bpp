import unittest
from unittest import mock

from scripts.run_vector_mcts import (
    _accumulate,
    _dominates,
    _new_edge_stat,
    _oriented,
    _output_contract,
    _pareto_puct_choice,
    _terminal_rollout,
    _update_edge_stat,
    build_resurrection_audit,
    compose_leaf_value,
    pareto_frontier,
    summarize_resurrection_audits,
    vector_search_root,
)
from scripts.beta_proposal import stratum_entropy


def vector(fill, soft=0.0, pc=0.0, pm=0.0, tv=0.0):
    return {
        "fill_gain": fill,
        "soft_violation_gain": soft,
        "priority_covered_gain": pc,
        "priority_misrouted_gain": pm,
        "surface_total_variation_delta": tv,
    }


class VectorSearchPrimitiveTests(unittest.TestCase):
    def test_terminal_audit_contract_is_separate_from_teacher_and_oracle_guidance(self):
        self.assertEqual(
            _output_contract("measured", terminal_audit=True),
            (
                3, "pareto_search_terminal_audit_v3",
                "terminal_frontier_resurrection_v1",
            ),
        )
        self.assertEqual(
            _output_contract("measured", allocation="pareto-puct"),
            (2, "vector_pareto_puct_search_v1", None),
        )
        self.assertEqual(
            _output_contract(
                "value", terminal_audit=True, allocation="pareto-puct"
            ),
            (
                4, "pareto_puct_value_terminal_audit_v4",
                "terminal_frontier_resurrection_v1",
            ),
        )

    def test_rollout_oracle_cannot_masquerade_as_legacy_search_teacher(self):
        self.assertEqual(
            _output_contract("measured"),
            (1, "vector_mcts_search_pareto_v1", None),
        )
        self.assertEqual(
            _output_contract("rollout"),
            (
                2, "pareto_tree_search_terminal_oracle_v2",
                "terminal_frontier_resurrection_v1",
            ),
        )

    def test_orientation_flips_minimize_heads(self):
        oriented = _oriented(vector(2.0, soft=1.0))
        self.assertEqual(oriented[0], 2.0)
        self.assertEqual(oriented[1], -1.0)
        self.assertIsNone(_oriented({"fill_gain": 1.0}))

    def test_dominance_and_frontier_are_weight_free(self):
        vectors = {
            "a": _oriented(vector(3.0, soft=0.0)),
            "b": _oriented(vector(1.0, soft=0.0)),   # dominated by a
            "c": _oriented(vector(2.0, soft=-1.0)),  # tradeoff: on frontier
        }
        self.assertTrue(_dominates(vectors["a"], vectors["b"]))
        self.assertFalse(_dominates(vectors["a"], vectors["c"]))
        self.assertEqual(pareto_frontier(vectors), {"a", "c"})

    def test_accumulate_is_additive_and_censors_none(self):
        base = {"fill_gain": 1.0, "soft_violation_gain": 0.0}
        delta = {
            "fill_gain": {"value": 2.0},
            "soft_violation_gain": {"value": None},
        }
        accumulated = _accumulate(base, delta)
        self.assertEqual(accumulated["fill_gain"], 3.0)
        self.assertIsNone(accumulated["soft_violation_gain"])

    def test_leaf_value_composition_respects_head_semantics(self):
        result = compose_leaf_value(
            {
                "fill_gain": 2.0, "placed_gain": 1.0,
                "soft_violation_gain": 0.0,
                "priority_covered_gain": 1.0,
                "priority_misrouted_gain": 0.0,
                "center_of_mass_z_delta": 0.2,
                "surface_total_variation_delta": 0.3,
            },
            {
                "fill_return": {"mean": 5.0},
                "placed_return": {"mean": 3.0},
                "soft_violation_return": {"mean": 1.0},
                "priority_covered_return": {"mean": 0.0},
                "priority_misrouted_return": {"mean": 2.0},
                "center_of_mass_z_return": {"mean": -0.1},
                "surface_total_variation_return": {"mean": 0.4},
                "stream_completed": {"mean": 0.75},
                "terminal_stability_max_shift": {"mean": 0.08},
            },
        )

        self.assertEqual(result["fill_gain"], 7.0)
        self.assertEqual(result["placed_gain"], 4.0)
        self.assertEqual(result["soft_violation_gain"], 1.0)
        self.assertAlmostEqual(result["center_of_mass_z_delta"], 0.1)
        self.assertEqual(result["surface_total_variation_delta"], 0.7)
        self.assertEqual(result["stream_completed_probability"], 0.75)
        self.assertEqual(result["terminal_stability_max_shift"], 0.08)

    def test_value_leaf_requires_puct_and_an_adapter(self):
        common = dict(
            agent_module=object(), task_config={}, case_id="m-test",
            environment_seed=1, prefix_actions=[], root_candidates=[{}],
            attempt_budget=1, deep_top_k=1, expansions=0, max_depth=2,
            step=0, leaf_eval="value",
        )
        with self.assertRaisesRegex(ValueError, "Pareto-PUCT"):
            vector_search_root(**common, allocation="frontier")
        with self.assertRaisesRegex(ValueError, "leaf_vector_fn"):
            vector_search_root(**common, allocation="pareto-puct")

    def test_leaf_value_abstains_when_oof_head_loses_to_constant(self):
        result = compose_leaf_value(
            vector(2.0),
            {
                "fill_return": {
                    "mean": 9.0, "oof_inference_eligible": True,
                },
                "soft_violation_return": {
                    "mean": 7.0, "oof_inference_eligible": False,
                },
                "priority_covered_return": {
                    "mean": 5.0, "oof_inference_eligible": False,
                },
                "priority_misrouted_return": {
                    "mean": 4.0, "oof_inference_eligible": False,
                },
                "surface_total_variation_return": {
                    "mean": 0.5, "oof_inference_eligible": True,
                },
            },
        )
        self.assertEqual(result["fill_gain"], 11.0)
        self.assertEqual(result["soft_violation_gain"], 0.0)
        self.assertEqual(result["priority_covered_gain"], 0.0)
        self.assertEqual(result["surface_total_variation_delta"], 0.5)

    def test_resurrection_audit_separates_truth_frontier_and_expansion(self):
        nodes = {
            "a-root": {
                "root_candidate_id": "a", "depth": 1,
                "vector": vector(3.0),
                "evaluation_vector": vector(4.0),
                "terminal_vector": vector(4.0),
                "terminal_genuine": True,
            },
            "b-root": {
                "root_candidate_id": "b", "depth": 1,
                "vector": vector(1.0),
                "evaluation_vector": vector(10.0),
                "terminal_vector": vector(10.0),
                "terminal_genuine": True,
            },
        }
        roots = [
            {"root_candidate_id": "a", "node": "a-root"},
            {"root_candidate_id": "b", "node": "b-root"},
        ]

        audit = build_resurrection_audit(roots, nodes)

        self.assertEqual(audit["h1_pareto_candidates"], ["a"])
        self.assertEqual(audit["measured_search_pareto_candidates"], ["a"])
        self.assertEqual(audit["evaluated_search_pareto_candidates"], ["b"])
        self.assertEqual(audit["terminal_pareto_candidates"], ["b"])
        self.assertEqual(
            audit["terminal_frontier_resurrection_candidates"], ["b"]
        )
        self.assertEqual(audit["deepened_resurrection_candidates"], [])
        self.assertEqual(audit["deepened_resurrection_recall"], 0.0)
        self.assertEqual(audit["evaluated_frontier_resurrection_recall"], 1.0)
        self.assertTrue(
            audit["candidate_audit"]["b"]["terminal_frontier_resurrection"]
        )
        self.assertFalse(audit["candidate_audit"]["b"]["deepened"])

    def test_resurrection_audit_counts_actual_deepening_independently(self):
        nodes = {
            "a-root": {
                "root_candidate_id": "a", "depth": 1,
                "vector": vector(3.0), "evaluation_vector": vector(3.0),
                "terminal_vector": vector(4.0), "terminal_genuine": True,
            },
            "b-root": {
                "root_candidate_id": "b", "depth": 1,
                "vector": vector(1.0), "evaluation_vector": vector(1.0),
                "terminal_vector": vector(10.0), "terminal_genuine": True,
            },
            "b-deep": {
                "root_candidate_id": "b", "depth": 2,
                "vector": vector(6.0), "evaluation_vector": vector(6.0),
                "terminal_vector": vector(10.0), "terminal_genuine": True,
            },
        }
        roots = [
            {"root_candidate_id": "a", "node": "a-root"},
            {"root_candidate_id": "b", "node": "b-root"},
        ]

        audit = build_resurrection_audit(roots, nodes)

        self.assertEqual(audit["deepened_candidates"], ["b"])
        self.assertEqual(audit["deepened_resurrection_candidates"], ["b"])
        self.assertEqual(audit["deepened_resurrection_recall"], 1.0)
        self.assertEqual(
            audit["measured_frontier_resurrection_candidates"], ["b"]
        )

    def test_censored_terminal_rollout_never_enters_terminal_truth(self):
        nodes = {
            "a-root": {
                "root_candidate_id": "a", "depth": 1,
                "vector": vector(3.0), "evaluation_vector": vector(3.0),
                "terminal_vector": vector(4.0), "terminal_genuine": True,
            },
            "b-root": {
                "root_candidate_id": "b", "depth": 1,
                "vector": vector(1.0), "evaluation_vector": None,
                "terminal_vector": None, "terminal_genuine": False,
            },
        }
        roots = [
            {"root_candidate_id": "a", "node": "a-root"},
            {"root_candidate_id": "b", "node": "b-root"},
        ]

        audit = build_resurrection_audit(roots, nodes)

        self.assertEqual(audit["terminal_eligible_candidates"], ["a"])
        self.assertEqual(audit["terminal_censored_candidates"], ["b"])
        self.assertEqual(audit["terminal_frontier_resurrection_candidates"], [])
        self.assertIsNone(audit["deepened_resurrection_recall"])

    def test_resurrection_summary_uses_action_counts_and_skips_censored_roots(self):
        complete = {
            "terminal_truth_complete": True,
            "terminal_frontier_resurrection_candidates": ["a", "b"],
            "deepened_resurrection_candidates": ["a"],
            "measured_frontier_resurrection_candidates": [],
            "evaluated_frontier_resurrection_candidates": ["a", "b"],
        }
        no_resurrection = {
            "terminal_truth_complete": True,
            "terminal_frontier_resurrection_candidates": [],
            "deepened_resurrection_candidates": [],
            "measured_frontier_resurrection_candidates": [],
            "evaluated_frontier_resurrection_candidates": [],
        }
        censored = {
            "terminal_truth_complete": False,
            "terminal_frontier_resurrection_candidates": ["must-not-count"],
        }

        summary = summarize_resurrection_audits([
            complete, no_resurrection, censored
        ])

        self.assertEqual(summary["roots"], 3)
        self.assertEqual(summary["terminal_truth_complete_roots"], 2)
        self.assertEqual(summary["terminal_truth_censored_roots"], 1)
        self.assertEqual(summary["terminal_resurrection_actions"], 2)
        self.assertEqual(summary["deepened_resurrection_actions"], 1)
        self.assertEqual(summary["deepened_resurrection_recall"], 0.5)
        self.assertEqual(summary["evaluated_frontier_resurrection_recall"], 1.0)

    @mock.patch("scripts.run_vector_mcts.build_candidate_provider")
    @mock.patch("scripts.run_vector_mcts._rollout")
    def test_rollout_leaf_eval_records_terminal_truth_without_losing_h1(
        self, measured_rollout, provider_builder,
    ):
        provider_builder.return_value = lambda *_args: []

        class Env:
            def close(self):
                pass

        def measured(*_args, actions, **_kwargs):
            fill = 3.0 if actions[0]["item_idx"] == 0 else 1.0
            return {
                "safe": True, "terminated": False, "truncated": False,
                "step_deltas": [{
                    head: {"value": value}
                    for head, value in vector(fill).items()
                }],
                "observation": {}, "env": Env(),
            }

        measured_rollout.side_effect = measured

        def terminal(actions):
            fill = 4.0 if actions[0]["item_idx"] == 0 else 10.0
            return {
                "termination": "stream_exhausted",
                "genuine_terminal": True,
                "continuation_steps": 4,
                "physical_steps": 5,
                "terminal_vector": vector(fill),
                "terminal_metrics": {"fill_score_proxy": fill},
                "evaluation": {},
            }

        def candidate(name, item_idx, rank):
            return {
                "candidate_id": name,
                "command_action": {
                    "item_idx": item_idx, "container_idx": 0,
                    "place_pos": [0.0, 0.0, 0.0], "orientation": 0,
                },
                "selection": {"rank": rank, "stable_item_index": item_idx},
                "proposal_provenance": {"source": "test"},
            }

        result = vector_search_root(
            object(), {}, case_id="case", environment_seed=42,
            prefix_actions=[],
            root_candidates=[candidate("a", 0, 0), candidate("b", 1, 1)],
            attempt_budget=1, deep_top_k=1, expansions=0,
            max_depth=1, step=0, leaf_eval="rollout",
            terminal_rollout_fn=terminal,
        )

        self.assertEqual(result["leaf_eval"], "rollout")
        self.assertEqual(
            [row["root_candidate_id"] for row in result["root_candidates"]],
            ["a", "b"],
        )
        self.assertEqual(result["root_candidate_ids"], ["a", "b"])
        self.assertEqual(result["h1_pareto_candidates"], ["a"])
        self.assertEqual(result["terminal_pareto_candidates"], ["b"])
        self.assertEqual(
            result["terminal_frontier_resurrection_candidates"], ["b"]
        )
        self.assertEqual(result["search_pareto_candidates"], ["b"])
        self.assertEqual(result["terminal_rollout_physical_steps"], 10)

    @mock.patch("scripts.run_vector_mcts.build_candidate_provider")
    @mock.patch("scripts.run_vector_mcts._rollout")
    def test_measured_leaf_eval_never_calls_terminal_oracle(
        self, measured_rollout, provider_builder,
    ):
        provider_builder.return_value = lambda *_args: []

        class Env:
            def close(self):
                pass

        measured_rollout.return_value = {
            "safe": True, "terminated": False, "truncated": False,
            "step_deltas": [{
                head: {"value": value}
                for head, value in vector(2.0).items()
            }],
            "observation": {}, "env": Env(),
        }
        terminal = mock.Mock(side_effect=AssertionError("oracle called"))
        candidate = {
            "candidate_id": "a",
            "command_action": {
                "item_idx": 0, "container_idx": 0,
                "place_pos": [0.0, 0.0, 0.0], "orientation": 0,
            },
            "selection": {"rank": 0, "stable_item_index": 0},
            "proposal_provenance": {"source": "test"},
        }

        result = vector_search_root(
            object(), {}, case_id="case", environment_seed=42,
            prefix_actions=[], root_candidates=[candidate],
            attempt_budget=1, deep_top_k=1, expansions=0,
            max_depth=1, step=0, leaf_eval="measured",
            terminal_rollout_fn=terminal,
        )

        terminal.assert_not_called()
        self.assertEqual(result["search_pareto_candidates"], ["a"])
        self.assertFalse(result["terminal_truth_complete"])

    @mock.patch("scripts.run_vector_mcts.build_candidate_provider")
    @mock.patch("scripts.run_vector_mcts._rollout")
    def test_terminal_audit_scores_roots_but_does_not_guide_allocation(
        self, measured_rollout, provider_builder,
    ):
        provider_builder.return_value = lambda *_args: []

        class Env:
            def close(self):
                pass

        def measured(*_args, actions, **_kwargs):
            fill = 3.0 if actions[0]["item_idx"] == 0 else 1.0
            return {
                "safe": True, "terminated": False, "truncated": False,
                "step_deltas": [{
                    head: {"value": value}
                    for head, value in vector(fill).items()
                }],
                "observation": {}, "env": Env(),
            }

        measured_rollout.side_effect = measured
        terminal = mock.Mock(side_effect=lambda actions: {
            "termination": "stream_exhausted",
            "genuine_terminal": True,
            "continuation_steps": 2,
            "physical_steps": 3,
            "terminal_vector": vector(
                4.0 if actions[0]["item_idx"] == 0 else 10.0
            ),
            "terminal_metrics": {},
            "evaluation": {},
        })

        result = vector_search_root(
            object(), {}, case_id="case", environment_seed=42,
            prefix_actions=[],
            root_candidates=[
                self._candidate("a", 0), self._candidate("b", 1)
            ],
            attempt_budget=1, deep_top_k=1, expansions=0,
            max_depth=1, step=0, leaf_eval="measured",
            terminal_audit=True, terminal_rollout_fn=terminal,
        )

        self.assertEqual(terminal.call_count, 2)
        self.assertEqual(result["search_pareto_candidates"], ["a"])
        self.assertEqual(result["terminal_pareto_candidates"], ["b"])
        self.assertEqual(
            result["terminal_frontier_resurrection_candidates"], ["b"]
        )
        self.assertEqual(result["terminal_rollout_physical_steps"], 6)

    @mock.patch("scripts.run_vector_mcts.build_candidate_provider")
    @mock.patch("scripts.run_vector_mcts._rollout")
    def test_value_leaf_uses_model_while_terminal_audit_stays_scoring_only(
        self, measured_rollout, provider_builder,
    ):
        provider_builder.return_value = lambda *_args: []

        class Env:
            def close(self):
                pass

        def measured(*_args, actions, **_kwargs):
            item = actions[0]["item_idx"]
            return {
                "safe": True, "terminated": False, "truncated": False,
                "step_deltas": [{
                    head: {"value": value}
                    for head, value in vector(3.0 if item == 0 else 1.0).items()
                }],
                "observation": {"item": item}, "env": Env(),
            }

        measured_rollout.side_effect = measured
        terminal = mock.Mock(side_effect=lambda actions: {
            "termination": "stream_exhausted", "genuine_terminal": True,
            "continuation_steps": 1, "physical_steps": 2,
            "terminal_vector": vector(
                4.0 if actions[0]["item_idx"] == 0 else 10.0
            ),
            "terminal_metrics": {}, "evaluation": {},
        })

        def leaf(*, observation, **_kwargs):
            remaining = 0.0 if observation["item"] == 0 else 9.0
            return {
                "fill_return": {"mean": remaining},
                "soft_violation_return": {"mean": 0.0},
                "priority_covered_return": {"mean": 0.0},
                "priority_misrouted_return": {"mean": 0.0},
                "surface_total_variation_return": {"mean": 0.0},
            }

        result = vector_search_root(
            object(), {}, case_id="case", environment_seed=42,
            prefix_actions=[], root_candidates=[
                self._candidate("a", 0), self._candidate("b", 1)
            ],
            attempt_budget=1, deep_top_k=1, expansions=0,
            max_depth=2, step=0, leaf_eval="value",
            allocation="pareto-puct", leaf_vector_fn=leaf,
            terminal_audit=True, terminal_rollout_fn=terminal,
        )

        self.assertEqual(result["measured_search_pareto_candidates"], ["a"])
        self.assertEqual(result["evaluated_search_pareto_candidates"], ["b"])
        self.assertEqual(result["terminal_pareto_candidates"], ["b"])
        self.assertEqual(terminal.call_count, 2)

    @staticmethod
    def _candidate(name, item_idx):
        return {
            "candidate_id": name,
            "command_action": {
                "item_idx": item_idx, "container_idx": 0,
                "place_pos": [0.0, 0.0, 0.0], "orientation": 0,
            },
            "selection": {"rank": item_idx, "stable_item_index": item_idx},
            "proposal_provenance": {"source": "test"},
        }

    def test_pareto_puct_optimism_reopens_a_low_visit_dominated_edge(self):
        edges = {
            "a": _new_edge_stat(prior=0.5),
            "b": _new_edge_stat(prior=0.5),
        }
        _update_edge_stat(edges["a"], vector(3.0))
        _update_edge_stat(edges["b"], vector(1.0))
        # Equal counts: exploitation keeps the currently dominant edge.
        self.assertEqual(_pareto_puct_choice(edges, c_puct=2.0), "a")
        # Evidence accumulated under a reduces its count bonus; b becomes
        # optimistic and must be revisited despite its lower mean.
        _update_edge_stat(edges["a"], vector(3.0))
        _update_edge_stat(edges["a"], vector(3.0))
        self.assertEqual(_pareto_puct_choice(edges, c_puct=2.0), "b")

    def test_pareto_puct_tie_break_uses_prior_separately_from_optimism(self):
        edges = {
            "coverage": _new_edge_stat(prior=0.25),
            "learned": _new_edge_stat(prior=0.75),
        }
        for edge in edges.values():
            _update_edge_stat(edge, vector(2.0))
        self.assertEqual(
            _pareto_puct_choice(edges, c_puct=1.0), "learned"
        )

    @mock.patch("scripts.run_vector_mcts.build_candidate_provider")
    @mock.patch("scripts.run_vector_mcts._rollout")
    def test_pareto_puct_deepens_a_shallow_dominated_root_that_v0_drops(
        self, measured_rollout, provider_builder,
    ):
        class Env:
            def close(self):
                pass

        continuation = self._candidate("child", 9)
        provider_builder.return_value = lambda _env, observation, _k: (
            [continuation] if observation["depth"] < 3 else []
        )

        def measured(*_args, actions, **_kwargs):
            root_fill = 3.0 if actions[0]["item_idx"] == 0 else 1.0
            deltas = [vector(root_fill)] + [vector(0.0)] * (len(actions) - 1)
            return {
                "safe": True, "terminated": False, "truncated": False,
                "step_deltas": [
                    {head: {"value": value} for head, value in delta.items()}
                    for delta in deltas
                ],
                "observation": {"depth": len(actions)}, "env": Env(),
            }

        measured_rollout.side_effect = measured
        common = dict(
            agent_module=object(), task_config={}, case_id="case",
            environment_seed=42, prefix_actions=[],
            root_candidates=[
                self._candidate("a", 0), self._candidate("b", 1)
            ],
            attempt_budget=1, deep_top_k=1, expansions=2,
            max_depth=3, step=0, leaf_eval="measured",
        )

        v0 = vector_search_root(**common, allocation="frontier")
        puct = vector_search_root(
            **common, allocation="pareto-puct", c_puct=2.0
        )

        self.assertNotIn("b", v0["deepened_candidates"])
        self.assertIn("b", puct["deepened_candidates"])
        self.assertGreater(
            puct["root_visit_counts"]["b"], v0["root_visit_counts"]["b"]
        )
        self.assertAlmostEqual(sum(puct["root_visit_policy"].values()), 1.0)

    @mock.patch("scripts.run_vector_mcts._compact_evaluation", side_effect=lambda x: x)
    @mock.patch("scripts.run_vector_mcts.cumulative_metrics")
    @mock.patch("scripts.run_vector_mcts._fresh_env")
    def test_terminal_rollout_reaches_rank0_genuine_terminal(
        self, fresh_env, metrics_fn, _compact,
    ):
        class Env:
            def __init__(self):
                self.fill = 0.0

            def reset_settings(self):
                pass

            def reset_item_stream(self):
                pass

            def reset(self, seed):
                return {}, {}

            def step(self, action):
                self.fill += float(action["fill"])
                return {}, 0.0, False, False, {
                    "status": {
                        "is_included": True, "is_valid": True,
                        "is_placed_safe": True,
                    }
                }

            def evaluate(self):
                return {"shake_response": {"shake_max_shift": 0.25}}

            def close(self):
                pass

        env = Env()
        fresh_env.return_value = env

        def current_metrics(current):
            return {
                "fill_score_proxy": current.fill,
                "placed_count": current.fill,
                "soft_covered_by_other": 0.0,
                "priority_covered_by_other": 0.0,
                "priority_misrouted": 0.0,
                "center_of_mass_z": 0.0,
                "surface_total_variation": 0.0,
            }

        metrics_fn.side_effect = current_metrics
        provider = mock.Mock(return_value=[])

        result = _terminal_rollout(
            {}, environment_seed=42, prefix_actions=[],
            forced_actions=[{"fill": 2.0}], provider=provider,
            legal_filter=mock.Mock(), top_k=3, root_step=0,
            max_continuation_steps=10,
        )

        self.assertEqual(result["termination"], "no_retained_candidate")
        self.assertTrue(result["genuine_terminal"])
        self.assertEqual(result["terminal_vector"]["fill_gain"], 2.0)
        self.assertEqual(result["forced_actions"], [{"fill": 2.0}])
        self.assertEqual(result["continuation_actions"], [])
        self.assertEqual(
            result["terminal_metrics"]["post_shake_max_shift"], 0.25
        )

    @mock.patch("scripts.run_vector_mcts.cumulative_metrics", return_value={})
    @mock.patch("scripts.run_vector_mcts._fresh_env")
    def test_terminal_rollout_cap_is_censored(self, fresh_env, _metrics):
        class Env:
            def reset_settings(self):
                pass

            def reset_item_stream(self):
                pass

            def reset(self, seed):
                return {}, {}

            def step(self, _action):
                return {}, 0.0, False, False, {
                    "status": {
                        "is_included": True, "is_valid": True,
                        "is_placed_safe": True,
                    }
                }

            def close(self):
                pass

        fresh_env.return_value = Env()
        result = _terminal_rollout(
            {}, environment_seed=42, prefix_actions=[],
            forced_actions=[{"fill": 1.0}], provider=mock.Mock(),
            legal_filter=mock.Mock(), top_k=3, root_step=0,
            max_continuation_steps=0,
        )

        self.assertEqual(result["termination"], "continuation_cap")
        self.assertFalse(result["genuine_terminal"])
        self.assertIsNone(result["terminal_vector"])


class BetaProposalTests(unittest.TestCase):
    def test_stratum_entropy_zero_for_collapsed_proposals(self):
        row = {
            "selection": {"stable_item_index": 4},
            "command_action": {
                "container_idx": 0, "orientation": 1,
                "place_pos": [0, 0, 0],
            },
        }
        self.assertEqual(stratum_entropy([row, dict(row)]), 0.0)

    def test_stratum_entropy_grows_with_diversity(self):
        rows = [
            {
                "selection": {"stable_item_index": index},
                "command_action": {
                    "container_idx": 0, "orientation": 0,
                    "place_pos": [0, 0, 0],
                },
            }
            for index in range(4)
        ]
        self.assertGreater(stratum_entropy(rows), 1.0)


if __name__ == "__main__":
    unittest.main()
