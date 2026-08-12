from __future__ import annotations

import unittest

from scripts.evaluate_counterfactual_teacher_cross_run import (
    _action_delta,
    evaluate_cross_run,
)
from tests.test_evaluate_counterfactual_teacher_discovery import row


def run(run_id: str, sign: float):
    discovery = [
        row(f"{run_id}-d1", f"{run_id}-g1", -0.3 * sign, "lower_immediate_score_better"),
        row(f"{run_id}-d2", f"{run_id}-g2", 0.3 * sign, "higher_immediate_score_better"),
    ]
    late = [
        row(f"{run_id}-h", f"{run_id}-g3", 0.2 * sign, "higher_immediate_score_better")
    ]
    for example in discovery + late:
        relation = example["labels"]["fill_score_proxy"]
        example["labels"]["com_z"] = relation
        example["labels"]["surface_total_variation"] = relation
    return {"run_id": run_id, "discovery": discovery, "late": late}


class CrossRunCounterfactualTeacherTests(unittest.TestCase):
    def test_holds_out_each_complete_run(self):
        report = evaluate_cross_run([run("1", 1.0), run("2", 1.0)])

        self.assertEqual(len(report["targets"]), 2)
        self.assertEqual(report["targets"][0]["training_run_ids"], ["2"])
        self.assertEqual(
            report["pooled_exact_counts"]["fill_score_proxy"]
            ["cross_run_action_ridge"]["total"],
            2,
        )
        self.assertEqual(
            report["pooled_pareto_shadow"]["immediate_higher"]["pairs"],
            2,
        )
        self.assertEqual(
            report["pooled_exact_counts"]["fill_score_proxy"]
            ["cross_run_geometry_ridge"]["total"],
            2,
        )

    def test_requires_unique_independent_runs(self):
        with self.assertRaisesRegex(ValueError, "unique"):
            evaluate_cross_run([run("same", 1.0), run("same", -1.0)])

    def test_action_delta_negates_when_candidate_values_are_swapped(self):
        example = run("1", 1.0)["late"][0]
        forward = _action_delta(example, include_score=False)
        example["lower_action_tensor"], example["higher_action_tensor"] = (
            example["higher_action_tensor"], example["lower_action_tensor"]
        )
        backward = _action_delta(example, include_score=False)

        self.assertEqual(backward, [-value for value in forward])


if __name__ == "__main__":
    unittest.main()
