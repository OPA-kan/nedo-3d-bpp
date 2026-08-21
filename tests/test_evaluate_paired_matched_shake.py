import unittest

from scripts.evaluate_paired_matched_shake import normalized_shake


class MatchedShakeTests(unittest.TestCase):
    def test_normalizes_energy_by_count_and_mass(self):
        result = normalized_shake(
            {"placed_count": 4, "placed_mass": 20.0},
            {
                "shake_peak_kinetic_energy": 10.0,
                "shake_items_shifted": 1,
                "shake_items_toppled": 2,
            },
        )

        self.assertEqual(result["peak_kinetic_energy_per_item"], 2.5)
        self.assertEqual(result["peak_kinetic_energy_per_mass"], 0.5)
        self.assertEqual(result["shifted_fraction"], 0.25)
        self.assertEqual(result["toppled_fraction"], 0.5)


if __name__ == "__main__":
    unittest.main()
