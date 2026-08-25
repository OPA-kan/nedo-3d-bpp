import importlib.util
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

import numpy as np

from scripts.train_rollout_trigger import (
    CANDIDATE_GEOMETRY_FEATURES,
    allocator_budget_curve,
    budget_curve,
    group_folds,
    load_examples,
    select_operating_points,
)

TORCH_AVAILABLE = importlib.util.find_spec("torch") is not None


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
                "incumbent_candidate_id": "a", "selected_candidate_id": "a",
                "terminal_intervention": True,
                "decision_timing": {"decision_total_seconds": 12.0},
                "estimated_no_terminal_decision_seconds": 2.0,
                "candidates": [{
                    "root_candidate_id": "a", "safe": True,
                    "stable_item_index": 3,
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
        token = examples[0]["candidate"][0]
        self.assertEqual(token[:5], [1, 0, 0, 0, -0.5])
        self.assertEqual(token[5:9], [0.2, 0.2, 0.2, 1.0])
        self.assertEqual(token[-1], 1.0)
        self.assertNotIn("step", contract["state_features"])
        self.assertIn("terminal_vector", contract["forbidden_inputs"])

    def test_group_folds_never_split_a_group(self):
        folds = group_folds(["a", "a", "b", "c"], 2, 7)
        self.assertEqual(set.union(*folds), {"a", "b", "c"})
        self.assertFalse(folds[0] & folds[1])

    def test_geometry_policy_uses_action_without_h1_outcomes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            (root / "cell").mkdir()
            state = snapshot()
            state["observation"]["container_list"][0]["center"] = [1, 2, 0]
            (root / "cell" / "state.json").write_text(
                json.dumps(state), encoding="utf-8"
            )
            candidate = {
                "root_candidate_id": "a", "safe": True,
                "stable_item_index": 3,
                "command_action": {
                    "item_idx": 3, "container_idx": 0,
                    "place_pos": [1.5, 2.25, 0.5], "orientation": 2,
                },
                # Deliberately absent: one_step_vector.
            }
            row = {
                "cell": "cell", "root_id": "r",
                "snapshot_path": "cell/state.json",
                "incumbent_candidate_id": "a", "selected_candidate_id": "a",
                "terminal_intervention": False,
                "decision_timing": {"decision_total_seconds": 12.0},
                "estimated_no_terminal_decision_seconds": 2.0,
                "candidates": [candidate],
            }
            dataset = {
                "contract": "terminal_rollout_trigger_dataset_with_actions_v1",
                "rows": [row, {**row, "cell": "cell2", "root_id": "r2"}],
            }
            (root / "dataset.json").write_text(json.dumps(dataset))
            examples, contract = load_examples(
                root / "dataset.json", root,
                candidate_feature_mode="geometry",
            )
        token = examples[0]["candidate"][0]
        self.assertEqual(token[:3], [0.5, 0.25, 0.5])
        self.assertEqual(token[6:12], [0, 0, 1, 0, 0, 0])
        self.assertEqual(len(token), len(CANDIDATE_GEOMETRY_FEATURES))
        self.assertEqual(contract["candidate_feature_mode"], "geometry")

    def test_group_folds_stratify_positive_trajectories(self):
        groups = ["a", "a", "b", "b", "c", "c", "d", "d"]
        labels = [1, 0, 1, 0, 1, 0, 1, 0]
        folds = group_folds(groups, 4, 7, labels=labels)
        positives = {
            group for group, label in zip(groups, labels) if label
        }
        self.assertTrue(all(fold & positives for fold in folds))

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

    @unittest.skipUnless(TORCH_AVAILABLE, "torch not installed")
    def test_saved_ensemble_round_trips_and_scores_live_candidates(self):
        import torch

        from scripts.learned_allocator_policy import LearnedAllocatorPolicy
        from scripts.train_rollout_trigger import (
            load_allocator_ensemble,
            predict_allocator,
            save_allocator_ensemble,
        )

        state = snapshot()
        state["observation"]["container_list"][0]["center"] = [1, 2, 0]
        state["observation"]["container_list"][0]["packed_items"] = [
            {"index": 0, "length": 0.2, "width": 0.2, "height": 0.2,
             "mass": 1},
        ]
        state["physics"]["packed_items"] = [{
            "container_index": 0, "item_index": 0,
            "position": [1.0, 2.0, 0.1], "quaternion": [0, 0, 0, 1],
        }]
        candidates = [
            {
                "root_candidate_id": name, "safe": True,
                "stable_item_index": 3,
                "command_action": {
                    "item_idx": 3, "container_idx": 0,
                    "place_pos": [1.5 + shift, 2.25, 0.5],
                    "orientation": 2,
                },
            }
            for shift, name in ((0.0, "a"), (0.3, "b"))
        ]
        row = {
            "cell": "cell", "root_id": "r",
            "snapshot_path": "cell/state.json",
            "incumbent_candidate_id": "a", "selected_candidate_id": "b",
            "terminal_intervention": True,
            "decision_timing": {"decision_total_seconds": 12.0},
            "estimated_no_terminal_decision_seconds": 2.0,
            "candidates": candidates,
        }
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            (root / "cell").mkdir()
            (root / "cell" / "state.json").write_text(
                json.dumps(state), encoding="utf-8"
            )
            dataset = {
                "contract": (
                    "terminal_rollout_trigger_dataset_with_actions_v1"
                ),
                "rows": [row, {**row, "cell": "cell2", "root_id": "r2"}],
            }
            (root / "dataset.json").write_text(json.dumps(dataset))
            examples, contract = load_examples(
                root / "dataset.json", root,
                candidate_feature_mode="geometry",
            )
            model_dir = root / "model"
            metadata = save_allocator_ensemble(
                torch, examples, contract, model_dir,
                ensemble_size=2, epochs=1, dim=8, seed=7,
            )
            self.assertEqual(len(metadata["members"]), 2)
            members, loaded = load_allocator_ensemble(torch, model_dir)
            self.assertEqual(
                loaded["feature_contract"]["candidate_feature_mode"],
                "geometry",
            )
            offline = predict_allocator(torch, members, examples)[0]
            policy = LearnedAllocatorPolicy(model_dir)
            live = policy.score_candidates(
                state, candidates, incumbent_id="a"
            )
        self.assertEqual(set(live), {"a", "b"})
        self.assertAlmostEqual(sum(live.values()), 1.0, places=5)
        # the runtime path must reproduce the offline forward pass
        self.assertAlmostEqual(live["a"], offline[0], places=5)
        self.assertAlmostEqual(live["b"], offline[1], places=5)

    def test_allocator_budget_keeps_incumbent_and_ranks_one_alternative(self):
        examples = [{
            "candidate_ids": ["inc", "bad", "winner"],
            "candidate_work": [10.0, 10.0, 10.0],
            "incumbent_index": 0,
            "selected_index": 2,
            "full_seconds": 32.0,
            "shallow_seconds": 2.0,
        }]
        points = allocator_budget_curve(examples, [[0.1, 0.2, 0.9]])
        self.assertEqual(points[1]["candidate_budget"], 2)
        self.assertEqual(points[1]["intervention_action_recall"], 1.0)
        self.assertEqual(
            points[1]["uniform_expected_intervention_recall"], 0.5
        )
        self.assertAlmostEqual(points[1]["estimated_mean_seconds"], 22.0)


if __name__ == "__main__":
    unittest.main()
