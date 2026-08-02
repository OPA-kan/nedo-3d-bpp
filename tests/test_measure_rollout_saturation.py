import unittest

from scripts import measure_rollout_saturation as saturation


class BuildArmsTests(unittest.TestCase):
    def test_baseline_is_first_and_unstrided(self):
        arms = saturation.build_arms([2], [], base_attempts=64)

        self.assertEqual(arms[0]["name"], "baseline")
        self.assertEqual(arms[0]["stride"], 1)
        self.assertEqual(arms[0]["attempts_per_step"], 64)

    def test_stride_arms_hold_the_attempt_budget_fixed(self):
        arms = saturation.build_arms([2, 4], [], base_attempts=64)
        stride_arms = [arm for arm in arms if arm["family"] == "stride"]

        self.assertEqual([arm["stride"] for arm in stride_arms], [2, 4])
        for arm in stride_arms:
            self.assertEqual(arm["attempts_per_step"], 64)

    def test_budget_arms_hold_the_stride_fixed(self):
        arms = saturation.build_arms([], [256, 512], base_attempts=64)
        budget_arms = [arm for arm in arms if arm["family"] == "budget"]

        self.assertEqual(
            [arm["attempts_per_step"] for arm in budget_arms], [256, 512]
        )
        for arm in budget_arms:
            self.assertEqual(arm["stride"], 1)

    def test_a_budget_equal_to_the_base_is_not_duplicated(self):
        arms = saturation.build_arms([], [64, 512], base_attempts=64)

        self.assertEqual(
            [arm["name"] for arm in arms], ["baseline", "budget-512"]
        )

    def test_offsets_beyond_the_stride_are_not_valid_phases(self):
        arms = saturation.build_arms(
            [2], [], base_attempts=64, offsets=[0, 1, 2, 3]
        )

        self.assertEqual(
            [arm["name"] for arm in arms],
            ["baseline", "stride-2", "stride-2+1"],
        )


class SummaryTests(unittest.TestCase):
    def _row(self, snapshot, step, baseline_nd, wide_nd):
        return {
            "snapshot": snapshot,
            "step": step,
            "arms": {
                "baseline": {
                    "non_degenerate": baseline_nd,
                    "any_future_placement": baseline_nd,
                    "elapsed_ms": 50.0,
                },
                "stride-4": {
                    "non_degenerate": wide_nd,
                    "any_future_placement": False,
                    "elapsed_ms": 90.0,
                },
            },
        }

    def _arms(self):
        return [
            {
                "name": "baseline",
                "stride": 1,
                "stride_offset": 0,
                "attempts_per_step": 64,
            },
            {
                "name": "stride-4",
                "stride": 4,
                "stride_offset": 0,
                "attempts_per_step": 64,
            },
        ]

    def test_bands_split_on_the_late_step(self):
        rows = [
            self._row("early", 8, True, True),
            self._row("late", 12, False, True),
        ]

        summary = saturation.summarize(rows, self._arms(), late_step=10)

        self.assertEqual(summary["early_step_lt_10"]["snapshots"], 1)
        self.assertEqual(summary["late_step_ge_10"]["snapshots"], 1)

    def test_recovery_counts_only_snapshots_the_baseline_tied(self):
        rows = [
            self._row("tied", 12, False, True),
            self._row("already-split", 13, True, True),
        ]

        late = saturation.summarize(rows, self._arms(), late_step=10)[
            "late_step_ge_10"
        ]

        self.assertEqual(late["arms"]["stride-4"]["baseline_tied_snapshots"], 1)
        self.assertEqual(
            late["arms"]["stride-4"]["recovered_from_baseline_ties"], 1
        )
        self.assertEqual(
            late["arms"]["baseline"]["recovered_from_baseline_ties"], 0
        )

    def test_future_placement_is_tracked_apart_from_non_degeneracy(self):
        """
        A rollout key can split on the risk terms alone, with every branch
        still placing nothing. That is discrimination without reach, and the
        two must not be reported as the same recovery.
        """
        rows = [self._row("risk-only", 12, False, True)]

        late = saturation.summarize(rows, self._arms(), late_step=10)[
            "late_step_ge_10"
        ]

        self.assertEqual(late["arms"]["stride-4"]["non_degenerate"], 1)
        self.assertEqual(late["arms"]["stride-4"]["any_future_placement"], 0)

    def test_rows_without_arms_are_excluded_from_every_band(self):
        rows = [
            self._row("usable", 12, False, True),
            {"snapshot": "skipped", "step": 12, "arms": {}},
        ]

        summary = saturation.summarize(rows, self._arms(), late_step=10)

        self.assertEqual(summary["snapshots"], 2)
        self.assertEqual(summary["usable"], 1)
        self.assertEqual(summary["late_step_ge_10"]["snapshots"], 1)


if __name__ == "__main__":
    unittest.main()
