from __future__ import annotations

import unittest

from scripts.aggregate_task_b import aggregate_rows, build_aggregate_markdown
from scripts.summarize_task_b import SELECTED_CONFUSION_SCOPE


class TaskBAggregateTests(unittest.TestCase):
    def test_aggregates_replicates_and_failure_counts(self) -> None:
        rows = [
            {
                "look_ahead": 10,
                "selection_mode": "weighted",
                "coverage_mode": "class_aware",
                "risk_gate_mode": "enforce",
                "replicate": 1,
                "placed_count": 18,
                "fill_score": 20.0,
                "failure_mode": "fixed_fallback",
                "starvation_signal": True,
                "coverage": {
                    "overall": {"c1": 0.8, "c2": 0.9, "c3": 0.5},
                    "by_class": {},
                },
                "release": {
                    "gate_evaluated": 10,
                    "gate_would_reject": 4,
                    "gate_enforced_rejections": 4,
                    "selected_release_count": 1,
                    "rotation_over_30_count": 0,
                    "large_displacement_count": 0,
                    "physical_failure_count": 0,
                },
            },
            {
                "look_ahead": 10,
                "selection_mode": "weighted",
                "coverage_mode": "class_aware",
                "risk_gate_mode": "enforce",
                "replicate": 2,
                "placed_count": 20,
                "fill_score": 24.0,
                "failure_mode": "release_failure",
                "starvation_signal": False,
                "coverage": {
                    "overall": {"c1": 1.0, "c2": 0.8, "c3": 0.6},
                    "by_class": {},
                },
                "release": {
                    "gate_evaluated": 20,
                    "gate_would_reject": 8,
                    "gate_enforced_rejections": 8,
                    "selected_release_count": 2,
                    "rotation_over_30_count": 1,
                    "large_displacement_count": 1,
                    "physical_failure_count": 1,
                },
            },
            {
                "look_ahead": 10,
                "selection_mode": "weighted",
                "coverage_mode": "class_aware",
                "risk_gate_mode": "enforce",
                "replicate": 3,
                "placed_count": 16,
                "fill_score": 22.0,
                "failure_mode": "fixed_fallback",
                "starvation_signal": False,
                "coverage": {
                    "overall": {"c1": 0.9, "c2": 1.0, "c3": 0.4},
                    "by_class": {},
                },
                "release": {
                    "gate_evaluated": 15,
                    "gate_would_reject": 6,
                    "gate_enforced_rejections": 6,
                    "selected_release_count": 1,
                    "rotation_over_30_count": 0,
                    "large_displacement_count": 0,
                    "physical_failure_count": 0,
                },
            },
        ]

        aggregates = aggregate_rows(rows)
        markdown = build_aggregate_markdown(aggregates)

        result = aggregates[0]
        self.assertEqual(result["runs"], 3)
        self.assertEqual(result["placed"]["mean"], 18.0)
        self.assertEqual(result["placed"]["median"], 18.0)
        self.assertAlmostEqual(result["placed"]["stddev"], 2.0)
        self.assertEqual(result["placed"]["min"], 16)
        self.assertEqual(result["placed"]["max"], 20)
        self.assertEqual(
            result["failure_modes"],
            {"fixed_fallback": 2, "release_failure": 1},
        )
        self.assertEqual(result["starvation_signal_count"], 1)
        self.assertAlmostEqual(
            result["coverage"]["overall"]["c1"]["mean"],
            0.9,
        )
        self.assertEqual(result["risk_gate_mode"], "enforce")
        self.assertEqual(
            result["release"]["gate_evaluated"]["mean"],
            15.0,
        )
        self.assertIn(
            "| 10 | enforce | 0.0 | 0.0 | - | 0.0 | 0.0 | - | "
            "0.0 | 15.0 | 6.0 |",
            markdown,
        )
        self.assertIn("fixed_fallback=2", markdown)

    def test_selected_confusion_matrix_and_labels_reach_the_aggregate(
        self,
    ) -> None:
        def row(replicate: int, tp: int) -> dict:
            return {
                "look_ahead": 20,
                "selection_mode": "weighted",
                "coverage_mode": "class_aware",
                "risk_gate_mode": "shadow",
                "replicate": replicate,
                "placed_count": 17,
                "fill_score": 24.531,
                "failure_mode": "release_failure",
                "starvation_signal": False,
                "coverage": {"overall": {}, "by_class": {}},
                "release": {
                    "selected_gate_scored_count": 6,
                    "selected_gate_pass_physical_safe_count": 3,
                    "selected_gate_pass_physical_failure_count": 1,
                    "selected_gate_reject_physical_safe_count": 2,
                    "selected_gate_reject_physical_failure_count": tp,
                    "selected_gate_reject_count": 2 + tp,
                    "selected_gate_reject_physical_failure_rate": 0.5,
                    "selected_labelled_count": 6,
                    "selected_rotated_over_30_count": 1,
                    "selected_displaced_over_half_footprint_count": 2,
                    "selected_horizontal_displaced"
                    "_over_half_footprint_count": 1,
                    "selected_not_placed_safe_count": 1,
                    "selected_not_valid_count": 0,
                    "selected_not_included_count": 1,
                    "selected_physically_dangerous_count": 2,
                },
            }

        aggregates = aggregate_rows([row(1, 2), row(2, 4)])
        markdown = build_aggregate_markdown(aggregates)
        release = aggregates[0]["release"]

        self.assertEqual(
            release["selected_gate_reject_physical_failure_count"]["mean"],
            3.0,
        )
        self.assertEqual(
            release["selected_gate_pass_physical_safe_count"]["mean"], 3.0
        )
        self.assertEqual(
            release[
                "selected_horizontal_displaced_over_half_footprint_count"
            ]["mean"],
            1.0,
        )
        self.assertEqual(
            release["selected_not_included_count"]["mean"], 1.0
        )
        # The conditioning has to survive into the JSON too: analysis code
        # that never renders the Markdown would otherwise see four bare cells.
        scope = aggregates[0]["selected_confusion_scope"]
        self.assertIn("selected_release_candidates_only", scope)
        self.assertIn("not a gate-wide", scope)
        self.assertEqual(scope, SELECTED_CONFUSION_SCOPE)

        self.assertIn("### Selected-release confusion matrix means", markdown)
        self.assertIn("### Selected-release physical label means", markdown)
        # The conditioning must never be dropped from the report.
        self.assertIn("not** the gate's overall precision/recall", markdown)
        self.assertIn("stratified counterfactual replay dataset", markdown)
        self.assertIn("| 20 | shadow | 6.0 | 3.0 | 1.0 | 2.0 | 3.0 |", markdown)

    def test_off_shadow_action_mismatch_is_reported_as_blocker(self) -> None:
        rows = []
        for mode, digest in (("off", "old-action"), ("shadow", "changed")):
            rows.append(
                {
                    "look_ahead": 20,
                    "selection_mode": "weighted",
                    "coverage_mode": "class_aware",
                    "risk_gate_mode": mode,
                    "replicate": 1,
                    "placed_count": 1,
                    "fill_score": 1.0,
                    "coverage": {"overall": {}, "by_class": {}},
                    "release": {"action_sequence_sha256": digest},
                }
            )

        markdown = build_aggregate_markdown(aggregate_rows(rows))

        self.assertIn("| 20 | 1 | 0 | yes |", markdown)
