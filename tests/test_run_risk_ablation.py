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

    def test_future_option_is_paired_against_shipped_base(self):
        rows = [
            episode_row("base", "b000-k20", 18, 22.0),
            episode_row("future-option", "b000-k20", 20, 25.0),
        ]

        summary = summarize(rows)

        diff = summary["paired_vs_base"]["future-option"]["b000-k20"]
        self.assertEqual(diff["placed_diff"], 2.0)
        self.assertEqual(diff["fill_diff"], 3.0)


class ConfigureArmEnvironmentTests(unittest.TestCase):
    def test_future_option_keeps_shipped_risk_and_enables_only_tiebreak(self):
        env = {
            "RELEASE_RISK_LIVE_RERANK": "0",
            "RELEASE_RISK_P_MODEL": "old",
            "RELEASE_RISK_RERANK_LAMBDA": "9",
            "RELEASE_RISK_SLIDE_LAMBDA": "9",
            "RELEASE_RISK_SHADOW_RERANK": "1",
        }

        configure_arm_environment(
            env, "future-option", risk_lambda=1.0
        )

        self.assertEqual(env["FUTURE_OPTION_TIEBREAK"], "1")
        for key in (
            "RELEASE_RISK_LIVE_RERANK",
            "RELEASE_RISK_P_MODEL",
            "RELEASE_RISK_RERANK_LAMBDA",
            "RELEASE_RISK_SLIDE_LAMBDA",
            "RELEASE_RISK_SHADOW_RERANK",
        ):
            self.assertNotIn(key, env)

    def test_other_arms_cannot_inherit_future_option_flag(self):
        env = {
            "FUTURE_OPTION_TIEBREAK": "1",
            "FUTURE_OPTION_ROUTE_SHADOW": "1",
        }

        configure_arm_environment(env, "base", risk_lambda=1.0)

        self.assertNotIn("FUTURE_OPTION_TIEBREAK", env)
        self.assertNotIn("FUTURE_OPTION_ROUTE_SHADOW", env)


if __name__ == "__main__":
    unittest.main()
