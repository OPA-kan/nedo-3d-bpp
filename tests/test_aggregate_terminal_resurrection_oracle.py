import json
import pathlib
import tempfile
import unittest

from scripts.aggregate_terminal_resurrection_oracle import (
    aggregate,
    compare_pair,
    render_markdown,
)


def _payload(*, rollout: bool, complete: bool = True):
    root = {
        "root_id": "root-1",
        "root_candidates": [
            {
                "root_candidate_id": "a",
                "one_step_vector": {"fill": 1.0},
            },
            {
                "root_candidate_id": "b",
                "one_step_vector": {"fill": 0.5},
            },
        ],
    }
    payload = {
        "contract": (
            "pareto_tree_search_terminal_oracle_v2"
            if rollout else "vector_mcts_search_pareto_v1"
        ),
        "oracle_contract": (
            "terminal_frontier_resurrection_v1" if rollout else None
        ),
        "case_id": "case",
        "roots": [root],
    }
    if rollout:
        root.update({
            "terminal_truth_complete": complete,
            "terminal_frontier_resurrection_candidates": (
                ["b"] if complete else []
            ),
        })
        payload["resurrection_summary"] = {
            "deepened_resurrection_actions": 1 if complete else 0,
            "measured_frontier_resurrection_actions": 0,
            "evaluated_frontier_resurrection_actions": 1 if complete else 0,
        }
    return payload


class TerminalResurrectionAggregateTests(unittest.TestCase):
    def test_pair_requires_identical_h1_vectors(self):
        measured = _payload(rollout=False)
        rollout = _payload(rollout=True)
        rollout["roots"][0]["root_candidates"][0]["one_step_vector"][
            "fill"
        ] = 2.0
        with self.assertRaisesRegex(ValueError, "H1 candidate vectors differ"):
            compare_pair(measured, rollout, cell="x")

    def test_aggregate_counts_actions_and_censored_roots(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            for cell, complete in (("a", True), ("b", False)):
                directory = root / cell
                directory.mkdir()
                (directory / "measured.json").write_text(
                    json.dumps(_payload(rollout=False)), encoding="utf-8"
                )
                (directory / "rollout.json").write_text(
                    json.dumps(_payload(rollout=True, complete=complete)),
                    encoding="utf-8",
                )
            result = aggregate(root)
        self.assertEqual(result["cell_count"], 2)
        self.assertEqual(result["root_count"], 2)
        self.assertEqual(result["complete_terminal_truth_roots"], 1)
        self.assertEqual(result["censored_terminal_truth_roots"], 1)
        self.assertEqual(result["terminal_resurrection_actions"], 1)
        self.assertEqual(result["deepened_resurrection_recall"], 1.0)
        self.assertIn("paired H1 vectors identical", render_markdown(result))

    def test_missing_measured_arm_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            directory = root / "a"
            directory.mkdir()
            (directory / "rollout.json").write_text(
                json.dumps(_payload(rollout=True)), encoding="utf-8"
            )
            with self.assertRaises(FileNotFoundError):
                aggregate(root)


if __name__ == "__main__":
    unittest.main()
