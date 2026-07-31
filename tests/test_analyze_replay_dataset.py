import importlib.util
import pathlib
import sys
import unittest


MODULE_PATH = (
    pathlib.Path(__file__).parents[1] / "scripts" / "analyze_replay_dataset.py"
)
SPEC = importlib.util.spec_from_file_location(
    "analyze_replay_dataset", MODULE_PATH
)
analyze_mod = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = analyze_mod
SPEC.loader.exec_module(analyze_mod)


def release_row(
    snapshot="snap-0",
    gate_passed=True,
    not_placed_safe=False,
    weight=1.0,
    support_ratio=0.5,
    band="top10",
):
    return {
        "kind": "release_candidate",
        "snapshot_id": snapshot,
        "gate_passed": gate_passed,
        "phi_modelling": {"support_ratio": support_ratio},
        "stratum": {"score_band": band},
        "sampling": {
            "stratum_key": f"kind=release_candidate|band={band}",
            "sampling_weight": weight,
        },
        "physical": {
            "delta_theta_deg": 45.0 if not_placed_safe else 1.0,
            "d_xy": 0.4 if not_placed_safe else 0.01,
            "d_z": 0.02,
            "Y": {
                "rotated_over_30": not_placed_safe,
                "horizontal_displaced_over_half_footprint": False,
                "displaced_over_half_footprint": False,
                "not_placed_safe": not_placed_safe,
                "not_valid": False,
                "not_included": False,
                "physically_dangerous": not_placed_safe,
            },
        },
        "_dataset_dir": "test",
    }


class RankAndCorrelationTests(unittest.TestCase):
    def test_average_ranks_handles_ties(self):
        self.assertEqual(
            analyze_mod.average_ranks([10.0, 20.0, 20.0, 30.0]),
            [1.0, 2.5, 2.5, 4.0],
        )

    def test_spearman_is_one_for_monotonic_data(self):
        x = [1.0, 2.0, 3.0, 4.0, 5.0]
        y = [10.0, 100.0, 1000.0, 10000.0, 100000.0]
        self.assertAlmostEqual(analyze_mod.spearman(x, y), 1.0)

    def test_spearman_is_minus_one_for_reversed_data(self):
        x = [1.0, 2.0, 3.0, 4.0]
        y = [4.0, 3.0, 2.0, 1.0]
        self.assertAlmostEqual(analyze_mod.spearman(x, y), -1.0)

    def test_spearman_requires_variance_and_size(self):
        self.assertIsNone(analyze_mod.spearman([1.0, 1.0, 1.0], [1, 2, 3]))
        self.assertIsNone(analyze_mod.spearman([1.0, 2.0], [1.0, 2.0]))


class WeightingTests(unittest.TestCase):
    def test_weighted_rate_uses_sampling_weights(self):
        pairs = [(True, 3.0), (False, 1.0)]
        self.assertAlmostEqual(analyze_mod.weighted_rate(pairs), 0.75)

    def test_weighted_rate_empty_is_none(self):
        self.assertIsNone(analyze_mod.weighted_rate([]))

    def test_quartile_edges_are_monotonic(self):
        edges = analyze_mod.quartile_edges([5.0, 1.0, 3.0, 2.0, 4.0])
        self.assertEqual(edges, sorted(edges))
        self.assertEqual(analyze_mod.quartile_index(0.0, edges), 0)
        self.assertEqual(analyze_mod.quartile_index(99.0, edges), 3)


class ConfusionTests(unittest.TestCase):
    def test_confusion_counts_reject_as_positive_prediction(self):
        rows = [
            release_row(gate_passed=False, not_placed_safe=True),   # TP
            release_row(gate_passed=False, not_placed_safe=False),  # FP
            release_row(gate_passed=True, not_placed_safe=True),    # FN
            release_row(gate_passed=True, not_placed_safe=False),   # TN
        ]
        report = analyze_mod.confusion_report(rows, "not_placed_safe")
        self.assertEqual(
            report["counts"], {"tp": 1, "fp": 1, "fn": 1, "tn": 1}
        )
        self.assertAlmostEqual(report["reject_precision"], 0.5)
        self.assertAlmostEqual(report["reject_recall"], 0.5)
        self.assertAlmostEqual(report["danger_rate_among_passed"], 0.5)

    def test_confusion_weights_move_rates_not_counts(self):
        rows = [
            release_row(gate_passed=True, not_placed_safe=True, weight=9.0),
            release_row(gate_passed=True, not_placed_safe=False, weight=1.0),
        ]
        report = analyze_mod.confusion_report(rows, "not_placed_safe")
        self.assertEqual(report["counts"], {"tp": 0, "fp": 0, "fn": 1, "tn": 1})
        self.assertAlmostEqual(report["danger_rate_among_passed"], 0.9)


class WithinSnapshotTests(unittest.TestCase):
    def test_contrast_uses_only_snapshots_with_both_outcomes(self):
        rows = [
            release_row(snapshot="a", not_placed_safe=False, support_ratio=0.9),
            release_row(snapshot="a", not_placed_safe=True, support_ratio=0.2),
            release_row(snapshot="b", not_placed_safe=False, support_ratio=0.5),
        ]
        contrast = analyze_mod.within_snapshot_contrast(
            rows, ["support_ratio"]
        )
        self.assertEqual(contrast["snapshots_with_both"], 1)
        feature = contrast["features"]["support_ratio"]
        self.assertAlmostEqual(
            feature["mean_diff_safe_minus_dangerous"], 0.7
        )
        self.assertEqual(feature["positive"], 1)


class AucTests(unittest.TestCase):
    def test_rank_auc_perfect_separation_is_one(self):
        self.assertAlmostEqual(
            analyze_mod.rank_auc(
                [0.1, 0.2, 0.8, 0.9], [False, False, True, True]
            ),
            1.0,
        )

    def test_rank_auc_handles_ties_as_half_credit(self):
        self.assertAlmostEqual(
            analyze_mod.rank_auc([0.5, 0.5], [True, False]), 0.5
        )

    def test_rank_auc_single_class_is_none(self):
        self.assertIsNone(analyze_mod.rank_auc([0.1, 0.2], [True, True]))


class GateReasonTests(unittest.TestCase):
    def test_reasons_split_by_actual_outcome(self):
        rows = [
            release_row(gate_passed=False, not_placed_safe=True),
            release_row(gate_passed=False, not_placed_safe=False),
            release_row(gate_passed=True, not_placed_safe=False),
        ]
        rows[0]["gate_reasons"] = ["support"]
        rows[1]["gate_reasons"] = ["support", "com_margin"]
        rows[2]["gate_reasons"] = []
        report = analyze_mod.gate_reason_report(rows)
        self.assertEqual(
            report["support"],
            {"rejected_dangerous": 1, "rejected_safe": 1},
        )
        self.assertEqual(
            report["com_margin"],
            {"rejected_dangerous": 0, "rejected_safe": 1},
        )


class SupportSweepTests(unittest.TestCase):
    def test_sweep_counts_only_rows_above_threshold(self):
        rows = [
            release_row(support_ratio=0.95, not_placed_safe=False),
            release_row(support_ratio=0.55, not_placed_safe=True),
            release_row(support_ratio=0.10, not_placed_safe=True),
        ]
        sweep = analyze_mod.support_sweep_report(rows)
        by_threshold = {
            entry["min_support_ratio"]: entry for entry in sweep
        }
        self.assertEqual(by_threshold[0.9]["n"], 1)
        self.assertAlmostEqual(
            by_threshold[0.9]["rate_not_placed_safe"], 0.0
        )
        self.assertEqual(by_threshold[0.5]["n"], 2)
        self.assertAlmostEqual(
            by_threshold[0.5]["rate_not_placed_safe"], 0.5
        )


class EndToEndTests(unittest.TestCase):
    def test_analyze_and_render_run_on_synthetic_rows(self):
        rows = [
            release_row(gate_passed=False, not_placed_safe=True,
                        support_ratio=0.1, band="tail"),
            release_row(gate_passed=True, not_placed_safe=False,
                        support_ratio=0.9, band="top1"),
            release_row(gate_passed=True, not_placed_safe=False,
                        support_ratio=0.7, band="top10"),
            release_row(gate_passed=False, not_placed_safe=False,
                        support_ratio=0.3, band="tail"),
        ]
        result = analyze_mod.analyze(rows)
        self.assertEqual(result["row_count"], 4)
        markdown = analyze_mod.render_markdown(result)
        self.assertIn("Gate verdict split", markdown)
        self.assertIn("support_ratio", markdown)


if __name__ == "__main__":
    unittest.main()
