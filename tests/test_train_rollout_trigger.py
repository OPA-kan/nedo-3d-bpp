import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

import numpy as np

from scripts.train_rollout_trigger import (
    budget_curve,
    group_folds,
    load_examples,
    select_operating_points,
)


def snapshot():
    return {
        "observation": {
            "container_list": [{
                "index": 0, "length": 2, "width": 1, "height": 1,
                "packed_items": [],
            }],
            "pool_list": [{
                "index": 3, "length": 0.2, "width": 0.2,
                "height": 0.2, "mass": 1,
            }],
        },
        "physics": {"packed_items": []},
    }


class RolloutTriggerTests(unittest.TestCase):
    def test_script_can_run_directly_like_the_workflow(self):
        result = subprocess.run(
            [sys.executable, "scripts/train_rollout_trigger.py", "--help"],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--dataset-root", result.stdout)

    def test_load_excludes_future_and_builds_candidate_set(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            (root / "cell").mkdir()
            (root / "cell" / "state.json").write_text(
                json.dumps(snapshot()), encoding="utf-8"
            )
            row = {
                "cell": "cell", "root_id": "r", "snapshot_path": "cell/state.json",
                "incumbent_candidate_id": "a", "terminal_intervention": True,
                "decision_timing": {"decision_total_seconds": 12.0},
                "estimated_no_terminal_decision_seconds": 2.0,
                "candidates": [{
                    "root_candidate_id": "a", "safe": True,
                    "one_step_vector": {
                        "fill_gain": 1, "soft_violation_gain": 0,
                        "priority_covered_gain": 0,
                        "priority_misrouted_gain": 0,
                        "surface_total_variation_delta": 0.5,
                    },
                }],
            }
            dataset = {
                "contract": "terminal_rollout_trigger_dataset_v1",
                "rows": [row, {**row, "cell": "cell2", "root_id": "r2"}],
            }
            (root / "dataset.json").write_text(json.dumps(dataset))
            examples, contract = load_examples(root / "dataset.json", root)
        self.assertEqual(examples[0]["candidate"][0], [1, 0, 0, 0, -0.5, 1])
        self.assertNotIn("step", contract["state_features"])
        self.assertIn("terminal_vector", contract["forbidden_inputs"])

    def test_group_folds_never_split_a_group(self):
        folds = group_folds(["a", "a", "b", "c"], 2, 7)
        self.assertEqual(set.union(*folds), {"a", "b", "c"})
        self.assertFalse(folds[0] & folds[1])

    def test_budget_curve_exposes_recall_latency_tradeoff(self):
        labels = np.asarray([1.0, 0.0, 0.0])
        scores = np.asarray([0.9, 0.8, 0.1])
        full = np.asarray([12.0, 20.0, 30.0])
        shallow = np.asarray([2.0, 2.0, 2.0])
        points = budget_curve(labels, scores, full, shallow)
        chosen = select_operating_points(points)
        fast = chosen["fastest_with_recall_ge_0_8"]
        self.assertEqual(fast["triggered_roots"], 1)
        self.assertEqual(fast["intervention_recall"], 1.0)
        self.assertGreater(fast["estimated_speedup_vs_full"], 3.0)


if __name__ == "__main__":
    unittest.main()
