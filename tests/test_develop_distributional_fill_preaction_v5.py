from __future__ import annotations

import unittest

from scripts.develop_distributional_fill_preaction_v5 import (
    DISCORDANT_FLOOR,
    confirmation_gate_v5,
    minimum_powered_discordant,
    prediction_disagreements,
)


def _evaluation(*, wins: int, losses: int, streams: int = 5) -> dict:
    ties = 200 - wins - losses
    per_stream = [
        {
            "stream_variant": f"s{index}",
            "rows": 10,
            "candidate_correct": 5,
            "action_geometry_correct": 5,
        }
        for index in range(streams)
    ]
    discordant = wins + losses
    if discordant:
        from scripts.evaluate_counterfactual_afterstate_value import (
            _exact_two_sided_sign_p,
        )
        p = _exact_two_sided_sign_p(wins, losses)
    else:
        p = 1.0
    return {
        "support": {"raw_rows": 400, "unique_rows": 200, "unique_fraction": 0.5},
        "paired_candidate_vs_action": {
            "wins": wins, "ties": ties, "losses": losses,
            "exact_two_sided_sign_p": p,
        },
        "per_stream": per_stream,
    }


class DistributionalFillPreactionV5Tests(unittest.TestCase):
    def test_perfect_sweep_needs_exactly_the_floor(self) -> None:
        self.assertEqual(minimum_powered_discordant(1.0), DISCORDANT_FLOOR)

    def test_weaker_effects_need_more_discordant_pairs(self) -> None:
        strong = minimum_powered_discordant(0.9)
        weak = minimum_powered_discordant(0.66)
        self.assertGreater(weak, strong)
        self.assertGreaterEqual(strong, DISCORDANT_FLOOR)

    def test_win_fraction_at_or_below_half_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            minimum_powered_discordant(0.5)

    def test_prediction_disagreements_counts_differing_rows(self) -> None:
        candidate = ["higher_afterstate_better"] * 3 + ["lower_afterstate_better"]
        action = [
            "higher_afterstate_better", "lower_afterstate_better",
            "higher_afterstate_better", "lower_afterstate_better",
        ]
        self.assertEqual(prediction_disagreements(candidate, action), 1)

    def test_gate_marks_underpowered_confirmation(self) -> None:
        gate = confirmation_gate_v5(_evaluation(wins=2, losses=1), 12)
        self.assertFalse(gate["passed"])
        self.assertTrue(gate["underpowered"])
        self.assertFalse(gate["checks"]["discordant_pairs_at_least_frozen_minimum"])

    def test_gate_passes_a_powered_significant_confirmation(self) -> None:
        gate = confirmation_gate_v5(_evaluation(wins=14, losses=2), 12)
        self.assertTrue(gate["checks"]["discordant_pairs_at_least_frozen_minimum"])
        self.assertFalse(gate["underpowered"])
        self.assertTrue(gate["passed"])


if __name__ == "__main__":
    unittest.main()
