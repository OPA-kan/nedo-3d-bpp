from __future__ import annotations

import unittest
import json
import pathlib
import tempfile

from scripts.evaluate_counterfactual_afterstate_value import (
    _exact_two_sided_sign_p,
    _state_delta,
    _state_block_delta,
    evaluate,
    load_run,
)
from tests.test_evaluate_counterfactual_teacher_discovery import action, state


def row(name: str, graph: str, delta: float, relation: str) -> dict:
    lower = state(0.0)
    higher = state(delta)
    return {
        "teacher_id": name,
        "graph_id": graph,
        "equal_immediate_score": False,
        "lower_action_tensor": action(-0.3, 1.0),
        "higher_action_tensor": action(0.3, 2.0),
        "lower_afterstate_tensor": lower,
        "higher_afterstate_tensor": higher,
        "continuation_labels": {
            metric: {"relation": relation}
            for metric in (
                "placed_count", "fill_score_proxy", "com_z",
                "surface_total_variation", "priority_misrouted",
                "soft_covered_by_other",
            )
        },
        "distributional_continuation_labels": {
            metric: {"relation": relation}
            for metric in (
                "placed_count", "fill_score_proxy", "com_z",
                "surface_total_variation", "priority_misrouted",
                "soft_covered_by_other",
            )
        },
    }


def run(run_id: str) -> dict:
    return {
        "run_id": run_id,
        "discovery": [
            row(f"{run_id}-d1", "g1", -0.3, "lower_afterstate_better"),
            row(f"{run_id}-d2", "g2", 0.3, "higher_afterstate_better"),
        ],
        "late": [
            row(f"{run_id}-h", "g3", 0.2, "higher_afterstate_better")
        ],
    }


class CounterfactualAfterstateValueTests(unittest.TestCase):
    def test_loader_normalizes_legacy_float_roundoff_label(self) -> None:
        example = row("x", "g", 0.2, "lower_afterstate_better")
        label = example["continuation_labels"]["fill_score_proxy"]
        label.update({
            "lower_best_continuation": 1.8249423006277077,
            "higher_best_continuation": 1.8249423006277041,
        })
        for metric, other in example["continuation_labels"].items():
            other.setdefault("lower_best_continuation", 0)
            other.setdefault("higher_best_continuation", 1)
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            (root / "manifest.json").write_text(
                json.dumps({"schema_version": 4, "source_run_id": "r"}),
                encoding="utf-8",
            )
            payload = json.dumps(example) + "\n"
            (root / "discovery.jsonl").write_text(payload, encoding="utf-8")
            (root / "late_holdout.jsonl").write_text(payload, encoding="utf-8")
            loaded = load_run(root)

        self.assertEqual(
            loaded["late"][0]["continuation_labels"]["fill_score_proxy"]
            ["relation"],
            "equal",
        )

    def test_loader_uses_dedicated_distributional_splits(self) -> None:
        optimistic = row("old", "g", 0.2, "lower_afterstate_better")
        distributional = row("new", "g", 0.2, "higher_afterstate_better")
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            (root / "manifest.json").write_text(
                json.dumps({"schema_version": 5, "source_run_id": "r"}),
                encoding="utf-8",
            )
            for name, value in (
                ("discovery", optimistic), ("late_holdout", optimistic),
                ("distributional_discovery", distributional),
                ("distributional_late_holdout", distributional),
            ):
                (root / f"{name}.jsonl").write_text(
                    json.dumps(value) + "\n", encoding="utf-8"
                )

            loaded = load_run(
                root, label_family="distributional_continuation_labels"
            )

        self.assertEqual(loaded["discovery"][0]["teacher_id"], "new")
        self.assertEqual(loaded["late"][0]["teacher_id"], "new")

    def test_state_delta_negates_when_afterstates_are_swapped(self) -> None:
        example = row("x", "g", 0.2, "higher_afterstate_better")
        forward = _state_delta(example)
        pair = (
            example["higher_afterstate_tensor"],
            example["lower_afterstate_tensor"],
        )
        self.assertEqual(_state_delta(example, pair), [-value for value in forward])

    def test_named_state_blocks_are_strict_subsets(self) -> None:
        example = row("x", "g", 0.2, "higher_afterstate_better")

        self.assertEqual(len(_state_block_delta(example, "packed")), 37)
        self.assertEqual(len(_state_block_delta(example, "packed_visible")), 62)

    def test_holds_out_each_complete_physical_run(self) -> None:
        report = evaluate([run("1"), run("2")])

        self.assertEqual(len(report["targets"]), 2)
        self.assertEqual(report["targets"][0]["training_run_ids"], ["2"])
        pooled = report["pooled_exact_counts"]["placed_count"]
        self.assertEqual(pooled["afterstate"], {"correct": 2, "total": 2})
        self.assertEqual(
            report["permuted_afterstate_negative_control"]["placed_count"]["total"],
            2,
        )
        selective = report["fill_selective_consensus"]
        self.assertIn("retrospective", selective["selection_warning"])
        self.assertEqual(selective["late_retrospective"]["total"], 2)

    def test_can_evaluate_only_a_preregistered_target_run(self) -> None:
        report = evaluate(
            [run("1"), run("2"), run("3")], target_run_ids={"3"}
        )

        self.assertEqual(report["evaluated_target_run_ids"], ["3"])
        self.assertEqual(len(report["targets"]), 1)
        self.assertEqual(report["targets"][0]["training_run_ids"], ["1", "2"])
        self.assertEqual(
            report["pooled_exact_counts"]["fill_score_proxy"]["afterstate"],
            {"correct": 1, "total": 1},
        )

    def test_can_evaluate_distributional_pessimistic_label_family(self) -> None:
        report = evaluate(
            [run("1"), run("2")],
            label_family="distributional_continuation_labels",
        )

        self.assertEqual(
            report["label_family"], "distributional_continuation_labels"
        )
        self.assertIn("uniform-searched-action", report["target"])
        self.assertEqual(
            report["pooled_exact_counts"]["fill_score_proxy"]["afterstate"],
            {"correct": 2, "total": 2},
        )

    def test_equal_immediate_score_abstains_in_distributional_baseline(self) -> None:
        runs = [run("1"), run("2")]
        for item in runs:
            item["late"][0]["equal_immediate_score"] = True
        report = evaluate(
            runs, label_family="distributional_continuation_labels"
        )

        immediate = report["pooled_exact_counts"]["fill_score_proxy"][
            "immediate_score"
        ]
        self.assertEqual(immediate, {"correct": 0, "total": 2})
        self.assertEqual(
            report["immediate_score_abstentions"]["fill_score_proxy"], 2
        )

    def test_rejects_duplicate_run_ids(self) -> None:
        with self.assertRaisesRegex(ValueError, "unique"):
            evaluate([run("same"), run("same")])

    def test_exact_sign_test_uses_only_discordant_rows(self) -> None:
        self.assertEqual(_exact_two_sided_sign_p(4, 0), 0.125)
        self.assertEqual(_exact_two_sided_sign_p(3, 1), 0.625)
        self.assertEqual(_exact_two_sided_sign_p(0, 0), 1.0)


if __name__ == "__main__":
    unittest.main()
