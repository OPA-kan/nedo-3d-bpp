from __future__ import annotations

import unittest

from scripts.adjudicate_safety_rerank import adjudicate, placed_floor


def _row(
    case_id: str,
    arm: str,
    repeat: int,
    placed: int,
    channel: str,
    enforced: int = 0,
    returncode: int = 0,
) -> dict:
    return {
        "arm": arm,
        "repeat": repeat,
        "process_returncode": returncode,
        "cases": {
            case_id: {
                "placed_count": placed,
                "fill_score": float(placed),
                "terminal_channel": channel,
            }
        },
        "policy_trace": {
            "safety_rerank_observed_steps": placed,
            "safety_rerank_triggered_count": enforced,
            "safety_rerank_would_swap_count": enforced,
            "safety_rerank_enforced_count": enforced,
        },
    }


BASELINE = {
    "cases": {
        "b000-k20": {"placed_sd": 1.0},
        "c000-k1": {"placed_sd": 0.0},
    }
}


def _matrix(rerank_placed_c: int, rerank_channel_c: str) -> list[dict]:
    rows = []
    for repeat in range(3):
        rows.append(_row("b000-k20", "base", repeat, 20, "safe_end"))
        rows.append(_row("c000-k1", "base", repeat, 16, "topple"))
        rows.append(_row("b000-k20", "safety_null", repeat, 20, "safe_end"))
        rows.append(_row("c000-k1", "safety_null", repeat, 16, "topple"))
        rows.append(
            _row("b000-k20", "safety_rerank", repeat, 20, "safe_end",
                 enforced=1)
        )
        rows.append(
            _row("c000-k1", "safety_rerank", repeat, rerank_placed_c,
                 rerank_channel_c, enforced=1)
        )
    return rows


class AdjudicateSafetyRerankTests(unittest.TestCase):
    def test_placed_floor(self) -> None:
        self.assertEqual(placed_floor({"placed_sd": 1.5}), 3.0)
        self.assertEqual(placed_floor({"placed_sd": 0.0}), 1.0)
        self.assertEqual(placed_floor(None), 1.0)

    def test_all_gates_pass(self) -> None:
        result = adjudicate(_matrix(19, "safe_end"), BASELINE)
        self.assertTrue(all(result["gates"].values()))
        self.assertEqual(
            result["verdict"], "development_pass_gate3_required"
        )
        self.assertEqual(
            result["swap_activity"]["safety_rerank"]["enforced"], 6
        )

    def test_mechanism_gate_fails_without_channel_shift(self) -> None:
        result = adjudicate(_matrix(19, "topple"), BASELINE)
        self.assertFalse(result["gates"]["mechanism_topple_slide_lower"])
        self.assertEqual(
            result["verdict"], "development_fail_arm_closed"
        )

    def test_no_harm_gate_uses_baseline_floor(self) -> None:
        # c000-k1 has sd 0 -> floor 1 placement; dropping the mean by 3
        # placements breaches it even though the pooled direction and the
        # channel gates might pass.
        result = adjudicate(_matrix(13, "safe_end"), BASELINE)
        self.assertFalse(result["gates"]["no_harm_per_config"])

    def test_inert_arm_closes(self) -> None:
        rows = []
        for repeat in range(3):
            rows.append(_row("b000-k20", "base", repeat, 20, "safe_end"))
            rows.append(
                _row("b000-k20", "safety_null", repeat, 20, "safe_end")
            )
            rows.append(
                _row("b000-k20", "safety_rerank", repeat, 20, "safe_end",
                     enforced=0)
            )
        result = adjudicate(rows, BASELINE)
        self.assertEqual(result["verdict"], "inert_arm_closed")

    def test_negative_control_voids_wave(self) -> None:
        rows = _matrix(19, "safe_end")
        # Push the null arm outside the b000-k20 floor (2 sd = 2).
        for row in rows:
            if row["arm"] == "safety_null" and "b000-k20" in row["cases"]:
                row["cases"]["b000-k20"]["placed_count"] = 15
        result = adjudicate(rows, BASELINE)
        self.assertFalse(
            result["gates"]["negative_control_within_floor"]
        )
        self.assertEqual(
            result["verdict"], "development_fail_arm_closed"
        )

    def test_arm_names_are_overridable_for_the_probe_guard_wave(self) -> None:
        rows = []
        for repeat in range(3):
            rows.append(_row("b000-k20", "base", repeat, 20, "safe_end"))
            rows.append(_row("c000-k1", "base", repeat, 16, "topple"))
            rows.append(_row("b000-k20", "probe_null", repeat, 20, "safe_end"))
            rows.append(_row("c000-k1", "probe_null", repeat, 16, "topple"))
            for case_id, placed, channel in (
                ("b000-k20", 20, "safe_end"),
                ("c000-k1", 19, "safe_end"),
            ):
                row = _row(case_id, "probe_guard", repeat, placed, channel)
                row["policy_trace"] = {
                    "probe_guard_observed_steps": placed,
                    "probe_guard_unsafe_incumbent_count": 1,
                    "probe_guard_swapped_count": 1,
                    "probe_guard_budget_exhausted_count": 0,
                }
                rows.append(row)
        result = adjudicate(
            rows,
            BASELINE,
            null_arm="probe_null",
            enforce_arm="probe_guard",
        )
        self.assertEqual(result["null_arm"], "probe_null")
        self.assertEqual(result["enforce_arm"], "probe_guard")
        self.assertTrue(all(result["gates"].values()))
        self.assertEqual(
            result["verdict"], "development_pass_gate3_required"
        )
        self.assertEqual(
            result["swap_activity"]["probe_guard"]["enforced"], 6
        )

    def test_inert_guard_arm_closes_under_renamed_arms(self) -> None:
        rows = []
        for repeat in range(3):
            rows.append(_row("b000-k20", "base", repeat, 20, "safe_end"))
            rows.append(
                _row("b000-k20", "probe_null", repeat, 20, "safe_end")
            )
            row = _row("b000-k20", "probe_guard", repeat, 20, "safe_end")
            row["policy_trace"] = {
                "probe_guard_observed_steps": 20,
                "probe_guard_unsafe_incumbent_count": 0,
                "probe_guard_swapped_count": 0,
                "probe_guard_budget_exhausted_count": 0,
            }
            rows.append(row)
        result = adjudicate(
            rows,
            BASELINE,
            null_arm="probe_null",
            enforce_arm="probe_guard",
        )
        self.assertEqual(result["verdict"], "inert_arm_closed")

    def test_survival_mechanism_gates_on_pooled_steps(self) -> None:
        # The quiet-guard wave's channel composition: the enforce arm
        # still dies physically (channel unchanged) but LATER, so the
        # channel gate fails while the survival gate reads the extra
        # steps. Steps come from the cases' "steps" field.
        def row_with_steps(case_id, arm, repeat, placed, channel, steps,
                           swapped=0):
            row = _row(case_id, arm, repeat, placed, channel)
            row["cases"][case_id]["steps"] = steps
            row["policy_trace"] = {
                "probe_guard_observed_steps": steps,
                "probe_guard_unsafe_incumbent_count": swapped,
                "probe_guard_swapped_count": swapped,
                "probe_guard_budget_exhausted_count": 0,
                "probe_guard_quiet_skipped_count": steps - swapped,
            }
            return row

        rows = []
        for repeat in range(3):
            rows.append(
                row_with_steps("b000-k20", "base", repeat, 20,
                               "safe_end", 21)
            )
            rows.append(
                row_with_steps("c000-k1", "base", repeat, 16,
                               "topple", 17)
            )
            rows.append(
                row_with_steps("b000-k20", "quiet_null", repeat, 20,
                               "safe_end", 21)
            )
            rows.append(
                row_with_steps("c000-k1", "quiet_null", repeat, 16,
                               "topple", 17)
            )
            rows.append(
                row_with_steps("b000-k20", "quiet_guard", repeat, 20,
                               "safe_end", 21, swapped=1)
            )
            rows.append(
                row_with_steps("c000-k1", "quiet_guard", repeat, 19,
                               "topple", 20, swapped=1)
            )
        survival = adjudicate(
            rows,
            BASELINE,
            null_arm="quiet_null",
            enforce_arm="quiet_guard",
            mechanism="survival",
        )
        self.assertEqual(survival["mechanism"], "survival")
        self.assertIn("mechanism_pooled_steps_higher", survival["gates"])
        self.assertNotIn(
            "mechanism_topple_slide_lower", survival["gates"]
        )
        self.assertTrue(
            survival["gates"]["mechanism_pooled_steps_higher"]
        )
        self.assertEqual(
            survival["pooled_steps"],
            {"base": 114, "quiet_null": 114, "quiet_guard": 123},
        )
        # Channel composition stays reported even though it is not gated.
        self.assertEqual(
            survival["pooled_channels"]["quiet_guard"],
            {"safe_end": 3, "topple": 3},
        )
        self.assertTrue(all(survival["gates"].values()))
        self.assertEqual(
            survival["verdict"], "development_pass_gate3_required"
        )

        channels = adjudicate(
            rows,
            BASELINE,
            null_arm="quiet_null",
            enforce_arm="quiet_guard",
        )
        self.assertEqual(channels["mechanism"], "channels")
        self.assertFalse(
            channels["gates"]["mechanism_topple_slide_lower"]
        )

    def test_unknown_mechanism_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            adjudicate([], BASELINE, mechanism="bogus")

    def test_failed_processes_are_excluded_by_loader_contract(self) -> None:
        # adjudicate() receives already-filtered rows; collect() must
        # still ignore rows without exactly one case.
        rows = _matrix(19, "safe_end")
        rows.append({
            "arm": "base", "repeat": 9, "process_returncode": 0,
            "cases": {},
        })
        result = adjudicate(rows, BASELINE)
        self.assertEqual(result["episodes"], 18)


if __name__ == "__main__":
    unittest.main()
