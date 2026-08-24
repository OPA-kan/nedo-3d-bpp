import unittest

from scripts.single_agent_packing import (
    COMPONENT_HEAD_SPECS,
    SUFFIX_HEAD_SPECS,
    component_delta_vector,
    suffix_value_heads,
)


def metrics(fill=0.0, soft=0.0, shift=None):
    result = {
        "fill_score_proxy": fill,
        "placed_count": 1.0,
        "soft_covered_by_other": soft,
        "soft_direct_violating_pairs": soft,
        "soft_stack_violated_items": soft,
        "soft_stack_violating_pairs": soft,
        "priority_covered_by_other": 0.0,
        "priority_direct_violating_pairs": 0.0,
        "priority_stack_violated_items": 0.0,
        "priority_stack_violating_pairs": 0.0,
        "priority_misrouted": 0.0,
        "center_of_mass_z": 0.4,
        "surface_total_variation": 0.01,
    }
    if shift is not None:
        result["post_shake_max_shift"] = shift
        result["post_shake_peak_kinetic_energy"] = 0.5
        result["post_shake_items_toppled"] = 0.0
    return result


class SingleAgentPackingTests(unittest.TestCase):
    def test_no_game_heads_exist(self):
        for spec in (COMPONENT_HEAD_SPECS, SUFFIX_HEAD_SPECS):
            self.assertFalse(any("game" in head for head in spec))
            self.assertFalse(any("return_to_go" in head for head in spec))

    def test_component_deltas_censor_missing_metrics(self):
        before = metrics(fill=1.0)
        after = metrics(fill=3.5, soft=1.0)
        del after["surface_total_variation"]

        heads = component_delta_vector(before, after)

        self.assertEqual(heads["fill_gain"]["value"], 2.5)
        self.assertEqual(heads["soft_violation_gain"]["value"], 1.0)
        self.assertIsNone(heads["surface_total_variation_delta"]["value"])
        self.assertFalse(
            heads["surface_total_variation_delta"]["target_eligible"]
        )
        self.assertEqual(
            heads["surface_total_variation_delta"]["censor_reason"],
            "unmeasured",
        )

    def test_suffix_heads_are_genuine_termination_gated(self):
        step = metrics(fill=2.0)
        final = metrics(fill=10.0, shift=0.12)

        genuine = suffix_value_heads(
            step, final, termination="stream_exhausted"
        )
        censored = suffix_value_heads(step, final, termination="max_steps")

        self.assertEqual(genuine["fill_return"]["value"], 8.0)
        self.assertTrue(genuine["fill_return"]["target_eligible"])
        self.assertEqual(genuine["stream_completed"]["value"], 1.0)
        self.assertEqual(
            genuine["terminal_stability_max_shift"]["value"], 0.12
        )
        self.assertFalse(censored["fill_return"]["target_eligible"])
        self.assertEqual(
            censored["fill_return"]["censor_reason"], "max_steps"
        )

    def test_exhaustion_termination_scores_stream_incomplete(self):
        heads = suffix_value_heads(
            metrics(), metrics(shift=0.1),
            termination="no_retained_candidate",
        )

        self.assertEqual(heads["stream_completed"]["value"], 0.0)
        self.assertTrue(heads["stream_completed"]["target_eligible"])


if __name__ == "__main__":
    unittest.main()
