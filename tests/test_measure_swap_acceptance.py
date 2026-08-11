from __future__ import annotations

import unittest

from scripts.measure_swap_acceptance import summarise, verdict


def row(
    *,
    degrading: int = 0,
    shipped: tuple[float, float, float] = (0.1, 0.05, 0.0),
    shadow: tuple[float, float, float] = (0.09, 0.06, 0.1),
    refused: int = 0,
) -> dict:
    return {
        "source": "r",
        "case_id": "c",
        "step": 3,
        "degrading_swaps": degrading,
        "refused_by_gate": refused,
        "shipped_swaps": 5,
        "shadow_swaps": 4,
        "shipped_sum": shipped[0],
        "shipped_occupancy": shipped[1],
        "shipped_consumption": shipped[2],
        "shadow_sum": shadow[0],
        "shadow_occupancy": shadow[1],
        "shadow_consumption": shadow[2],
    }


class VerdictTests(unittest.TestCase):
    def test_no_degrading_swap_means_the_rule_cannot_matter(self):
        # The cheapest possible answer, and the one that should stop the
        # investigation: if the sum rule never bought a component with the
        # other, the two rules agree by construction.
        report = summarise([row(degrading=0), row(degrading=0)])
        report["verdict"] = verdict(report)

        self.assertEqual(
            report["verdict"], "acceptance_rule_cannot_matter_here"
        )

    def test_the_gate_winning_both_components_is_named_as_such(self):
        report = summarise([row(degrading=2)])
        report["verdict"] = verdict(report)

        self.assertEqual(
            report["verdict"], "gate_dominates_on_both_components"
        )

    def test_a_trade_between_components_is_not_a_win(self):
        # The gate raising occupancy while dropping consumption is exactly
        # the pathology it exists to prevent, so it must not be reported as
        # a win just because one number went up.
        report = summarise(
            [row(degrading=1, shadow=(0.09, 0.09, -0.05))]
        )
        report["verdict"] = verdict(report)

        self.assertEqual(
            report["verdict"], "gate_trades_one_component_for_the_other"
        )

    def test_the_sum_rule_winning_both_is_reportable_too(self):
        report = summarise(
            [row(degrading=1, shadow=(0.05, 0.01, -0.2))]
        )
        report["verdict"] = verdict(report)

        self.assertEqual(
            report["verdict"], "sum_dominates_on_both_components"
        )

    def test_an_empty_corpus_does_not_claim_a_result(self):
        report = summarise([])
        report["verdict"] = verdict(report)

        self.assertEqual(report["verdict"], "no_paired_boards")


class SummaryTests(unittest.TestCase):
    def test_paired_deltas_are_gate_minus_sum(self):
        report = summarise([row(shipped=(0.1, 0.05, 0.0),
                                shadow=(0.09, 0.06, 0.1))])

        self.assertAlmostEqual(report["gate_minus_sum_sum"]["mean"], -0.01)
        self.assertAlmostEqual(
            report["gate_minus_sum_occupancy"]["mean"], 0.01
        )
        self.assertAlmostEqual(
            report["gate_minus_sum_consumption"]["mean"], 0.1
        )

    def test_ties_are_counted_apart_from_losses(self):
        report = summarise(
            [row(shipped=(0.1, 0.05, 0.0), shadow=(0.1, 0.05, 0.0))]
        )
        block = report["gate_minus_sum_occupancy"]

        self.assertEqual((block["gate_better"], block["tied"]), (0, 1))
        self.assertEqual(block["gate_worse"], 0)

    def test_a_missing_component_is_skipped_not_counted_as_zero(self):
        missing = row()
        missing["shadow_consumption"] = None

        report = summarise([missing, row()])

        self.assertEqual(report["gate_minus_sum_consumption"]["boards"], 1)
        self.assertEqual(report["gate_minus_sum_occupancy"]["boards"], 2)


if __name__ == "__main__":
    unittest.main()
