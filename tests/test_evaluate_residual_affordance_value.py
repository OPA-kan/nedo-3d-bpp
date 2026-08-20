from __future__ import annotations

import unittest

from scripts.evaluate_residual_affordance_value import (
    LABEL_FAMILY,
    PARETO_METRIC,
    affordance_summary,
    evaluate_phase_hybrid_candidate,
    evaluate_replication_candidate,
    freeze_replication_candidate,
    pareto_relation,
    phase_hybrid_predictions,
)


def afterstate(items: list[tuple[int, float, float, float, float, float]]) -> dict:
    return {
        "visible_item_features": [
            "length", "width", "height", "is_prioritized", "is_soft",
        ],
        "visible_item_indices": [item[0] for item in items],
        "visible_item_values": [list(item[1:]) for item in items],
    }


class ResidualAffordanceValueTests(unittest.TestCase):
    def test_summary_measures_safe_paths_and_attribute_breadth(self) -> None:
        state = afterstate([
            (1, 0.5, 0.4, 0.3, 0, 1),
            (2, 0.8, 0.5, 0.4, 1, 0),
            (3, 0.3, 0.3, 0.2, 0, 0),
        ])
        samples = [
            {
                "terminal_reason": "horizon",
                "path_stable_item_indices": [1, 2],
                "search_policy_weight": 0.5,
            },
            {
                "terminal_reason": "physical_failure",
                "path_stable_item_indices": [3, 2],
                "search_policy_weight": 0.5,
            },
        ]

        values = affordance_summary(samples, state)

        self.assertEqual(values[0], 1.5)
        self.assertEqual(values[1], 0.5)
        self.assertEqual(values[2:7], [2.0, 3.0, 2.0, 1.0, 1.0])
        self.assertAlmostEqual(values[7], 0.8 * 0.5 * 0.4)

    def test_failed_first_action_does_not_count_as_affordance(self) -> None:
        values = affordance_summary([
            {
                "terminal_reason": "physical_failure",
                "path_stable_item_indices": [1],
                "search_policy_weight": 1.0,
            }
        ], afterstate([(1, 1, 1, 1, 0, 0)]))

        self.assertEqual(values, [0.0] * 8)

    def test_pareto_relation_requires_no_regressions(self) -> None:
        self.assertEqual(
            pareto_relation([1, 2, 3], [1, 2, 4]),
            "higher_afterstate_better",
        )
        self.assertEqual(
            pareto_relation([1, 3, 3], [2, 2, 4]),
            "tradeoff",
        )
        self.assertEqual(pareto_relation([1, 2], [1, 2]), "equal")

    def test_metric_name_declares_searched_affordance_proxy(self) -> None:
        self.assertEqual(PARETO_METRIC, "searched_residual_affordance_pareto")

    def test_replication_candidate_requires_observed_action_gain(self) -> None:
        policy = {
            "source_run_id": "train",
            "action_model": {"weights": []},
            "training_teacher_signatures": [],
        }
        report = {
            "directional_rows": 20,
            "prospective_signal": {
                "non_immediate_model_beats_immediate": False,
            },
            "models": {
                "immediate_score": {"correct": 10},
                "action_geometry": {"correct": 10},
            },
        }

        with self.assertRaisesRegex(ValueError, "action gain"):
            freeze_replication_candidate(policy, "discovery", [], report)

    def test_replication_rejects_training_or_discovery_run(self) -> None:
        candidate = {
            "status": "prospective_replication_only",
            "training_run_id": "train",
            "discovery_run_id": "discovery",
        }

        with self.assertRaisesRegex(ValueError, "third physical run"):
            evaluate_replication_candidate(candidate, "discovery", [], {})

    def test_phase_hybrid_requires_a_fourth_run(self) -> None:
        candidate = {
            "status": "prospective_phase_hybrid_only",
            "training_run_id": "train",
            "discovery_run_id": "discovery",
            "replication_run_id": "replication",
        }

        with self.assertRaisesRegex(ValueError, "fourth physical run"):
            evaluate_phase_hybrid_candidate(candidate, "replication", [], {})

    def test_phase_hybrid_uses_action_only_through_declared_step(self) -> None:
        rows = [
            {"teacher_id": "early", "root_step": 6},
            {"teacher_id": "late", "root_step": 12},
        ]

        predictions = phase_hybrid_predictions(
            rows,
            {"early": "action", "late": "action"},
            {"early": "immediate", "late": "immediate"},
            maximum_root_step=6,
        )

        self.assertEqual(predictions, {"early": "action", "late": "immediate"})


if __name__ == "__main__":
    unittest.main()
