from __future__ import annotations

import unittest

import numpy as np

from scripts.compare_risk_rules import (
    calibration_table,
    evaluate_rules,
    pareto_flags,
    rule_selection,
)


def make_row(
    snapshot_id: str,
    score: float,
    rotated: bool,
    unsafe: bool | None = None,
    weight: float = 1.0,
    remaining: int = 10,
):
    return {
        "snapshot_id": snapshot_id,
        "score_immediate": score,
        "_remaining_items": remaining,
        "sampling": {"sampling_weight": weight},
        "physical": {
            "Y": {
                "rotated_over_30": rotated,
                "not_placed_safe": rotated if unsafe is None else unsafe,
            }
        },
    }


class RuleSelectionTests(unittest.TestCase):
    def setUp(self):
        self.scores = np.array([1.0, 0.9, 0.5])
        self.risks = np.array([0.5, 0.05, 0.9])

    def test_linear_trades_score_for_risk(self):
        # lambda small: top score wins; lambda large: low risk wins.
        self.assertEqual(
            rule_selection(self.scores, self.risks, "linear", 0.1), 0
        )
        self.assertEqual(
            rule_selection(self.scores, self.risks, "linear", 1.0), 1
        )

    def test_state_scaled_matches_linear_at_equivalent_product(self):
        for lam in (0.25, 1.0, 4.0):
            self.assertEqual(
                rule_selection(
                    self.scores, self.risks, "linear", lam * 2.0
                ),
                rule_selection(
                    self.scores,
                    self.risks,
                    "state_scaled_linear",
                    lam,
                    scale=2.0,
                ),
            )

    def test_quadratic_penalizes_small_risks_less_than_linear(self):
        scores = np.array([1.0, 0.9])
        risks = np.array([0.3, 0.0])
        # linear lambda=1: 0.7 vs 0.9 -> switches to the safe candidate.
        self.assertEqual(rule_selection(scores, risks, "linear", 1.0), 1)
        # quadratic lambda=1: 1 - 0.09 = 0.91 vs 0.9 -> keeps the top score.
        self.assertEqual(
            rule_selection(scores, risks, "quadratic", 1.0), 0
        )

    def test_hinge_ignores_risk_below_tau(self):
        scores = np.array([1.0, 0.99])
        risks = np.array([0.19, 0.0])
        self.assertEqual(
            rule_selection(scores, risks, "hinge", 100.0, tau=0.2), 0
        )
        self.assertEqual(
            rule_selection(scores, risks, "hinge", 100.0, tau=0.1), 1
        )

    def test_hard_picks_best_feasible(self):
        # eps=0.2: only candidate 1 is feasible.
        self.assertEqual(
            rule_selection(self.scores, self.risks, "hard", 0.2), 1
        )
        # eps=0.6: candidates 0 and 1 feasible, 0 has the better score.
        self.assertEqual(
            rule_selection(self.scores, self.risks, "hard", 0.6), 0
        )

    def test_hard_falls_back_to_least_risky_when_starved(self):
        self.assertEqual(
            rule_selection(self.scores, self.risks, "hard", 0.01), 1
        )

    def test_unknown_rule_raises(self):
        with self.assertRaises(ValueError):
            rule_selection(self.scores, self.risks, "nonsense", 1.0)


class EvaluateRulesTests(unittest.TestCase):
    def test_linear_lambda_moves_selection_off_rotated_top_score(self):
        # One snapshot: top-score candidate rotates, runner-up is safe.
        rows = [
            make_row("s1", 1.0, rotated=True),
            make_row("s1", 0.9, rotated=False),
        ]
        predictions = np.array([0.8, 0.5])
        results = evaluate_rules(rows, predictions)
        by_config = {
            (entry["rule"], entry["parameter"]): entry
            for entry in results
        }
        strong = by_config[("linear", 4.0)]
        self.assertEqual(strong["selected_rotated"], 0)
        self.assertAlmostEqual(strong["mean_score_loss"], 0.1)
        weak = by_config[("linear", 0.25)]
        self.assertEqual(weak["selected_rotated"], 1)
        self.assertAlmostEqual(weak["mean_score_loss"], 0.0)

    def test_hard_starvation_counted_and_fallback_used(self):
        rows = [
            make_row("s1", 1.0, rotated=True),
            make_row("s1", 0.9, rotated=False),
        ]
        predictions = np.array([0.95, 0.9])
        results = evaluate_rules(rows, predictions)
        hard = [entry for entry in results if entry["rule"] == "hard"]
        tight = next(e for e in hard if e["parameter"] == 0.1)
        # No candidate under eps=0.1: starved, fallback picks lower risk.
        self.assertEqual(tight["hard_starved_snapshots"], 1)
        self.assertEqual(tight["selected_rotated"], 0)
        loose = next(e for e in hard if e["parameter"] == 0.5)
        self.assertEqual(loose["hard_starved_snapshots"], 1)

    def test_state_scale_uses_remaining_items(self):
        # Two snapshots with identical candidates but different remaining
        # items: the scaled rule should switch only where remaining is high.
        rows = [
            make_row("early", 1.0, rotated=True, remaining=18),
            make_row("early", 0.9, rotated=False, remaining=18),
            make_row("late", 1.0, rotated=True, remaining=2),
            make_row("late", 0.9, rotated=False, remaining=2),
        ]
        predictions = np.array([0.4, 0.1, 0.4, 0.1])
        results = evaluate_rules(rows, predictions)
        by_config = {
            (entry["rule"], entry["parameter"]): entry
            for entry in results
        }
        # mean_remaining = 10; scale early=1.8, late=0.2.
        # lambda0=0.5: early penalty 0.5*1.8*0.3=0.27 > 0.1 gap (switch),
        # late penalty 0.5*0.2*0.3=0.03 < 0.1 gap (keep rotated top).
        scaled = by_config[("state_scaled_linear", 0.5)]
        self.assertEqual(scaled["selected_rotated"], 1)
        flat = by_config[("linear", 0.5)]
        self.assertEqual(flat["selected_rotated"], 0)


class CalibrationTests(unittest.TestCase):
    def test_rates_track_predictions_and_weights(self):
        rows = []
        predictions = []
        for i in range(100):
            p = i / 100.0
            rows.append(
                make_row("s", 0.0, rotated=(i % 10 < i // 10), weight=1.0)
            )
            predictions.append(p)
        table = calibration_table(np.array(predictions), rows)
        self.assertEqual(sum(entry["n"] for entry in table), 100)
        self.assertLess(table[0]["raw_rate"], table[-1]["raw_rate"])
        for entry in table:
            self.assertAlmostEqual(
                entry["raw_rate"], entry["weighted_rate"]
            )

    def test_weighted_rate_differs_under_unequal_weights(self):
        rows = [
            make_row("s", 0.0, rotated=True, weight=3.0),
            make_row("s", 0.0, rotated=False, weight=1.0),
        ]
        predictions = np.array([0.5, 0.5])
        table = calibration_table(predictions, rows)
        total_n = sum(entry["n"] for entry in table)
        self.assertEqual(total_n, 2)
        weighted = sum(
            entry["weighted_rate"] * entry["n"] for entry in table
        ) / total_n
        self.assertAlmostEqual(weighted, 0.75)


class ParetoTests(unittest.TestCase):
    def test_dominated_flagging(self):
        results = [
            {"selected_rotated": 0, "mean_score_loss": 0.5},
            {"selected_rotated": 2, "mean_score_loss": 0.1},
            {"selected_rotated": 2, "mean_score_loss": 0.3},  # dominated
            {"selected_rotated": 1, "mean_score_loss": 0.2},
        ]
        pareto_flags(results)
        self.assertFalse(results[0]["dominated"])
        self.assertFalse(results[1]["dominated"])
        self.assertTrue(results[2]["dominated"])
        self.assertFalse(results[3]["dominated"])

    def test_ties_are_not_mutually_dominating(self):
        results = [
            {"selected_rotated": 1, "mean_score_loss": 0.2},
            {"selected_rotated": 1, "mean_score_loss": 0.2},
        ]
        pareto_flags(results)
        self.assertFalse(results[0]["dominated"])
        self.assertFalse(results[1]["dominated"])


if __name__ == "__main__":
    unittest.main()
