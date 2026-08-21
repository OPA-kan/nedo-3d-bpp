import unittest

from scripts.build_trajectory_advantage_dataset import trajectory_advantage_rows
from scripts.evaluate_trajectory_advantage_value import (
    evaluate_metric,
    feature_vector,
    fit_ridge,
    predict,
)
from tests.test_build_trajectory_advantage_dataset import advantage_graph


def rows_for_groups():
    rows = []
    for index in range(3):
        graph = advantage_graph()
        graph["graph_id"] = f"g-{index}"
        graph["future_stream_id"] = f"stream-{index}"
        row = trajectory_advantage_rows(graph, policy_generation="pi0")[0]
        row["candidate_action_tensor"]["values"][1] += index * 0.1
        rows.append(row)
    return rows


class TrajectoryAdvantageValueTests(unittest.TestCase):
    def test_pair_features_are_candidate_minus_incumbent_and_score_free(self):
        row = rows_for_groups()[0]
        values = feature_vector(row, "action")

        self.assertEqual(
            len(values), len(row["candidate_action_tensor"]["feature_names"])
        )
        self.assertNotIn(
            "immediate_score", row["candidate_action_tensor"]["feature_names"]
        )
        self.assertAlmostEqual(
            values[1],
            row["candidate_action_tensor"]["values"][1]
            - row["incumbent_action_tensor"]["values"][1],
        )

    def test_ridge_predicts_in_directed_outcome_units(self):
        rows = rows_for_groups()
        model = fit_ridge(rows, "fill_score_proxy", "action")

        self.assertGreater(predict(model, rows[0]), 0.0)

    def test_evaluation_holds_out_complete_trajectory_groups(self):
        rows = rows_for_groups()
        result = evaluate_metric(rows, "fill_score_proxy", "action")

        self.assertEqual(result["group_count"], 3)
        self.assertEqual(result["row_count"], 3)
        self.assertEqual(result["directional_rows"], 3)
        self.assertEqual(set(result["per_group_directional"]), {
            row["split_group_id"] for row in rows
        })


if __name__ == "__main__":
    unittest.main()
