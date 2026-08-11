from __future__ import annotations

import unittest

import json
import pathlib as _pathlib
import tempfile

from scripts.measure_swap_acceptance import (
    paired_rows,
    sign_test,
    summarise,
    verdict,
)


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
        "shipped_rule": "pareto_gate",
        "sum_rule_swaps": 5,
        "gate_swaps": 4,
        "sum_rule_sum": shipped[0],
        "sum_rule_occupancy": shipped[1],
        "sum_rule_consumption": shipped[2],
        "gate_sum": shadow[0],
        "gate_occupancy": shadow[1],
        "gate_consumption": shadow[2],
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
        report = summarise([row(degrading=2)] * 12)
        report["verdict"] = verdict(report)

        self.assertEqual(
            report["verdict"], "gate_dominates_on_both_components"
        )

    def test_a_trade_between_components_is_not_a_win(self):
        # The gate raising occupancy while dropping consumption is exactly
        # the pathology it exists to prevent, so it must not be reported as
        # a win just because one number went up.
        report = summarise(
            [row(degrading=1, shadow=(0.09, 0.09, -0.05))] * 12
        )
        report["verdict"] = verdict(report)

        self.assertEqual(
            report["verdict"], "gate_trades_one_component_for_the_other"
        )

    def test_the_sum_rule_winning_both_is_reportable_too(self):
        report = summarise(
            [row(degrading=1, shadow=(0.05, 0.01, -0.2))] * 12
        )
        report["verdict"] = verdict(report)

        self.assertEqual(
            report["verdict"], "sum_dominates_on_both_components"
        )

    def test_a_mean_with_the_right_sign_is_not_a_result(self):
        # The measured occupancy column: +0.0019 mean, 24 boards better and
        # 13 worse. That reads as a win and is not one -- p is about 0.1.
        # Reporting it as a win is the mistake this test exists to stop.
        rows = (
            [row(degrading=1, shadow=(0.09, 0.06, 0.9))] * 24
            + [row(degrading=1, shadow=(0.09, 0.04, 0.9))] * 13
        )
        report = summarise(rows)

        block = report["gate_minus_sum_occupancy"]
        self.assertGreater(block["mean"], 0.0)
        self.assertGreater(block["sign_test_p"], 0.05)
        self.assertEqual(block["direction"], "indistinguishable")
        self.assertEqual(
            verdict(report), "gate_wins_consumption_rest_indistinguishable"
        )

    def test_no_movement_at_all_is_reported_as_such(self):
        report = summarise(
            [row(degrading=1, shipped=(0.1, 0.05, 0.2),
                 shadow=(0.1, 0.05, 0.2))] * 12
        )

        self.assertEqual(verdict(report), "no_measurable_difference")


class GuardSafetyTests(unittest.TestCase):
    def test_both_arms_report_whether_a_board_would_fail_the_guard(self):
        # Adopting the gate lowers the number the acceptance guard reads.
        # Whether that turns a passing condition into a failing one is a
        # separate question from which rule covers the space better.
        report = summarise(
            [row(shipped=(0.1, 0.05, 0.0), shadow=(-0.01, 0.06, 0.1))]
        )

        self.assertEqual(
            report["sum_rule_guard_number"]["boards_at_or_below_zero"], 0
        )
        self.assertEqual(
            report["gate_guard_number"]["boards_at_or_below_zero"], 1
        )


class SignTestTests(unittest.TestCase):
    def test_a_unanimous_split_is_significant(self):
        self.assertLess(sign_test(12, 0), 0.001)

    def test_an_even_split_is_not(self):
        self.assertEqual(sign_test(6, 6), 1.0)

    def test_no_paired_boards_is_not_evidence_of_anything(self):
        self.assertEqual(sign_test(0, 0), 1.0)

    def test_the_measured_occupancy_split_is_not_significant(self):
        self.assertGreater(sign_test(24, 13), 0.05)

    def test_the_measured_consumption_split_is(self):
        self.assertLess(sign_test(25, 4), 0.001)

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
        missing["gate_consumption"] = None

        report = summarise([missing, row()])

        self.assertEqual(report["gate_minus_sum_consumption"]["boards"], 1)
        self.assertEqual(report["gate_minus_sum_occupancy"]["boards"], 2)


def trace(rule: str, *, sum_delta: float, occupancy: float,
          consumption: float, degrading: int = 0, refused: int = 0) -> dict:
    return {
        "acceptance": rule,
        "swaps_applied": 5,
        "component_degrading_swaps": degrading,
        "swaps_refused_by_gate": refused,
        "final_objective": {
            "mean_nearest_neighbor_distance_delta": sum_delta
        },
        "final_components": {
            "occupancy_delta": occupancy,
            "consumption_delta": consumption,
        },
    }


class SlotIndependenceTests(unittest.TestCase):
    """The defect: reading the arms by slot instead of by rule.

    Adopting the gate swapped which rule ships and which shadows. A reader
    that assumed the old assignment reported every column with its sign
    flipped -- the gate's replicated consumption win came out labelled
    `sum_better`, which is the opposite of what the corpus said.
    """

    SUM = trace("sum", sum_delta=0.10, occupancy=0.05,
                consumption=0.00, degrading=3)
    GATE = trace("pareto_gate", sum_delta=0.09, occupancy=0.06,
                 consumption=0.10, refused=7)

    def manifest(self, shipped: dict, shadow: dict) -> dict:
        return {
            "case": {
                "case_id": "m-dual-empty",
                "steps": [
                    {
                        "step": 3,
                        "sampling": {
                            "outcome_split": {
                                "swap_optimizer": shipped,
                                "swap_optimizer_shadow": shadow,
                            }
                        },
                    }
                ],
            }
        }

    def rows_for(self, shipped: dict, shadow: dict) -> list[dict]:
        with tempfile.TemporaryDirectory() as raw:
            root = _pathlib.Path(raw)
            (root / "dataset").mkdir()
            (root / "dataset" / "manifest.json").write_text(
                json.dumps(self.manifest(shipped, shadow)), encoding="utf-8"
            )
            return paired_rows(root)

    def test_the_two_slot_assignments_give_the_same_answer(self):
        before = summarise(self.rows_for(self.SUM, self.GATE))
        after = summarise(self.rows_for(self.GATE, self.SUM))

        for name in ("sum", "occupancy", "consumption"):
            self.assertEqual(
                before[f"gate_minus_sum_{name}"]["mean"],
                after[f"gate_minus_sum_{name}"]["mean"],
                f"{name} flipped when the arms swapped slots",
            )

    def test_the_counts_come_from_the_rule_that_can_produce_them(self):
        # Only the sum rule can accept a component-degrading swap, and only
        # the gate can refuse one, whichever slot each happens to sit in.
        for shipped, shadow in ((self.SUM, self.GATE), (self.GATE, self.SUM)):
            row = self.rows_for(shipped, shadow)[0]

            self.assertEqual(row["degrading_swaps"], 3)
            self.assertEqual(row["refused_by_gate"], 7)

    def test_the_shipped_rule_is_reported_not_assumed(self):
        self.assertEqual(
            self.rows_for(self.GATE, self.SUM)[0]["shipped_rule"],
            "pareto_gate",
        )

    def test_a_step_missing_one_rule_is_skipped(self):
        # Runs measured before the shadow arm landed carry one trace only.
        self.assertEqual(self.rows_for(self.SUM, {}), [])


if __name__ == "__main__":
    unittest.main()
