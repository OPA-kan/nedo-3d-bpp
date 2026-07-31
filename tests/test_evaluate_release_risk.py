import importlib.util
import pathlib
import sys
import unittest

import numpy as np


MODULE_PATH = (
    pathlib.Path(__file__).parents[1] / "scripts" / "evaluate_release_risk.py"
)
SPEC = importlib.util.spec_from_file_location(
    "evaluate_release_risk", MODULE_PATH
)
risk_mod = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = risk_mod
SPEC.loader.exec_module(risk_mod)


def release_row(
    snapshot="snap-0",
    candidate_id="c0",
    score=1.0,
    rotated=False,
    unsafe=False,
    selected=False,
    support_ratio=0.5,
):
    return {
        "kind": "release_candidate",
        "snapshot_id": snapshot,
        "candidate_id": candidate_id,
        "score_immediate": score,
        "selected": selected,
        "phi_modelling": {
            "support_ratio": support_ratio,
            "com_margin": 0.1,
            "drop_normalized": 0.2,
            "support_imbalance": 0.0,
            "left_right_imbalance": 0.0,
            "front_back_imbalance": 0.0,
        },
        "sampling": {"sampling_weight": 1.0},
        "physical": {
            "d_xy": 0.4 if unsafe else 0.01,
            "Y": {
                "rotated_over_30": rotated,
                "horizontal_displaced_over_half_footprint": unsafe,
                "displaced_over_half_footprint": unsafe,
                "not_placed_safe": unsafe,
                "not_valid": False,
                "not_included": False,
                "physically_dangerous": rotated or unsafe,
            },
        },
    }


class LeakageTests(unittest.TestCase):
    def test_held_out_group_is_scored_by_other_groups_only(self):
        # Group A is all-positive, group B all-negative. A one-class
        # training fold must fall back to its own mean, proving the
        # held-out group's rows were not used in training.
        features = np.array([[1.0], [1.0], [-1.0], [-1.0]])
        targets = np.array([1.0, 1.0, 0.0, 0.0])
        groups = ["a", "a", "b", "b"]
        predictions = risk_mod.leave_one_group_out_predictions(
            features, targets, groups
        )
        np.testing.assert_allclose(predictions[:2], [0.0, 0.0])
        np.testing.assert_allclose(predictions[2:], [1.0, 1.0])


class BootstrapTests(unittest.TestCase):
    def test_clustered_rate_point_estimate_is_weighted(self):
        flags = np.array([1.0, 0.0])
        weights = np.array([3.0, 1.0])
        report = risk_mod.clustered_bootstrap_rate(
            flags, weights, ["s1", "s2"], iterations=50, seed=1
        )
        self.assertAlmostEqual(report["point"], 0.75)
        self.assertLessEqual(report["ci_2.5"], report["ci_97.5"])

    def test_clustered_auc_ci_brackets_point(self):
        scores = np.array([0.9, 0.8, 0.2, 0.1, 0.85, 0.15])
        labels = np.array([True, True, False, False, True, False])
        groups = ["a", "a", "b", "b", "c", "c"]
        report = risk_mod.clustered_bootstrap_auc(
            scores, labels, groups, iterations=100, seed=1
        )
        self.assertAlmostEqual(report["point"], 1.0)
        self.assertLessEqual(report["ci_2.5"], 1.0)


class RerankTests(unittest.TestCase):
    def test_lambda_moves_selection_from_risky_to_safe(self):
        rows = [
            release_row(
                candidate_id="risky",
                score=1.0,
                rotated=True,
                selected=True,
            ),
            release_row(candidate_id="safe", score=0.8),
        ]
        predictions = {
            ("snap-0", "risky"): 0.9,
            ("snap-0", "safe"): 0.05,
        }
        sweep = risk_mod.rerank_sweep(rows, predictions)
        by_lambda = {entry["lambda"]: entry for entry in sweep}
        self.assertEqual(by_lambda[0.0]["selected_rotated_over_30"], 1)
        self.assertEqual(by_lambda[0.0]["changed_vs_score_argmax"], 0)
        self.assertEqual(by_lambda[1.0]["selected_rotated_over_30"], 0)
        self.assertEqual(by_lambda[1.0]["changed_vs_score_argmax"], 1)
        self.assertAlmostEqual(
            by_lambda[1.0]["mean_score_opportunity_loss"],
            0.2,
            places=6,
        )
        self.assertEqual(
            by_lambda[1.0]["changed_vs_original_release_selection"], 1
        )
        self.assertEqual(by_lambda[1.0]["original_release_snapshots"], 1)

    def test_settled_rows_are_excluded_from_the_release_argmax(self):
        settled = {
            "kind": "candidate",
            "snapshot_id": "snap-0",
            "candidate_id": "settled",
            "score_immediate": 99.0,
            "selected": True,
            "phi_modelling": None,
            "sampling": {"sampling_weight": 1.0},
            "physical": {"d_xy": 0.0, "Y": {
                "rotated_over_30": False,
                "horizontal_displaced_over_half_footprint": False,
                "displaced_over_half_footprint": False,
                "not_placed_safe": False,
                "not_valid": False,
                "not_included": False,
                "physically_dangerous": False,
            }},
        }
        rows = [settled, release_row(candidate_id="only", score=0.5)]
        sweep = risk_mod.rerank_sweep(rows, {})
        entry = sweep[0]
        self.assertEqual(entry["snapshots"], 1)
        # The original selection was settled, so no release-selection
        # change is counted.
        self.assertEqual(entry["original_release_snapshots"], 0)


class ShadowPairTests(unittest.TestCase):
    def test_pairs_join_baseline_and_shadow_labels(self):
        baseline = release_row(
            candidate_id="base", rotated=True, unsafe=True, selected=True
        )
        baseline["candidate_id"] = "base"
        shadow = release_row(candidate_id="shadow")
        shadow["candidate_id"] = "shadow"
        summaries = [
            {
                "snapshot_id": "snap-0",
                "_split": "development",
                "shadow_pair": {
                    "changed": True,
                    "baseline_candidate_id": "base",
                    "shadow_candidate_id": "shadow",
                },
            },
            {
                "snapshot_id": "snap-1",
                "_split": "development",
                "shadow_pair": {
                    "changed": False,
                    "baseline_candidate_id": None,
                    "shadow_candidate_id": None,
                },
            },
        ]
        report = risk_mod.shadow_pair_report(summaries, [baseline, shadow])
        self.assertEqual(report["changed_snapshots"], 1)
        self.assertEqual(report["labelled_pairs"], 1)
        self.assertEqual(report["rotation_danger_difference"], 1)
        self.assertEqual(report["placed_safe_difference"], 1)
        self.assertEqual(report["safe_to_dangerous_reversals"], 0)
        self.assertEqual(report["dangerous_to_safe_conversions"], 1)
        self.assertAlmostEqual(
            report["mean_pair_score_loss"], 0.0, places=6
        )

    def test_safe_to_dangerous_reversal_is_counted(self):
        baseline = release_row(candidate_id="base", selected=True)
        baseline["candidate_id"] = "base"
        shadow = release_row(candidate_id="shadow", unsafe=True)
        shadow["candidate_id"] = "shadow"
        summaries = [
            {
                "snapshot_id": "snap-0",
                "_split": "development",
                "shadow_pair": {
                    "changed": True,
                    "baseline_candidate_id": "base",
                    "shadow_candidate_id": "shadow",
                },
            }
        ]
        report = risk_mod.shadow_pair_report(summaries, [baseline, shadow])
        self.assertEqual(report["safe_to_dangerous_reversals"], 1)
        self.assertEqual(report["placed_safe_difference"], -1)


class HoldoutExclusionTests(unittest.TestCase):
    def test_final_holdout_dataset_is_skipped_by_default(self):
        import json
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            base = pathlib.Path(tmp)
            for name, split in (
                ("dev", "development"),
                ("hold", "final_holdout"),
            ):
                directory = base / name
                directory.mkdir()
                (directory / "manifest.json").write_text(
                    json.dumps({"status": "complete", "split": split})
                )
                row = release_row(snapshot=name, candidate_id=name)
                row["snapshot_path"] = "step-000-state.json"
                row["item_index"] = 0
                (directory / "step-000-candidates.jsonl").write_text(
                    json.dumps(row) + "\n"
                )
            closed, _release, _summaries = risk_mod.load_release_rows(
                [base / "dev", base / "hold"]
            )
            self.assertEqual(
                {row["_split"] for row in closed}, {"development"}
            )
            opened, _release, _summaries = risk_mod.load_release_rows(
                [base / "dev", base / "hold"], open_final_holdout=True
            )
            self.assertEqual(
                {row["_split"] for row in opened},
                {"development", "final_holdout"},
            )


class VectorTests(unittest.TestCase):
    def test_item_vector_derives_density_and_aspect(self):
        row = {
            "_item": {
                "length": 0.5,
                "width": 0.4,
                "height": 0.2,
                "mass": 8.0,
                "lateralFriction": 0.6,
                "restitution": 0.1,
                "is_soft": True,
            }
        }
        vector = risk_mod.item_vector(row)
        self.assertAlmostEqual(vector[0], 8.0)
        self.assertAlmostEqual(vector[3], 1.0)
        self.assertAlmostEqual(vector[4], 8.0 / 0.04)
        self.assertAlmostEqual(vector[5], 0.2 / 0.5)

    def test_item_vector_none_without_item(self):
        self.assertIsNone(risk_mod.item_vector({"_item": None}))


if __name__ == "__main__":
    unittest.main()
