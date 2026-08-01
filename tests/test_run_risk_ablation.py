from __future__ import annotations

import unittest

from scripts.run_risk_ablation import configure_arm_environment, summarize


def episode_row(arm, case_id, placed, fill, returncode=0):
    return {
        "arm": arm,
        "process_returncode": returncode,
        "cases": {
            case_id: {
                "placed_count": placed,
                "fill_score": fill,
                "steps": placed + 1,
            }
        },
    }


class SummarizeTests(unittest.TestCase):
    def test_paired_diff_vs_off(self):
        rows = [
            episode_row("off", "b000-k20", 16, 20.0),
            episode_row("off", "b000-k20", 18, 22.0),
            episode_row("mech-lam2", "b000-k20", 19, 24.0),
            episode_row("mech-lam2", "b000-k20", 19, 26.0),
        ]
        summary = summarize(rows)
        self.assertEqual(summary["arms"]["off"]["placed"]["n"], 2)
        self.assertAlmostEqual(
            summary["arms"]["mech-lam2"]["placed"]["mean"], 19.0
        )
        diff = summary["paired_vs_off"]["mech-lam2"]["b000-k20"]
        self.assertAlmostEqual(diff["placed_diff"], 2.0)
        self.assertAlmostEqual(diff["fill_diff"], 4.0)

    def test_failed_processes_excluded(self):
        rows = [
            episode_row("off", "b000-k20", 16, 20.0),
            episode_row("off", "b000-k20", 0, 0.0, returncode=1),
        ]
        summary = summarize(rows)
        self.assertEqual(summary["arms"]["off"]["placed"]["n"], 1)

    def test_no_off_arm_gives_no_paired_diff(self):
        rows = [episode_row("mech-lam2", "b000-k20", 19, 24.0)]
        summary = summarize(rows)
        self.assertEqual(summary["paired_vs_off"], {})


class ArmEnvironmentTests(unittest.TestCase):
    def test_rescue_is_the_shipped_baseline_plus_rescue_flag(self):
        env = {
            "RELEASE_RISK_LIVE_RERANK": "0",
            "RELEASE_RISK_SLIDE_LAMBDA": "9",
            "RESCUE_SCAN_ATTEMPT_BUDGET": "1",
        }

        configure_arm_environment(env, "rescue", 2.0, 0.0)

        self.assertNotIn("RELEASE_RISK_LIVE_RERANK", env)
        self.assertNotIn("RELEASE_RISK_SLIDE_LAMBDA", env)
        self.assertEqual(env["RESCUE_SCAN_ENABLED"], "1")
        self.assertNotIn("RESCUE_SCAN_ATTEMPT_BUDGET", env)

    def test_base_clears_rescue_controls(self):
        env = {"RESCUE_SCAN_ENABLED": "1"}

        configure_arm_environment(env, "base", 2.0, 0.0)

        self.assertNotIn("RESCUE_SCAN_ENABLED", env)


if __name__ == "__main__":
    unittest.main()
