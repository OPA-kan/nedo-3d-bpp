import unittest

from scripts.run_vector_mcts import (
    _accumulate,
    _dominates,
    _oriented,
    pareto_frontier,
)
from scripts.beta_proposal import stratum_entropy


def vector(fill, soft=0.0, pc=0.0, pm=0.0, tv=0.0):
    return {
        "fill_gain": fill,
        "soft_violation_gain": soft,
        "priority_covered_gain": pc,
        "priority_misrouted_gain": pm,
        "surface_total_variation_delta": tv,
    }


class VectorSearchPrimitiveTests(unittest.TestCase):
    def test_orientation_flips_minimize_heads(self):
        oriented = _oriented(vector(2.0, soft=1.0))
        self.assertEqual(oriented[0], 2.0)
        self.assertEqual(oriented[1], -1.0)
        self.assertIsNone(_oriented({"fill_gain": 1.0}))

    def test_dominance_and_frontier_are_weight_free(self):
        vectors = {
            "a": _oriented(vector(3.0, soft=0.0)),
            "b": _oriented(vector(1.0, soft=0.0)),   # dominated by a
            "c": _oriented(vector(2.0, soft=-1.0)),  # tradeoff: on frontier
        }
        self.assertTrue(_dominates(vectors["a"], vectors["b"]))
        self.assertFalse(_dominates(vectors["a"], vectors["c"]))
        self.assertEqual(pareto_frontier(vectors), {"a", "c"})

    def test_accumulate_is_additive_and_censors_none(self):
        base = {"fill_gain": 1.0, "soft_violation_gain": 0.0}
        delta = {
            "fill_gain": {"value": 2.0},
            "soft_violation_gain": {"value": None},
        }
        accumulated = _accumulate(base, delta)
        self.assertEqual(accumulated["fill_gain"], 3.0)
        self.assertIsNone(accumulated["soft_violation_gain"])


class BetaProposalTests(unittest.TestCase):
    def test_stratum_entropy_zero_for_collapsed_proposals(self):
        row = {
            "selection": {"stable_item_index": 4},
            "command_action": {
                "container_idx": 0, "orientation": 1,
                "place_pos": [0, 0, 0],
            },
        }
        self.assertEqual(stratum_entropy([row, dict(row)]), 0.0)

    def test_stratum_entropy_grows_with_diversity(self):
        rows = [
            {
                "selection": {"stable_item_index": index},
                "command_action": {
                    "container_idx": 0, "orientation": 0,
                    "place_pos": [0, 0, 0],
                },
            }
            for index in range(4)
        ]
        self.assertGreater(stratum_entropy(rows), 1.0)


if __name__ == "__main__":
    unittest.main()
