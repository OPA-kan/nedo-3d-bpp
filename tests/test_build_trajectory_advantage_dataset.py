import json
import unittest

from scripts.build_trajectory_advantage_dataset import (
    build_trajectory_advantage_corpus,
    trajectory_advantage_rows,
)
from tests.test_summarize_counterfactual_graph_signal import graph_fixture


def advantage_graph():
    graph = graph_fixture()
    graph["future_stream_id"] = "stream-shared"
    graph["budget"] = {"horizon": 3, "branch_factor": 2}
    graph["edges"][0]["selection"].update({"rank": 0, "score": 999.0})
    graph["edges"][1]["selection"].update({"rank": 1, "score": -999.0})
    graph["nodes"][1]["terminal_reason"] = "physical_failure"
    graph["nodes"][1]["cumulative_outcomes"]["fill_score_proxy"] = 11.0
    graph["nodes"][2]["terminal_reason"] = None
    graph["nodes"][2]["cumulative_outcomes"].update({
        "placed_count": 13,
        "fill_score_proxy": 11.5,
        "soft_covered_by_other": 0,
    })
    graph["nodes"].append({
        **graph["nodes"][2],
        "node_id": "candidate-leaf",
        "depth": 3,
        "cumulative_outcomes": {
            **graph["nodes"][2]["cumulative_outcomes"],
            "placed_count": 14,
            "fill_score_proxy": 13.0,
        },
    })
    graph["edges"].append({
        "source": "high",
        "target": "candidate-leaf",
        "command_action": {
            "item_idx": 0,
            "container_idx": 0,
            "place_pos": [0.2, 0.2, 0.7],
            "orientation": 0,
        },
        "selection": {
            "rank": 0,
            "score": 0.5,
            "stable_item_index": 1,
            "candidate_kind": "settled_candidate",
        },
        "immediate_outcomes": {"is_placed_safe": True},
    })
    return graph


class TrajectoryAdvantageDatasetTests(unittest.TestCase):
    def test_exports_direct_candidate_advantage_over_rank_zero_incumbent(self):
        rows = trajectory_advantage_rows(
            advantage_graph(), policy_generation="pi0"
        )

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["incumbent_stable_item_index"], 1)
        self.assertEqual(row["candidate_stable_item_index"], 2)
        self.assertEqual(row["future_stream_id"], "stream-shared")
        self.assertTrue(row["split_group_id"].startswith("trajectory-group-"))
        self.assertIn(row["evaluation_fold"], range(5))
        self.assertEqual(row["policy_generation"], "pi0")
        self.assertEqual(
            row["advantage_heads"]["placed_count"]["raw_advantage"], 1.0
        )
        self.assertEqual(
            row["advantage_heads"]["fill_score_proxy"]["raw_advantage"],
            2.0,
        )
        self.assertEqual(
            row["advantage_heads"]["physical_failure_rate"]
            ["raw_advantage"],
            -1.0,
        )
        self.assertEqual(
            row["advantage_heads"]["horizon_survival_rate"]
            ["directed_advantage"],
            1.0,
        )
        self.assertEqual(
            row["candidate_trajectory_samples"][0]
            ["path_stable_item_indices"],
            [2, 1],
        )

    def test_model_inputs_exclude_the_hand_written_immediate_score(self):
        row = trajectory_advantage_rows(
            advantage_graph(), policy_generation="pi0"
        )[0]

        for key in ("incumbent_action_tensor", "candidate_action_tensor"):
            tensor = row[key]
            self.assertNotIn("immediate_score", tensor["feature_names"])
            self.assertEqual(
                tensor["contract"],
                "observed_candidate_action_no_heuristic_or_future_labels",
            )
        encoded_inputs = json.dumps({
            "source": row["source_state_tensor"],
            "incumbent": row["incumbent_action_tensor"],
            "candidate": row["candidate_action_tensor"],
        })
        self.assertNotIn("immediate_score", encoded_inputs)
        self.assertNotIn("999", encoded_inputs)

    def test_manifest_proves_graph_group_split_and_input_contract(self):
        graph = advantage_graph()
        second = advantage_graph()
        second["graph_id"] = "g2"
        second["root_step"] = 18

        manifest, rows = build_trajectory_advantage_corpus(
            [graph, second], policy_generation="pi0"
        )

        self.assertEqual(len(rows), 2)
        self.assertTrue(manifest["evaluation_group_fold_consistent"])
        self.assertEqual(
            manifest["split_group_contract"],
            "policy_generation x future_stream x case x scenario",
        )
        self.assertEqual(manifest["rows_with_immediate_score_input"], 0)
        self.assertEqual(
            {row["root_regime"] for row in rows},
            {"discovery", "late_holdout"},
        )
        self.assertEqual(
            len({row["split_group_id"] for row in rows}), 1,
            "roots from one physical trajectory must remain in one fold",
        )
        self.assertEqual(len({row["evaluation_fold"] for row in rows}), 1)

    def test_refuses_an_ambiguous_behaviour_incumbent(self):
        graph = advantage_graph()
        graph["edges"][1]["selection"]["rank"] = 0

        with self.assertRaisesRegex(ValueError, "exactly one rank-0 incumbent"):
            trajectory_advantage_rows(graph, policy_generation="pi0")


if __name__ == "__main__":
    unittest.main()
