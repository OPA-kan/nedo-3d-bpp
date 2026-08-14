from __future__ import annotations

import unittest

from scripts.build_distributional_fill_shadow_model import (
    build_model,
    shadow_predictions,
)
from tests.test_evaluate_counterfactual_afterstate_value import run


class DistributionalFillShadowModelTests(unittest.TestCase):
    def test_model_artifact_drives_label_free_shadow_decisions(self) -> None:
        model = build_model([run("one"), run("two")])
        target = run("target")["late"]
        target[0].update({
            "source_node_id": "node-1",
            "lower_stable_item_index": 3,
            "higher_stable_item_index": 7,
        })

        predictions = shadow_predictions(model, target)

        self.assertEqual(model["training_run_ids"], ["one", "two"])
        self.assertNotIn("actual", predictions[0])
        self.assertIn(
            predictions[0]["shadow_stable_item_index"],
            (
                target[0]["lower_stable_item_index"],
                target[0]["higher_stable_item_index"],
            ),
        )
        self.assertEqual(
            predictions[0]["used_afterstate"],
            predictions[0]["packed_prediction"]
            == predictions[0]["packed_visible_prediction"],
        )


if __name__ == "__main__":
    unittest.main()
