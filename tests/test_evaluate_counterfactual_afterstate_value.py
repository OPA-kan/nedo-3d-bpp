from __future__ import annotations

import unittest

from scripts.evaluate_counterfactual_afterstate_value import (
    _exact_two_sided_sign_p,
    _state_delta,
    evaluate,
)
from tests.test_evaluate_counterfactual_teacher_discovery import action, state


def row(name: str, graph: str, delta: float, relation: str) -> dict:
    lower = state(0.0)
    higher = state(delta)
    return {
        "teacher_id": name,
        "graph_id": graph,
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
    def test_state_delta_negates_when_afterstates_are_swapped(self) -> None:
        example = row("x", "g", 0.2, "higher_afterstate_better")
        forward = _state_delta(example)
        pair = (
            example["higher_afterstate_tensor"],
            example["lower_afterstate_tensor"],
        )
        self.assertEqual(_state_delta(example, pair), [-value for value in forward])

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

    def test_rejects_duplicate_run_ids(self) -> None:
        with self.assertRaisesRegex(ValueError, "unique"):
            evaluate([run("same"), run("same")])

    def test_exact_sign_test_uses_only_discordant_rows(self) -> None:
        self.assertEqual(_exact_two_sided_sign_p(4, 0), 0.125)
        self.assertEqual(_exact_two_sided_sign_p(3, 1), 0.625)
        self.assertEqual(_exact_two_sided_sign_p(0, 0), 1.0)


if __name__ == "__main__":
    unittest.main()
