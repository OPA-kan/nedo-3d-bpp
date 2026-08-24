import copy
import unittest

from scripts.aggregate_single_agent_value_shadow import compare_pair


def payload(*, leaf):
    candidate = {
        "root_candidate_id": "a", "safe": True,
        "one_step_vector": {"fill_gain": 1.0},
        "terminal_genuine": True, "terminal_termination": "stream_exhausted",
        "terminal_vector": {"fill_gain": 4.0},
    }
    return {
        "contract": (
            "pareto_search_terminal_audit_v3" if leaf == "measured"
            else "pareto_puct_value_terminal_audit_v4"
        ),
        "case_id": "m-a", "leaf_eval": leaf, "terminal_audit": True,
        "allocation_mode": "pareto-puct", "max_depth": 2,
        "roots": [{
            "root_id": "r", "root_candidates": [candidate],
            "terminal_truth_complete": True,
            "terminal_frontier_resurrection_candidates": ["a"],
            "deepened_candidates": ["a"],
            "measured_search_pareto_candidates": ["a"],
            "evaluated_search_pareto_candidates": ["a"],
            "terminal_pareto_candidates": ["a"],
            "physical_steps": 2, "terminal_rollout_physical_steps": 3,
        }],
    }


class SingleAgentValueShadowAggregateTests(unittest.TestCase):
    def test_requires_identical_terminal_truth(self):
        zero, value = payload(leaf="measured"), payload(leaf="value")
        result = compare_pair(zero, value, cell="c")
        self.assertEqual(result["terminal_resurrection_actions"], 1)
        bad = copy.deepcopy(value)
        bad["roots"][0]["root_candidates"][0]["terminal_vector"] = {"fill_gain": 9.0}
        with self.assertRaisesRegex(ValueError, "evidence differs"):
            compare_pair(zero, bad, cell="c")

    def test_value_arm_is_scored_by_value_evaluated_not_measured_frontier(self):
        zero, value = payload(leaf="measured"), payload(leaf="value")
        value["roots"][0]["measured_search_pareto_candidates"] = []

        result = compare_pair(zero, value, cell="c")

        self.assertEqual(result["value"]["frontier_resurrection_actions"], 1)

    def test_rejects_non_h2_or_non_puct_arm(self):
        zero, value = payload(leaf="measured"), payload(leaf="value")
        value["max_depth"] = 3
        with self.assertRaisesRegex(ValueError, "not H2"):
            compare_pair(zero, value, cell="c")


if __name__ == "__main__":
    unittest.main()
