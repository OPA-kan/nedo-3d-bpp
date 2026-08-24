import json
import pathlib
import tempfile
import unittest

from scripts.aggregate_terminal_resurrection_oracle import (
    aggregate,
    compare_allocation_pair,
    render_markdown,
)


def _payload(*, allocation, deepened, frontier, complete=True):
    terminal_vector_a = {"fill_gain": 2.0}
    terminal_vector_b = {"fill_gain": 5.0}
    root = {
        "root_id": "root-1",
        "root_candidates": [
            {
                "root_candidate_id": "a", "safe": True,
                "one_step_vector": {"fill_gain": 3.0},
                "terminal_genuine": complete,
                "terminal_vector": terminal_vector_a if complete else None,
            },
            {
                "root_candidate_id": "b", "safe": True,
                "one_step_vector": {"fill_gain": 1.0},
                "terminal_genuine": complete,
                "terminal_vector": terminal_vector_b if complete else None,
            },
        ],
        "terminal_truth_complete": complete,
        "terminal_frontier_resurrection_candidates": (
            ["b"] if complete else []
        ),
        "terminal_pareto_candidates": ["b"] if complete else [],
        "deepened_candidates": list(deepened),
        "measured_search_pareto_candidates": list(frontier),
        "physical_steps": 10,
        "terminal_rollout_physical_steps": 8,
        "item_symmetry_cache_shadow": {
            "observations": 3,
            "quotient_only_hits": 1,
            "potential_state_reduction": 1,
            "evaluator_by_kind": {
                "rollout": {
                    "potential_call_savings": 1,
                    "conflicts": 0,
                }
            },
        },
    }
    return {
        "contract": "pareto_search_terminal_audit_v3",
        "oracle_contract": "terminal_frontier_resurrection_v1",
        "case_id": "case",
        "leaf_eval": "measured",
        "terminal_audit": True,
        "allocation_mode": allocation,
        "roots": [root],
    }


class TerminalResurrectionAggregateTests(unittest.TestCase):
    def test_pair_requires_identical_h1_and_terminal_evidence(self):
        v0 = _payload(allocation="frontier", deepened=[], frontier=["a"])
        puct = _payload(
            allocation="pareto-puct", deepened=["b"], frontier=["b"]
        )
        puct["roots"][0]["root_candidates"][0]["terminal_vector"][
            "fill_gain"
        ] = 9.0
        with self.assertRaisesRegex(ValueError, "terminal evidence differs"):
            compare_allocation_pair(v0, puct, cell="x")

    def test_pair_rejects_oracle_guided_allocation(self):
        v0 = _payload(allocation="frontier", deepened=[], frontier=["a"])
        puct = _payload(
            allocation="pareto-puct", deepened=["b"], frontier=["b"]
        )
        puct["leaf_eval"] = "rollout"
        with self.assertRaisesRegex(ValueError, "saw terminal values"):
            compare_allocation_pair(v0, puct, cell="x")

    def test_aggregate_scores_both_arms_against_shared_truth(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            directory = root / "cell"
            directory.mkdir()
            v0 = _payload(
                allocation="frontier", deepened=[], frontier=["a"]
            )
            puct = _payload(
                allocation="pareto-puct", deepened=["b"], frontier=["b"]
            )
            (directory / "v0.json").write_text(
                json.dumps(v0), encoding="utf-8"
            )
            (directory / "puct.json").write_text(
                json.dumps(puct), encoding="utf-8"
            )
            result = aggregate(root)

        self.assertEqual(result["terminal_resurrection_actions"], 1)
        self.assertEqual(result["v0"]["deepened_resurrection_recall"], 0.0)
        self.assertEqual(result["v0"]["frontier_resurrection_recall"], 0.0)
        self.assertEqual(result["v0"]["false_frontier_actions"], 1)
        self.assertEqual(
            result["pareto_puct"]["deepened_resurrection_recall"], 1.0
        )
        self.assertEqual(
            result["pareto_puct"]["frontier_resurrection_recall"], 1.0
        )
        self.assertEqual(
            result["pareto_puct"][
                "symmetry_shadow_potential_rollout_savings"
            ],
            1,
        )
        self.assertEqual(
            result["pareto_puct"][
                "symmetry_shadow_potential_state_reduction"
            ],
            1,
        )
        self.assertIn("Pareto-PUCT", render_markdown(result))
        self.assertIn("physical rollout reuse shadow", render_markdown(result))

    def test_missing_v0_arm_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            directory = root / "cell"
            directory.mkdir()
            puct = _payload(
                allocation="pareto-puct", deepened=["b"], frontier=["b"]
            )
            (directory / "puct.json").write_text(
                json.dumps(puct), encoding="utf-8"
            )
            with self.assertRaises(FileNotFoundError):
                aggregate(root)


if __name__ == "__main__":
    unittest.main()
