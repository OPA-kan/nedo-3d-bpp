from __future__ import annotations

import unittest
import json
import pathlib
import tempfile

from scripts.run_risk_ablation import (
    configure_arm_environment,
    policy_trace_summary,
    summarize,
)


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

    def test_rescue_is_paired_against_shipped_base(self):
        rows = [
            episode_row("base", "b000-k20", 14, 16.0),
            episode_row("rescue", "b000-k20", 16, 18.5),
        ]

        summary = summarize(rows)

        self.assertEqual(summary["baseline_arm"], "base")
        self.assertEqual(summary["paired_vs_off"], {})
        self.assertEqual(
            summary["paired_vs_baseline"]["rescue"]["b000-k20"],
            {"placed_diff": 2.0, "fill_diff": 2.5},
        )


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
        env = {
            "RESCUE_SCAN_ENABLED": "1",
            "CROSS_STEP_INCUMBENT_MODE": "shadow",
        }

        configure_arm_environment(env, "base", 2.0, 0.0)

        self.assertNotIn("RESCUE_SCAN_ENABLED", env)
        self.assertNotIn("CROSS_STEP_INCUMBENT_MODE", env)

    def test_cross_step_shadow_is_the_shipped_baseline_plus_telemetry(self):
        env = {
            "RELEASE_RISK_LIVE_RERANK": "0",
            "CROSS_STEP_INCUMBENT_PER_ITEM": "99",
        }

        configure_arm_environment(env, "cross_step_shadow", 2.0, 0.0)

        self.assertNotIn("RELEASE_RISK_LIVE_RERANK", env)
        self.assertEqual(env["CROSS_STEP_INCUMBENT_MODE"], "shadow")
        self.assertNotIn("CROSS_STEP_INCUMBENT_PER_ITEM", env)


class PolicyTraceSummaryTests(unittest.TestCase):
    def test_counts_rescue_and_protocol_fallback_separately(self):
        records = [
            {"event": "init"},
            {
                "event": "decision",
                "action_source": "placement_core",
                "candidate_diagnostics": {
                    "rescue_scan": {"triggered": False}
                },
            },
            {
                "event": "decision",
                "action_source": "rescue_scan",
                "candidate_diagnostics": {
                    "rescue_scan": {"triggered": True}
                },
            },
            {
                "event": "decision",
                "action_source": "unsafe_protocol_fallback",
                "candidate_diagnostics": {
                    "rescue_scan": {"triggered": True},
                    "cross_step_incumbent": {
                        "previous_count": 4,
                        "pool_survivor_count": 3,
                        "static_valid_count": 2,
                        "would_prevent_protocol_fallback": True,
                        "validation_seconds": 0.004,
                        "deadline_remaining_after_validation": -0.001,
                    },
                },
            },
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "trace.jsonl"
            path.write_text(
                "".join(json.dumps(record) + "\n" for record in records),
                encoding="utf-8",
            )

            summary = policy_trace_summary(path)

        self.assertEqual(
            summary,
            {
                "decision_count": 3,
                "rescue_trigger_count": 2,
                "rescue_action_count": 1,
                "protocol_fallback_count": 1,
                "cross_step_observed_steps": 1,
                "cross_step_previous_count": 4,
                "cross_step_pool_survivor_count": 3,
                "cross_step_static_valid_count": 2,
                "cross_step_would_prevent_fallback_count": 1,
                "cross_step_validation_seconds_total": 0.004,
                "cross_step_validation_seconds_max": 0.004,
                "cross_step_deadline_overrun_count": 1,
            },
        )


if __name__ == "__main__":
    unittest.main()
