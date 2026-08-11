from __future__ import annotations

import unittest

import numpy as np

from scripts.measure_residual_space import (
    board_pairs,
    command_record,
    observed_record,
    spearman,
)


def example(
    *,
    board: str,
    index: int,
    center: list[float],
    settled: list[float] | None,
) -> dict:
    return {
        "state": board,
        "case_id": "m-a",
        "pool_index": index,
        "item_index": index,
        "container_index": 0,
        "orientation": 0,
        "kind": "release_candidate",
        "center": center,
        "size": [0.3, 0.2, 0.2],
        "release_risk": {"features": {}},
        "x_plus": (
            None
            if settled is None
            else {
                "position": settled,
                "aabb_dimensions": [0.3, 0.2, 0.2],
                "quaternion": [0.0, 0.0, 0.0, 1.0],
            }
        ),
    }


class SpearmanTests(unittest.TestCase):
    def test_perfect_and_inverted_orderings(self):
        self.assertAlmostEqual(spearman([1, 2, 3, 4], [1, 2, 3, 4]), 1.0)
        self.assertAlmostEqual(spearman([1, 2, 3, 4], [4, 3, 2, 1]), -1.0)

    def test_a_constant_predictor_is_undefined_not_zero(self):
        # Otherwise a predictor that says nothing gets scored as merely
        # uncorrelated, which reads as a weak result instead of no result.
        self.assertIsNone(spearman([1, 1, 1, 1], [1, 2, 3, 4]))

    def test_ties_are_averaged_rather_than_ordered_arbitrarily(self):
        self.assertAlmostEqual(spearman([1, 1, 2, 2], [1, 2, 3, 4]), 0.894, 3)

    def test_too_few_points_is_undefined(self):
        self.assertIsNone(spearman([1, 2], [1, 2]))


class RecordTests(unittest.TestCase):
    def test_a_row_without_a_settled_state_has_no_truth(self):
        self.assertIsNone(
            observed_record(
                example(board="b", index=0, center=[0, 0, 0], settled=None)
            )
        )

    def test_the_command_record_carries_no_observed_field(self):
        # The predictors must be computable before the replay; leaking
        # x_plus into the command record would make the comparison circular.
        record = command_record(
            example(board="b", index=0, center=[0.1, 0, 0], settled=[9, 9, 9])
        )

        self.assertNotIn("x_plus", record)
        self.assertEqual(record["center"], [0.1, 0, 0])


class BoardPairTests(unittest.TestCase):
    def examples(self):
        # Settled position tracks the commanded x, so a predictor that reads
        # the command should order these pairs correctly.
        return [
            example(
                board="b",
                index=i,
                center=[0.2 * i, 0.0, 0.5],
                settled=[0.2 * i, 0.0, 0.5],
            )
            for i in range(5)
        ]

    def test_pairs_are_scored_within_a_board(self):
        columns = board_pairs(self.examples(), {})

        # 5 rows -> 10 unordered pairs.
        self.assertEqual(len(columns["truth"]), 10)
        self.assertEqual(len(columns["command_proxy"]), 10)

    def test_a_board_with_too_few_rows_is_skipped(self):
        columns = board_pairs(self.examples()[:2], {})

        self.assertEqual(columns["truth"], [])

    def test_an_embedding_is_scored_alongside_the_proxy(self):
        rows = self.examples()
        embedding = np.array([[float(i)] for i in range(len(rows))])

        columns = board_pairs(rows, {"set_attention": embedding})

        self.assertEqual(len(columns["set_attention"]), 10)
        self.assertAlmostEqual(
            spearman(columns["set_attention"], columns["truth"]), 1.0, 3
        )


if __name__ == "__main__":
    unittest.main()
