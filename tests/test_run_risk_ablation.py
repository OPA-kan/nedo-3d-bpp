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

    def test_cross_step_telemetry_is_preserved_in_compact_summary(self):
        row = episode_row("cross_step_shadow", "b000-k20", 13, 14.5)
        row["policy_trace"] = {
            "cross_step_observed_steps": 14,
            "cross_step_previous_count": 40,
            "cross_step_pool_survivor_count": 30,
            "cross_step_static_valid_count": 24,
            "cross_step_would_prevent_fallback_count": 1,
            "cross_step_validation_seconds_total": 0.028,
            "cross_step_validation_seconds_max": 0.004,
            "cross_step_deadline_overrun_count": 0,
        }

        trace = summarize([row])["policy_trace_by_arm"][
            "cross_step_shadow"
        ]

        self.assertEqual(trace["observed_steps"], 14)
        self.assertEqual(trace["previous_count"], 40)
        self.assertEqual(trace["pool_survival_rate"], 0.75)
        self.assertEqual(trace["static_survival_rate"], 0.6)
        self.assertEqual(trace["static_survival_given_pool"], 0.8)
        self.assertEqual(trace["would_prevent_fallback_count"], 1)
        self.assertEqual(trace["validation_ms_per_observed_step"], 2.0)

    def test_development_and_full_suite_totals_are_separate(self):
        rows = [
            episode_row("base", "b000-k15", 10, 11.0),
            episode_row("base", "b000-k15", 12, 13.0),
            episode_row("base", "b000-k10", 20, 21.0),
        ]

        summary = summarize(rows)

        self.assertEqual(
            summary["development_totals"]["base"],
            {"placed": 11.0, "fill": 12.0, "cases": 1},
        )
        self.assertEqual(
            summary["suite_totals"]["base"],
            {"placed": 31.0, "fill": 33.0, "cases": 2},
        )
        self.assertEqual(
            summary["registered_development_baseline"]["placed"], 88.0
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

    def test_rollout_shadow_is_the_shipped_baseline_plus_telemetry(self):
        env = {
            "RELEASE_RISK_LIVE_RERANK": "0",
            "VISIBLE_POOL_ROLLOUT_ATTEMPTS": "999",
        }

        configure_arm_environment(env, "rollout_shadow", 2.0, 0.0)

        self.assertNotIn("RELEASE_RISK_LIVE_RERANK", env)
        self.assertEqual(env["VISIBLE_POOL_ROLLOUT_MODE"], "shadow")
        self.assertNotIn("VISIBLE_POOL_ROLLOUT_ATTEMPTS", env)

    def test_rollout_enforce_is_the_shipped_baseline_plus_selection(self):
        env = {"RELEASE_RISK_LIVE_RERANK": "0"}

        configure_arm_environment(env, "rollout_enforce", 2.0, 0.0)

        self.assertNotIn("RELEASE_RISK_LIVE_RERANK", env)
        self.assertEqual(env["VISIBLE_POOL_ROLLOUT_MODE"], "enforce")

    def test_an_unstrided_arm_does_not_inherit_an_outer_stride(self):
        """
        The stride is an experiment control like every other rollout knob:
        an arm that does not set it must not silently run at whatever the
        caller's shell had. This is the failure mode that made ablation
        round 1 measure a stale configuration on both arms.
        """
        env = {"VISIBLE_POOL_ROLLOUT_STRIDE": "8"}

        configure_arm_environment(env, "rollout_enforce", 2.0, 0.0)

        self.assertNotIn("VISIBLE_POOL_ROLLOUT_STRIDE", env)

    def test_stride4_arms_differ_from_their_base_only_by_the_stride(self):
        enforce: dict[str, str] = {}
        enforce_stride4: dict[str, str] = {}
        configure_arm_environment(enforce, "rollout_enforce", 2.0, 0.0)
        configure_arm_environment(
            enforce_stride4, "rollout_enforce_stride4", 2.0, 0.0
        )

        self.assertEqual(
            enforce_stride4.pop("VISIBLE_POOL_ROLLOUT_STRIDE"), "4"
        )
        self.assertEqual(enforce_stride4, enforce)

    def test_live_interleave_touches_only_the_live_search(self):
        env: dict[str, str] = {}

        configure_arm_environment(env, "live_interleave4", 2.0, 0.0)

        self.assertEqual(env["LIVE_SEARCH_INTERLEAVE"], "4")
        self.assertNotIn("VISIBLE_POOL_ROLLOUT_MODE", env)
        self.assertNotIn("VISIBLE_POOL_ROLLOUT_STRIDE", env)

    def test_live_interleave_arms_differ_from_base_only_by_the_order(self):
        base: dict[str, str] = {}
        interleaved: dict[str, str] = {}
        configure_arm_environment(base, "base", 2.0, 0.0)
        configure_arm_environment(interleaved, "live_interleave8", 2.0, 0.0)

        self.assertEqual(interleaved.pop("LIVE_SEARCH_INTERLEAVE"), "8")
        self.assertEqual(interleaved, base)

    def test_an_arm_does_not_inherit_an_outer_live_interleave(self):
        env = {"LIVE_SEARCH_INTERLEAVE": "16"}

        configure_arm_environment(env, "base", 2.0, 0.0)

        self.assertNotIn("LIVE_SEARCH_INTERLEAVE", env)

    def test_item_cap_arms_touch_only_the_item_dimension(self):
        base: dict[str, str] = {}
        capped: dict[str, str] = {}
        configure_arm_environment(base, "base", 2.0, 0.0)
        configure_arm_environment(capped, "item_cap16", 2.0, 0.0)

        self.assertEqual(capped.pop("MAX_POOL_ITEMS_EVALUATED"), "16")
        self.assertEqual(capped, base)

    def test_an_arm_does_not_inherit_an_outer_item_cap(self):
        env = {"MAX_POOL_ITEMS_EVALUATED": "40"}

        configure_arm_environment(env, "base", 2.0, 0.0)

        self.assertNotIn("MAX_POOL_ITEMS_EVALUATED", env)

    def test_rollout_shadow_stride4_stays_telemetry_only(self):
        env: dict[str, str] = {}

        configure_arm_environment(env, "rollout_shadow_stride4", 2.0, 0.0)

        self.assertEqual(env["VISIBLE_POOL_ROLLOUT_MODE"], "shadow")
        self.assertEqual(env["VISIBLE_POOL_ROLLOUT_STRIDE"], "4")


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
                "rollout_observed_steps": 0,
                "rollout_candidate_count": 0,
                "rollout_eligible_count": 0,
                "rollout_non_degenerate_count": 0,
                "rollout_would_change_count": 0,
                "rollout_unrestricted_change_count": 0,
                "rollout_unrestricted_within_band_count": 0,
                "rollout_enforced_count": 0,
                "rollout_q_loss_bins": {
                    "nonpositive": 0,
                    "0_to_0.05": 0,
                    "0.05_to_0.10": 0,
                    "0.10_to_0.15": 0,
                    "over_0.15": 0,
                },
                "rollout_by_step": {},
                "rollout_seconds_total": 0.0,
                "rollout_seconds_max": 0.0,
            },
        )

    def test_rollout_shadow_summary_counts_discrimination_and_cost(self):
        record = {
            "event": "decision",
            "step": 9,
            "candidate_diagnostics": {
                "visible_pool_rollout": {
                    "candidate_count": 3,
                    "eligible_count": 2,
                    "would_change_item": True,
                    "unrestricted_would_change_item": True,
                    "unrestricted_proposal_within_q_band": True,
                    "unrestricted_proposed_q_loss": 0.12,
                    "enforced": True,
                    "elapsed_seconds": 0.15,
                    "candidates": [
                        {"rollout_key": [2, 0.1, 0.0, 0.0]},
                        {"rollout_key": [1, 0.2, 0.0, 0.0]},
                    ],
                }
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "trace.jsonl"
            path.write_text(json.dumps(record) + "\n", encoding="utf-8")

            summary = policy_trace_summary(path)

        self.assertEqual(summary["rollout_observed_steps"], 1)
        self.assertEqual(summary["rollout_candidate_count"], 3)
        self.assertEqual(summary["rollout_non_degenerate_count"], 1)
        self.assertEqual(summary["rollout_would_change_count"], 1)
        self.assertEqual(summary["rollout_unrestricted_change_count"], 1)
        self.assertEqual(
            summary["rollout_unrestricted_within_band_count"], 1
        )
        self.assertEqual(summary["rollout_enforced_count"], 1)
        self.assertEqual(
            summary["rollout_q_loss_bins"]["0.10_to_0.15"], 1
        )
        self.assertEqual(summary["rollout_by_step"]["9"]["observed"], 1)
        self.assertEqual(summary["rollout_by_step"]["9"]["enforced"], 1)
        self.assertAlmostEqual(summary["rollout_seconds_total"], 0.15)


if __name__ == "__main__":
    unittest.main()
