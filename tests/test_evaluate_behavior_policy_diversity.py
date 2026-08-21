from __future__ import annotations

import copy
import unittest

from scripts.evaluate_behavior_policy_diversity import evaluate_diversity
from tests.test_evaluate_budgeted_dag_search import search_graph


def tagged_graph(mode: str, *, board: str, future_sensitive: bool) -> dict:
    graph = copy.deepcopy(search_graph())
    graph["graph_id"] = f"{mode}-{board}"
    graph["case_id"] = "case-a"
    graph["root_step"] = 12
    graph["provenance"] = {
        "behavior_policy": {"mode": mode},
        "model_visible_state_signature": f"model-{board}",
    }
    graph["nodes"][0]["board_fingerprint"] = board
    if future_sensitive:
        graph["nodes"][1]["cumulative_outcomes"]["fill_score_proxy"] = 6.0
        graph["nodes"][2]["cumulative_outcomes"]["fill_score_proxy"] = 2.0
    return graph


class BehaviorPolicyDiversityEvaluationTests(unittest.TestCase):
    def test_counts_unique_states_and_new_reversal_from_alternative_policy(self):
        report = evaluate_diversity([
            tagged_graph("baseline", board="a", future_sensitive=False),
            tagged_graph("force-rank1", board="b", future_sensitive=True),
            tagged_graph("force-rank2", board="c", future_sensitive=False),
            tagged_graph("safe-temperature", board="c", future_sensitive=False),
        ])
        group = report["groups"][0]
        self.assertEqual(group["unique_board_fingerprints"], 3)
        self.assertEqual(group["unique_model_visible_states"], 3)
        self.assertTrue(group["new_future_sensitive_state_found"])
        self.assertEqual(report["groups_with_new_future_sensitive_state"], 1)


if __name__ == "__main__":
    unittest.main()
