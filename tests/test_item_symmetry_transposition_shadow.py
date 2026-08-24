import unittest

from scripts.item_symmetry_transposition_shadow import (
    ItemSymmetryTranspositionShadow,
)


class ItemSymmetryTranspositionShadowTests(unittest.TestCase):
    def test_quotient_only_hit_records_potential_saving_without_behavior(self):
        shadow = ItemSymmetryTranspositionShadow()

        first = shadow.observe(
            exact_key="label-a", symmetry_key="physical-q",
            value_signature="value-1",
        )
        second = shadow.observe(
            exact_key="label-b", symmetry_key="physical-q",
            value_signature="value-1",
        )
        summary = shadow.summary()

        self.assertFalse(first["symmetry_hit"])
        self.assertTrue(second["quotient_only_hit"])
        self.assertFalse(second["value_conflict"])
        self.assertEqual(summary["potential_state_reduction"], 1)
        self.assertEqual(summary["potential_evaluator_call_savings"], 1)
        self.assertEqual(summary["value_conflicts"], 0)
        self.assertEqual(summary["behavior_effect"], "none")

    def test_different_values_under_one_quotient_are_a_conflict(self):
        shadow = ItemSymmetryTranspositionShadow()
        shadow.observe(
            exact_key="label-a", symmetry_key="physical-q",
            value_signature="value-1",
        )

        event = shadow.observe(
            exact_key="label-b", symmetry_key="physical-q",
            value_signature="value-2",
        )

        self.assertTrue(event["value_conflict"])
        self.assertEqual(shadow.summary()["value_conflicts"], 1)
        self.assertFalse(shadow.summary()["zero_conflict_observed"])

    def test_exact_revisit_is_not_a_quotient_only_hit(self):
        shadow = ItemSymmetryTranspositionShadow()
        shadow.observe(exact_key="same", symmetry_key="same-q")

        event = shadow.observe(exact_key="same", symmetry_key="same-q")

        self.assertTrue(event["exact_hit"])
        self.assertFalse(event["quotient_only_hit"])
        self.assertEqual(shadow.summary()["potential_state_reduction"], 0)


if __name__ == "__main__":
    unittest.main()
