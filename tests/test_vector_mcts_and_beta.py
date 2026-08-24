import unittest
from unittest import mock

from scripts.run_vector_mcts import (
    _accumulate,
    _dominates,
    _oriented,
    _output_contract,
    _terminal_rollout,
    build_resurrection_audit,
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
