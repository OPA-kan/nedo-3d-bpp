import unittest

from scripts.run_provider_zero_rescue import resolve_strategies


class ProviderZeroRescueRunnerTests(unittest.TestCase):
    def test_rescue_budgets_are_relative_to_source_manifest(self):
        strategies = resolve_strategies(128)

        self.assertEqual(512, strategies["deep4x"]["attempt_budget"])
        self.assertEqual(2048, strategies["deep16x"]["attempt_budget"])
        self.assertEqual(128, strategies["stride4"]["attempt_budget"])
        self.assertEqual(4, strategies["stride4"]["candidate_stride"])

    def test_rejects_nonpositive_source_budget(self):
        with self.assertRaises(ValueError):
            resolve_strategies(0)


if __name__ == "__main__":
    unittest.main()
