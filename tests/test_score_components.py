import unittest

from scripts.score_components import components, dominates


def case(fill, com_z, shift, ke, prio=0, soft=0, placed=0.5):
    return {
        "evaluation": {
            "fill_score": fill,
            "num_placed_items": placed,
            "step_metrics": [
                {
                    "center_of_mass_z": com_z,
                    "priority_covered_by_other": prio,
                    "priority_misrouted": 0,
                    "soft_covered_by_other": soft,
                    "soft_misrouted": 0,
                }
            ],
            "shake_response": {
                "shake_max_shift": shift,
                "shake_peak_kinetic_energy": ke,
                "shake_items_shifted": 2,
                "shake_items_toppled": 0,
            },
        }
    }


class ComponentVectorTests(unittest.TestCase):
    def test_no_total_is_produced(self):
        """
        The point of the vector is that it cannot be collapsed without
        inventing the unpublished weights, which is the mechanism by which
        a policy -- learned or hand-written -- exploits a misspecified
        objective. If a 'total' ever appears here, that protection is gone.
        """
        vector = components(case(30.0, 0.70, 0.10, 8.0))
        for forbidden in ("total", "score", "reward", "weighted"):
            self.assertNotIn(forbidden, vector)

    def test_every_component_declares_a_direction_and_its_fidelity(self):
        for name, entry in components(case(30.0, 0.70, 0.10, 8.0)).items():
            with self.subTest(component=name):
                self.assertIn(entry["direction"], ("up", "down"))
                self.assertTrue(entry["fidelity"].strip())

    def test_gate_is_marked_as_a_constraint_not_a_term(self):
        # COMPETITION_RULES: below the placement threshold everything except
        # fill is zero. Treating placed as a sixth term to trade against the
        # others would invert that.
        self.assertIn("constraint", components(case(30.0, 0.7, 0.1, 8.0))["gate"]["note"])

    def test_directions_match_the_published_rules(self):
        vector = components(case(30.0, 0.70, 0.10, 8.0))
        self.assertEqual(vector["fill"]["direction"], "up")
        self.assertEqual(vector["gate"]["direction"], "up")
        # lower centre of gravity, less movement, fewer violations
        self.assertEqual(vector["cog"]["direction"], "down")
        self.assertEqual(vector["stability"]["direction"], "down")
        self.assertEqual(vector["placement"]["direction"], "down")
        self.assertEqual(vector["soft"]["direction"], "down")

    def test_dominance_needs_every_component_no_worse(self):
        better = components(case(30.0, 0.70, 0.10, 8.0))
        worse = components(case(29.0, 0.75, 0.12, 9.0))
        self.assertTrue(dominates(better, worse))
        self.assertFalse(dominates(worse, better))

    def test_a_trade_dominates_in_neither_direction(self):
        # More fill but a higher centre of gravity: exactly the shape of the
        # death-band regression, and precisely what a weighted total would
        # have hidden.
        traded = components(case(33.0, 0.80, 0.10, 8.0))
        base = components(case(30.0, 0.70, 0.10, 8.0))
        self.assertFalse(dominates(traded, base))
        self.assertFalse(dominates(base, traded))

    def test_violations_sum_covering_and_misrouting(self):
        vector = components(case(30.0, 0.7, 0.1, 8.0, prio=2, soft=3))
        self.assertEqual(vector["placement"]["raw"], 2.0)
        self.assertEqual(vector["soft"]["raw"], 3.0)

    def test_missing_quantities_are_none_not_zero(self):
        # A component that was never measured must not read as a perfect
        # score, which is how an unexercised axis fakes a clean arm.
        vector = components({"evaluation": {"fill_score": 30.0}})
        self.assertIsNone(vector["placement"]["raw"])
        self.assertIsNone(vector["cog"]["raw"])


if __name__ == "__main__":
    unittest.main()
