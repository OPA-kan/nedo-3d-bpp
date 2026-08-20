from __future__ import annotations

import copy
import unittest

from scripts.analyze_counterfactual_sensitivity_regimes import (
    aggregate_source_sensitivities,
    evaluate_sensitivity_regimes,
    fit_sensitivity_regimes,
    physical_response_vector,
)


METRIC = "post_shake_soft_covered_by_other"


def state(*, x: float = 0.0, z: float = 0.1, soft: float = 0.0) -> dict:
    return {
        "container_features": ["length", "width", "height"],
        "container_values": [[2.0, 1.0, 1.5]],
        "packed_item_features": [
            "container_index", "local_x", "local_y", "local_z",
            "length", "width", "height", "mass", "is_prioritized", "is_soft",
        ],
        "packed_item_values": [[0, x, 0, z, 0.4, 0.4, 0.2, 2, 0, soft]],
        "visible_item_features": [],
        "visible_item_values": [],
    }


def row(
    teacher_id: str,
    node: str,
    lower: dict,
    higher: dict,
    relation: str,
) -> dict:
    return {
        "teacher_id": teacher_id,
        "case_id": "case",
        "graph_id": "graph",
        "root_step": 12,
        "source_node_id": node,
        "source_state_tensor": state(),
        "lower_action_tensor": {"values": [teacher_id, "lower"]},
        "higher_action_tensor": {"values": [teacher_id, "higher"]},
        "lower_afterstate_tensor": lower,
        "higher_afterstate_tensor": higher,
        "distributional_continuation_labels": {
            METRIC: {"relation": relation},
        },
    }


class CounterfactualSensitivityRegimeTests(unittest.TestCase):
    def test_physical_response_is_invariant_to_pair_order(self) -> None:
        lower = state(x=0.0, z=0.1, soft=1.0)
        higher = state(x=0.7, z=0.5, soft=1.0)
        forward = row("a", "n", lower, higher, "higher_afterstate_better")
        reverse = row("b", "n", higher, lower, "lower_afterstate_better")

        self.assertEqual(
            physical_response_vector(forward),
            physical_response_vector(reverse),
        )

    def test_source_sensitivity_uses_equal_pairs_but_labels_only_directional(self) -> None:
        rows = [
            row("a", "n", state(), state(x=0.4), "equal"),
            row("b", "n", state(), state(z=0.5), "higher_afterstate_better"),
        ]

        groups = aggregate_source_sensitivities(rows)

        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["candidate_pairs"], 2)
        self.assertEqual(groups[0]["directional_rows"], 1)

    def test_regime_discovery_is_label_blind(self) -> None:
        rows = []
        for index, x in enumerate((0.02, 0.04, 0.7, 0.8)):
            relation = (
                "lower_afterstate_better" if index < 2
                else "higher_afterstate_better"
            )
            rows.append(row(str(index), f"n{index}", state(), state(x=x), relation))
        relabeled = copy.deepcopy(rows)
        for item in relabeled:
            current = item["distributional_continuation_labels"][METRIC]
            current["relation"] = (
                "higher_afterstate_better"
                if current["relation"] == "lower_afterstate_better"
                else "lower_afterstate_better"
            )

        first = fit_sensitivity_regimes(
            {"source_run_id": "train"}, rows, k_candidates=(2,)
        )
        second = fit_sensitivity_regimes(
            {"source_run_id": "train"}, relabeled, k_candidates=(2,)
        )

        self.assertEqual(first["normalization"], second["normalization"])
        self.assertEqual(first["centroids"], second["centroids"])
        self.assertNotEqual(
            first["cluster_relations"], second["cluster_relations"]
        )

    def test_singleton_cluster_is_not_supported_as_a_regime(self) -> None:
        rows = [
            row(str(index), f"n{index}", state(), state(x=x), "higher_afterstate_better")
            for index, x in enumerate((0.01, 0.02, 0.03, 0.04, 0.9))
        ]

        policy = fit_sensitivity_regimes(
            {"source_run_id": "train"}, rows, k_candidates=(2,)
        )

        self.assertFalse(policy["regime_structure_supported"])
        self.assertEqual(policy["minimum_source_states_per_regime"], 2)

    def test_unsupported_structure_cannot_pass_even_when_predictions_win(self) -> None:
        training = [
            row(str(index), f"train-{index}", state(), state(x=x), "higher_afterstate_better")
            for index, x in enumerate((0.01, 0.02, 0.03, 0.04, 0.9))
        ]
        policy = fit_sensitivity_regimes(
            {"source_run_id": "train"}, training, k_candidates=(2,)
        )
        policy["cluster_relations"] = {
            key: "lower_afterstate_better" for key in policy["cluster_relations"]
        }
        target = [
            row(
                f"target-{index}", f"target-{index}", state(),
                state(x=0.1 + index / 100), "lower_afterstate_better",
            )
            for index in range(20)
        ]

        report = evaluate_sensitivity_regimes(
            policy, {"source_run_id": "target"}, target
        )

        self.assertEqual(report["models"]["sensitivity_regime"]["correct"], 20)
        self.assertEqual(report["models"]["immediate_score"]["correct"], 0)
        self.assertFalse(report["promotion_gate"]["passed"])


if __name__ == "__main__":
    unittest.main()
