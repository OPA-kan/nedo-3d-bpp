from __future__ import annotations

import unittest

from scripts.evaluate_afterstate_spatial_representations import (
    _height_grid,
    evaluate,
)
from tests.test_evaluate_counterfactual_afterstate_value import run


class AfterstateSpatialRepresentationTests(unittest.TestCase):
    def test_height_grid_has_fixed_two_container_shape(self) -> None:
        row = run("x")["discovery"][0]
        self.assertEqual(len(_height_grid(row["lower_afterstate_tensor"], 4)), 32)
        self.assertEqual(len(_height_grid(row["lower_afterstate_tensor"], 8)), 128)

    def test_reports_every_attempted_representation(self) -> None:
        report = evaluate([run("base")], [run("one"), run("two")])
        self.assertIn("height_grid_4", report["models"])
        self.assertIn("height_grid_8", report["models"])
        self.assertIn("height_grid_4_knn_5", report["models"])


if __name__ == "__main__":
    unittest.main()
