from __future__ import annotations

import unittest

import numpy as np

from scripts.develop_distributional_fill_preaction_v4 import (
    _neighbor_score,
    group_complement_indices,
)


class DistributionalFillPreactionV4Tests(unittest.TestCase):
    def test_group_complement_excludes_every_heldout_stream(self) -> None:
        rows = [
            {"scenario_axes": {"stream_variant": "a"}},
            {
                "scenario_axes": {"stream_variant": "a"},
                "_preaction_stream_variants": ["a", "b"],
            },
            {"scenario_axes": {"stream_variant": "b"}},
            {"scenario_axes": {"stream_variant": "c"}},
        ]

        folds = group_complement_indices(rows)

        shared_train, shared_test = next(
            (train, test) for train, test in folds if test == [1]
        )
        self.assertEqual(shared_train, [3])

    def test_weighted_neighbor_score_favors_closer_label(self) -> None:
        labels = np.asarray([1.0, -1.0])
        squared = np.asarray([[0.0625, 4.0]])
        order = np.asarray([[0, 1]])

        score = _neighbor_score(
            labels, squared, order, k=2, weighted=True
        )

        self.assertGreater(score[0], 0.0)


if __name__ == "__main__":
    unittest.main()
