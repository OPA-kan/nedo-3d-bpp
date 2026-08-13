from __future__ import annotations

import unittest

from scripts.evaluate_afterstate_support_development import evaluate
from tests.test_evaluate_counterfactual_afterstate_value import run


class AfterstateSupportDevelopmentTests(unittest.TestCase):
    def test_holds_each_development_run_out_in_full(self) -> None:
        report = evaluate([run("base")], [run("dev-1"), run("dev-2")])

        self.assertEqual(report["development_run_ids"], ["dev-1", "dev-2"])
        for fold in report["folds"]:
            self.assertNotIn(fold["target_run_id"], fold["training_run_ids"])

    def test_rejects_base_development_leakage(self) -> None:
        with self.assertRaisesRegex(ValueError, "disjoint"):
            evaluate([run("same")], [run("same")])


if __name__ == "__main__":
    unittest.main()
