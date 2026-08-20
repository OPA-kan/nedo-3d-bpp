from __future__ import annotations

import unittest
import hashlib
import json
import pathlib
import tempfile

from scripts.run_risk_ablation import (
    configure_arm_environment,
    policy_trace_summary,
    summarize,
    terminal_failure_channel,
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
    def test_full_proxy_vector_and_terminal_channels_are_aggregated(self):
        row = episode_row("structured_noop", "b000-k20", 18, 22.0)
        case = row["cases"]["b000-k20"]
        case.update(
            {
                "final_com_z": 0.64,
                "policy_seconds": 6.4,
                "terminal_channel": "topple",
                "is_included": True,
                "is_valid": True,
                "is_placed_safe": False,
                "attribute_placement": {
                    "priority_clean_ratio": 0.75,
                    "soft_clean_ratio": 1.0,
                },
                "shake_response": {
                    "shake_items": 18,
                    "shake_items_shifted": 3,
                    "shake_items_toppled": 1,
                    "shake_max_shift": 0.12,
                    "shake_peak_kinetic_energy": 4.5,
                },
                "score_components": {
                    "cog_score": 9.5,
                    "stability_score": 12.0,
                    "placement_score": 2.0,
                    "soft_item_score": 4.0,
                },
            }
        )

        summary = summarize([row])
        arm = summary["arms"]["structured_noop"]

        self.assertEqual(arm["shake_toppled"]["mean"], 1.0)
        self.assertAlmostEqual(
            arm["shake_shifted_fraction"]["mean"], 0.167
        )
        self.assertEqual(arm["priority_clean"]["mean"], 0.75)
        self.assertEqual(arm["soft_clean"]["mean"], 1.0)
        self.assertEqual(arm["policy_seconds"]["mean"], 6.4)
        self.assertEqual(arm["official_cog"]["mean"], 9.5)
        self.assertEqual(arm["terminal_included"]["mean"], 1.0)
        self.assertEqual(arm["terminal_valid"]["mean"], 1.0)
        self.assertEqual(arm["terminal_placed_safe"]["mean"], 0.0)
        self.assertEqual(
            summary["terminal_channels"]["structured_noop"], {"topple": 1}
        )

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

    def test_temporal_chunk_telemetry_is_preserved_in_compact_summary(self):
        row = episode_row("temporal_chunk_shadow", "b000-k20", 13, 14.5)
        row["policy_trace"] = {
            "temporal_chunk_observed_steps": 10,
            "temporal_chunk_scheduled_count": 16,
            "temporal_chunk_static_valid_count": 12,
            "temporal_chunk_multi_origin_steps": 8,
            "temporal_chunk_consensus_steps": 5,
            "temporal_chunk_selected_match_count": 3,
            "temporal_chunk_selected_disagree_count": 2,
            "temporal_chunk_selected_matches_any_action_count": 4,
            "temporal_chunk_selected_matches_any_item_count": 7,
            "temporal_chunk_item_consensus_steps": 6,
            "temporal_chunk_selected_item_consensus_match_count": 4,
            "temporal_chunk_selected_item_consensus_disagree_count": 2,
            "temporal_chunk_would_prevent_fallback_count": 1,
            "temporal_chunk_generated_count": 18,
            "temporal_chunk_validation_seconds_total": 0.02,
            "temporal_chunk_validation_seconds_max": 0.004,
            "temporal_chunk_generation_seconds_total": 0.08,
            "temporal_chunk_generation_seconds_max": 0.015,
            "temporal_chunk_valid_by_delay": {"1": 7, "2": 5},
            "temporal_chunk_scheduled_by_delay": {"1": 8, "2": 8},
        }

        trace = summarize([row])["policy_trace_by_arm"][
            "temporal_chunk_shadow"
        ]

        self.assertEqual(trace["temporal_chunk_static_survival_rate"], 0.75)
        self.assertEqual(trace["temporal_chunk_consensus_steps"], 5)
        self.assertEqual(trace["temporal_chunk_selected_match_count"], 3)
        self.assertEqual(trace["temporal_chunk_selected_disagree_count"], 2)
        self.assertEqual(
            trace["temporal_chunk_selected_matches_any_action_count"], 4
        )
        self.assertEqual(
            trace["temporal_chunk_selected_matches_any_item_count"], 7
        )
        self.assertEqual(trace["temporal_chunk_item_consensus_steps"], 6)
        self.assertEqual(
            trace["temporal_chunk_selected_item_consensus_match_count"], 4
        )
        self.assertEqual(
            trace["temporal_chunk_selected_item_consensus_disagree_count"], 2
        )
        self.assertEqual(trace["temporal_chunk_ms_per_observed_step"], 10.0)
        self.assertEqual(
            trace["temporal_chunk_valid_by_delay"], {"1": 7, "2": 5}
        )
        self.assertEqual(
            trace["temporal_chunk_survival_by_delay"],
            {"1": 0.875, "2": 0.625},
        )

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

    def test_action_hash_negative_control_is_paired_by_case_and_repeat(self):
        rows = []
        for repeat, base_hash, shadow_hash in (
            (0, "same", "same"),
            (1, "base-only", "shadow-only"),
        ):
            for arm, digest in (
                ("base", base_hash),
                ("residual_affordance_shadow", shadow_hash),
            ):
                row = episode_row(arm, "b000-k20", 18, 20.0)
                row["repeat"] = repeat
                row["policy_trace"] = {
                    "action_sequence_sha256": digest
                }
                rows.append(row)

        control = summarize(rows)["action_sequence_negative_control"]

        self.assertEqual(control["paired"], 2)
        self.assertEqual(control["matched"], 1)
        self.assertEqual(control["mismatched"], 1)
        self.assertEqual(control["missing"], 0)
        self.assertFalse(control["passed"])


class ArmEnvironmentTests(unittest.TestCase):
    def test_multi_axis_enforce_uses_retained_portfolio(self):
        env = {}

        configure_arm_environment(env, "multi_axis_enforce", 2.0, 0.0)

        self.assertEqual(env["PLACEMENT_SELECTOR_MODE"], "structured_retained")
        self.assertEqual(env["MULTI_AXIS_SELECTOR_MODE"], "enforce")

    def test_multi_axis_shadow_uses_retained_portfolio_without_enforce(self):
        env = {
            "PLACEMENT_SELECTOR_MODE": "stale",
            "MULTI_AXIS_SELECTOR_MODE": "stale",
        }

        configure_arm_environment(env, "multi_axis_shadow", 2.0, 0.0)

        self.assertEqual(env["PLACEMENT_SELECTOR_MODE"], "structured_retained")
        self.assertEqual(env["MULTI_AXIS_SELECTOR_MODE"], "shadow")

    def test_residual_affordance_shadow_has_no_enforce_control(self):
        env = {
            "RESIDUAL_AFFORDANCE_SHADOW_MODE": "stale",
            "PLACEMENT_SELECTOR_MODE": "stale",
        }

        configure_arm_environment(
            env, "residual_affordance_shadow", 2.0, 0.0
        )

        self.assertNotIn("PLACEMENT_SELECTOR_MODE", env)
        self.assertEqual(env["RESIDUAL_AFFORDANCE_SHADOW_MODE"], "shadow")

    def test_structured_noop_is_baseline_plus_selector_mode(self):
        env = {"PLACEMENT_SELECTOR_MODE": "stale"}

        configure_arm_environment(env, "structured_noop", 2.0, 0.0)

        self.assertEqual(env["PLACEMENT_SELECTOR_MODE"], "structured_noop")
        base: dict[str, str] = {"PLACEMENT_SELECTOR_MODE": "stale"}
        configure_arm_environment(base, "base", 2.0, 0.0)
        self.assertNotIn("PLACEMENT_SELECTOR_MODE", base)

    def test_structured_retained_is_baseline_plus_selector_mode(self):
        env = {"PLACEMENT_SELECTOR_MODE": "stale"}

        configure_arm_environment(env, "structured_retained", 2.0, 0.0)

        self.assertEqual(
            env["PLACEMENT_SELECTOR_MODE"], "structured_retained"
        )

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

    def test_temporal_chunk_shadow_is_baseline_plus_shadow_flag(self):
        env = {
            "RELEASE_RISK_LIVE_RERANK": "0",
            "TEMPORAL_CHUNK_DEPTH": "99",
        }

        configure_arm_environment(env, "temporal_chunk_shadow", 2.0, 0.0)

        self.assertNotIn("RELEASE_RISK_LIVE_RERANK", env)
        self.assertEqual(env["TEMPORAL_CHUNK_ENSEMBLE_MODE"], "shadow")
        self.assertNotIn("TEMPORAL_CHUNK_DEPTH", env)

    def test_temporal_chunk_stride4_is_shadow_with_explicit_stride(self):
        env = {
            "RELEASE_RISK_LIVE_RERANK": "0",
            "TEMPORAL_CHUNK_STRIDE": "99",
        }

        configure_arm_environment(
            env, "temporal_chunk_shadow_stride4", 2.0, 0.0
        )

        self.assertNotIn("RELEASE_RISK_LIVE_RERANK", env)
        self.assertEqual(env["TEMPORAL_CHUNK_ENSEMBLE_MODE"], "shadow")
        self.assertEqual(env["TEMPORAL_CHUNK_STRIDE"], "4")

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

    def test_board_arms_differ_from_base_only_by_the_selection_rule_and_k(self):
        base: dict[str, str] = {}
        board: dict[str, str] = {}
        configure_arm_environment(base, "base", 2.0, 0.0)
        configure_arm_environment(board, "board_k8", 2.0, 0.0)

        self.assertEqual(board.pop("LOOKAHEAD_SELECTION_MODE"), "board")
        self.assertEqual(board.pop("LOOKAHEAD_TOP_K"), "8")
        self.assertEqual(board, base)

    def test_the_topk_control_changes_k_without_the_board_rule(self):
        """
        topk8 exists so a board_k8 win is not read as the board features
        when it is really the wider candidate set.
        """
        base: dict[str, str] = {}
        control: dict[str, str] = {}
        configure_arm_environment(base, "base", 2.0, 0.0)
        configure_arm_environment(control, "topk8", 2.0, 0.0)

        self.assertEqual(control.pop("LOOKAHEAD_TOP_K"), "8")
        self.assertNotIn("LOOKAHEAD_SELECTION_MODE", control)
        self.assertEqual(control, base)

    def test_board_k3_holds_k_at_the_shipped_value(self):
        """The clean contrast against base: the selection rule alone."""
        env: dict[str, str] = {}

        configure_arm_environment(env, "board_k3", 2.0, 0.0)

        self.assertEqual(env["LOOKAHEAD_TOP_K"], "3")
        self.assertEqual(env["LOOKAHEAD_SELECTION_MODE"], "board")

    def test_an_arm_does_not_inherit_an_outer_selection_mode(self):
        env = {"LOOKAHEAD_SELECTION_MODE": "board", "LOOKAHEAD_TOP_K": "32"}

        configure_arm_environment(env, "base", 2.0, 0.0)

        self.assertNotIn("LOOKAHEAD_SELECTION_MODE", env)
        self.assertNotIn("LOOKAHEAD_TOP_K", env)

    def test_first_pass_arms_differ_from_base_only_by_the_first_pass_depth(self):
        base: dict[str, str] = {}
        deeper: dict[str, str] = {}
        configure_arm_environment(base, "base", 2.0, 0.0)
        configure_arm_environment(deeper, "first_pass256", 2.0, 0.0)

        self.assertEqual(deeper.pop("ANCHOR_FIRST_PASS_ATTEMPTS"), "256")
        self.assertEqual(deeper, base)

    def test_the_midpoint_arm_exists_because_the_cliff_is_only_bracketed(self):
        env: dict[str, str] = {}

        configure_arm_environment(env, "first_pass128", 2.0, 0.0)

        self.assertEqual(env["ANCHOR_FIRST_PASS_ATTEMPTS"], "128")

    def test_the_old_default_stays_reachable_as_an_arm(self):
        """
        The default moved 64 -> 256. Without this arm the shipped-before
        behaviour would be unmeasurable, and a regression against it could
        not be checked.
        """
        env: dict[str, str] = {}

        configure_arm_environment(env, "first_pass64", 2.0, 0.0)

        self.assertEqual(env["ANCHOR_FIRST_PASS_ATTEMPTS"], "64")

    def test_the_ladder_extends_below_the_old_default_for_task_c(self):
        """
        Task C's fatal endgame states are starved of UNIT coverage, not of
        depth inside a unit: units visited at the c001-k1 step-19 terminal
        fell from 4 of 12 to 2 of 12 when the default moved 64 -> 256. The
        interesting direction there is shallower than anything the Task B
        depth block needed, so the ladder has to reach below 64.
        """
        for arm, depth in (("first_pass16", "16"), ("first_pass32", "32")):
            with self.subTest(arm=arm):
                base: dict[str, str] = {}
                shallower: dict[str, str] = {}
                configure_arm_environment(base, "base", 2.0, 0.0)
                configure_arm_environment(shallower, arm, 2.0, 0.0)

                self.assertEqual(
                    shallower.pop("ANCHOR_FIRST_PASS_ATTEMPTS"), depth
                )
                self.assertEqual(shallower, base)

    def test_an_arm_does_not_inherit_an_outer_first_pass_depth(self):
        env = {"ANCHOR_FIRST_PASS_ATTEMPTS": "1024"}

        configure_arm_environment(env, "base", 2.0, 0.0)

        self.assertNotIn("ANCHOR_FIRST_PASS_ATTEMPTS", env)

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

    def test_late_item_cap_arm_preserves_early_cap(self):
        env: dict[str, str] = {}
        configure_arm_environment(env, "late_item_cap20", 2.0, 0.0)
        self.assertEqual(env["LATE_POOL_ITEMS_EVALUATED"], "20")
        self.assertEqual(env["LATE_POOL_MIN_PLACED"], "6")
        self.assertNotIn("MAX_POOL_ITEMS_EVALUATED", env)

    def test_late_item_cap16_is_a_smaller_mid_late_intervention(self):
        env: dict[str, str] = {}
        configure_arm_environment(env, "late_item_cap16", 2.0, 0.0)
        self.assertEqual(env["LATE_POOL_ITEMS_EVALUATED"], "16")
        self.assertEqual(env["LATE_POOL_MIN_PLACED"], "6")
        self.assertNotIn("MAX_POOL_ITEMS_EVALUATED", env)

    def test_narrow_pool_arm_adds_only_a_visible_pool_guard(self):
        env: dict[str, str] = {}
        configure_arm_environment(env, "late_narrow_pool_cap16", 2.0, 0.0)
        self.assertEqual(env["LATE_POOL_ITEMS_EVALUATED"], "16")
        self.assertEqual(env["LATE_POOL_MIN_PLACED"], "6")
        self.assertEqual(env["LATE_POOL_MAX_VISIBLE"], "16")
        self.assertNotIn("MAX_POOL_ITEMS_EVALUATED", env)

    def test_rollout_shadow_stride4_stays_telemetry_only(self):
        env: dict[str, str] = {}

        configure_arm_environment(env, "rollout_shadow_stride4", 2.0, 0.0)

        self.assertEqual(env["VISIBLE_POOL_ROLLOUT_MODE"], "shadow")
        self.assertEqual(env["VISIBLE_POOL_ROLLOUT_STRIDE"], "4")


    def test_anchor_fallback_is_the_shipped_baseline_plus_the_flag(self):
        env = {
            "RELEASE_RISK_LIVE_RERANK": "0",
            "ANCHOR_FALLBACK_STRIDES": "1",
        }

        configure_arm_environment(env, "anchor_fallback", 2.0, 0.0)

        self.assertNotIn("RELEASE_RISK_LIVE_RERANK", env)
        self.assertEqual(env["ANCHOR_FALLBACK_ENABLED"], "1")
        # An inherited stride ladder would silently make the arms
        # incomparable across runs.
        self.assertNotIn("ANCHOR_FALLBACK_STRIDES", env)

    def test_base_clears_the_anchor_fallback_flag(self):
        env = {"ANCHOR_FALLBACK_ENABLED": "1"}

        configure_arm_environment(env, "base", 2.0, 0.0)

        self.assertNotIn("ANCHOR_FALLBACK_ENABLED", env)


class PolicyTraceSummaryTests(unittest.TestCase):
    def test_records_search_attempt_coverage(self):
        records = [
            {
                "event": "decision",
                "candidate_diagnostics": {
                    "search": {"attempts_consumed": 120}
                },
            },
            {
                "event": "decision",
                "candidate_diagnostics": {
                    "search": {"attempts_consumed": 80},
                    "selected_candidate_evaluation": {"schema_version": 1},
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

        self.assertEqual(summary["decision_count"], 2)
        self.assertEqual(summary["search_attempts_total"], 200)
        self.assertEqual(summary["search_attempts_max"], 120)
        self.assertEqual(summary["structured_evaluation_count"], 1)

    def test_action_sequence_hash_is_canonical_and_ordered(self):
        commands = [
            {
                "item_idx": 2,
                "container_idx": 0,
                "place_pos": [0.1, 0.2, 0.3],
                "orientation": 4,
            },
            {
                "item_idx": 1,
                "container_idx": 1,
                "place_pos": [0.4, 0.5, 0.6],
                "orientation": 2,
            },
        ]
        records = [
            {"event": "decision", "action_command": command}
            for command in commands
        ]
        expected = hashlib.sha256()
        for command in commands:
            expected.update(
                json.dumps(
                    command, sort_keys=True, separators=(",", ":")
                ).encode("utf-8")
            )
            expected.update(b"\n")
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "trace.jsonl"
            path.write_text(
                "".join(json.dumps(record) + "\n" for record in records),
                encoding="utf-8",
            )

            summary = policy_trace_summary(path)

        self.assertEqual(summary["action_command_count"], 2)
        self.assertEqual(
            summary["action_sequence_sha256"], expected.hexdigest()
        )

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
                "search_attempts_total": 0,
                "search_attempts_max": 0,
                "structured_evaluation_count": 0,
                "rescue_trigger_count": 2,
                "rescue_action_count": 1,
                "protocol_fallback_count": 1,
                "safety_rerank_observed_steps": 0,
                "safety_rerank_triggered_count": 0,
                "safety_rerank_would_swap_count": 0,
                "safety_rerank_enforced_count": 0,
                "visible_tree_observed_steps": 0,
                "visible_tree_would_change_count": 0,
                "visible_tree_enforced_count": 0,
                "visible_tree_budget_exhausted_count": 0,
                "physics_probe_observed_steps": 0,
                "physics_probe_failed_steps": 0,
                "physics_probe_unsafe_predictions": 0,
                "probe_guard_observed_steps": 0,
                "probe_guard_unsafe_incumbent_count": 0,
                "probe_guard_swapped_count": 0,
                "probe_guard_budget_exhausted_count": 0,
                "probe_guard_quiet_skipped_count": 0,
                "probe_guard_attr_filtered_count": 0,
                "cross_step_observed_steps": 1,
                "cross_step_previous_count": 4,
                "cross_step_pool_survivor_count": 3,
                "cross_step_static_valid_count": 2,
                "cross_step_would_prevent_fallback_count": 1,
                "cross_step_validation_seconds_total": 0.004,
                "cross_step_validation_seconds_max": 0.004,
                "cross_step_deadline_overrun_count": 1,
                "temporal_chunk_observed_steps": 0,
                "temporal_chunk_scheduled_count": 0,
                "temporal_chunk_static_valid_count": 0,
                "temporal_chunk_multi_origin_steps": 0,
                "temporal_chunk_consensus_steps": 0,
                "temporal_chunk_selected_match_count": 0,
                "temporal_chunk_selected_disagree_count": 0,
                "temporal_chunk_selected_matches_any_action_count": 0,
                "temporal_chunk_selected_matches_any_item_count": 0,
                "temporal_chunk_item_consensus_steps": 0,
                "temporal_chunk_selected_item_consensus_match_count": 0,
                "temporal_chunk_selected_item_consensus_disagree_count": 0,
                "temporal_chunk_would_prevent_fallback_count": 0,
                "temporal_chunk_generated_count": 0,
                "temporal_chunk_validation_seconds_total": 0.0,
                "temporal_chunk_validation_seconds_max": 0.0,
                "temporal_chunk_generation_seconds_total": 0.0,
                "temporal_chunk_generation_seconds_max": 0.0,
                "temporal_chunk_valid_by_delay": {},
                "temporal_chunk_scheduled_by_delay": {},
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
                "multi_axis_observed_steps": 0,
                "multi_axis_multi_candidate_steps": 0,
                "multi_axis_baseline_dominated_count": 0,
                "multi_axis_selected_dominated_count": 0,
                "multi_axis_would_change_action_count": 0,
                "multi_axis_would_change_selected_action_count": 0,
                "multi_axis_would_change_item_count": 0,
                "multi_axis_enforced_count": 0,
                "multi_axis_candidate_count": 0,
                "multi_axis_pareto_front_count": 0,
                "residual_affordance_observed_steps": 0,
                "residual_affordance_candidate_count": 0,
                "residual_affordance_would_change_count": 0,
                "residual_affordance_would_change_item_count": 0,
                "residual_affordance_guarded_change_count": 0,
                "residual_affordance_guarded_item_change_count": 0,
                "residual_affordance_attr_blocked_count": 0,
                "residual_affordance_contract_regression_count": 0,
                "residual_affordance_immediate_delta_total": 0.0,
                "residual_affordance_guarded_immediate_delta_total": 0.0,
                "action_command_count": 0,
                "action_sequence_sha256": (
                    "e3b0c44298fc1c149afbf4c8996fb924"
                    "27ae41e4649b934ca495991b7852b855"
                ),
            },
        )

    def test_physics_probe_summary_counts_failed_and_unsafe(self):
        records = [
            {
                "event": "physics_probe",
                "step": 0,
                "angle_deg": 1.2,
                "displacement": 0.01,
                "predicted_safe": True,
                "scene_bodies": 7,
                "elapsed_seconds": 0.04,
            },
            {
                "event": "physics_probe",
                "step": 1,
                "angle_deg": 88.0,
                "displacement": 0.6,
                "predicted_safe": False,
                "scene_bodies": 8,
                "elapsed_seconds": 0.05,
            },
            {
                "event": "physics_probe",
                "step": 2,
                "angle_deg": None,
                "displacement": None,
                "predicted_safe": None,
                "scene_bodies": None,
                "elapsed_seconds": None,
            },
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "trace.jsonl"
            path.write_text(
                "".join(json.dumps(record) + "\n" for record in records),
                encoding="utf-8",
            )

            summary = policy_trace_summary(path)

        self.assertEqual(summary["physics_probe_observed_steps"], 3)
        self.assertEqual(summary["physics_probe_failed_steps"], 1)
        self.assertEqual(summary["physics_probe_unsafe_predictions"], 1)
        self.assertEqual(summary["decision_count"], 0)

    def test_physics_probe_arm_sets_only_the_shadow_knob(self):
        env = {"PHYSICS_PROBE_SHADOW": "stale", "VISIBLE_TREE_SEARCH": "on"}
        configure_arm_environment(env, "physics_probe", 2.0, 0.0)
        self.assertEqual(env["PHYSICS_PROBE_SHADOW"], "1")
        self.assertNotIn("VISIBLE_TREE_SEARCH", env)

        base = {"PHYSICS_PROBE_SHADOW": "stale"}
        configure_arm_environment(base, "base", 2.0, 0.0)
        self.assertNotIn("PHYSICS_PROBE_SHADOW", base)

    def test_probe_null_is_the_log_only_timing_control(self):
        env = {"PHYSICS_PROBE_MODE": "stale"}
        configure_arm_environment(env, "probe_null", 2.0, 0.0)
        self.assertEqual(env["PHYSICS_PROBE_SHADOW"], "1")
        self.assertNotIn("PHYSICS_PROBE_MODE", env)

    def test_probe_guard_sets_only_the_guard_mode(self):
        env = {"PHYSICS_PROBE_SHADOW": "stale"}
        configure_arm_environment(env, "probe_guard", 2.0, 0.0)
        self.assertEqual(env["PHYSICS_PROBE_MODE"], "guard")
        self.assertNotIn("PHYSICS_PROBE_SHADOW", env)

        base = {"PHYSICS_PROBE_MODE": "guard"}
        configure_arm_environment(base, "base", 2.0, 0.0)
        self.assertNotIn("PHYSICS_PROBE_MODE", base)

    def test_quiet_null_sets_only_the_log_only_shadow_artifact(self):
        env = {"PHYSICS_PROBE_MODE": "stale", "SAFETY_RERANK_MODE": "stale"}
        configure_arm_environment(env, "quiet_null", 2.0, 0.0)
        self.assertTrue(
            env["SAFETY_RERANK_SHADOW"].endswith(
                "candidate-mlp-safety-v1.json"
            )
        )
        self.assertNotIn("PHYSICS_PROBE_MODE", env)
        self.assertNotIn("SAFETY_RERANK_MODE", env)

    def test_quiet_guard_mirrors_probe_guard_except_the_mode(self):
        guard: dict[str, str] = {}
        quiet: dict[str, str] = {}
        configure_arm_environment(guard, "probe_guard", 2.0, 0.0)
        configure_arm_environment(quiet, "quiet_guard", 2.0, 0.0)

        self.assertEqual(quiet.pop("PHYSICS_PROBE_MODE"), "guard_quiet")
        self.assertEqual(guard.pop("PHYSICS_PROBE_MODE"), "guard")
        self.assertEqual(quiet, guard)

    def test_quiet_skip_events_are_counted(self):
        records = [
            {
                "event": "physics_probe_guard",
                "step": 0,
                "probes_used": 0,
                "incumbent_safe": None,
                "swapped": False,
                "swap_rank": None,
                "elapsed_seconds": 0.0002,
                "budget_exhausted": False,
                "quiet_skipped": True,
                "incumbent_logit": 4.2,
            },
            {
                "event": "physics_probe_guard",
                "step": 1,
                "probes_used": 3,
                "incumbent_safe": False,
                "swapped": True,
                "swap_rank": 0,
                "elapsed_seconds": 0.4,
                "budget_exhausted": False,
                "quiet_skipped": False,
                "incumbent_logit": -1.1,
            },
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "trace.jsonl"
            path.write_text(
                "".join(json.dumps(record) + "\n" for record in records),
                encoding="utf-8",
            )

            summary = policy_trace_summary(path)

        self.assertEqual(summary["probe_guard_observed_steps"], 2)
        self.assertEqual(summary["probe_guard_quiet_skipped_count"], 1)
        self.assertEqual(summary["probe_guard_swapped_count"], 1)

    def test_probe_guard_summary_counts_unsafe_swaps_and_budget(self):
        records = [
            {
                "event": "physics_probe_guard",
                "step": 0,
                "probes_used": 1,
                "incumbent_safe": True,
                "swapped": False,
                "swap_rank": None,
                "elapsed_seconds": 0.05,
                "budget_exhausted": False,
            },
            {
                "event": "physics_probe_guard",
                "step": 1,
                "probes_used": 3,
                "incumbent_safe": False,
                "swapped": True,
                "swap_rank": 1,
                "elapsed_seconds": 0.2,
                "budget_exhausted": False,
            },
            {
                "event": "physics_probe_guard",
                "step": 2,
                "probes_used": 6,
                "incumbent_safe": False,
                "swapped": False,
                "swap_rank": None,
                "elapsed_seconds": 1.5,
                "budget_exhausted": True,
            },
            {
                "event": "physics_probe_guard",
                "step": 3,
                "probes_used": 1,
                "incumbent_safe": None,
                "swapped": False,
                "swap_rank": None,
                "elapsed_seconds": 0.03,
                "budget_exhausted": False,
            },
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "trace.jsonl"
            path.write_text(
                "".join(json.dumps(record) + "\n" for record in records),
                encoding="utf-8",
            )

            summary = policy_trace_summary(path)

        self.assertEqual(summary["probe_guard_observed_steps"], 4)
        self.assertEqual(summary["probe_guard_unsafe_incumbent_count"], 2)
        self.assertEqual(summary["probe_guard_swapped_count"], 1)
        self.assertEqual(summary["probe_guard_budget_exhausted_count"], 1)
        self.assertEqual(summary["decision_count"], 0)

    def test_multi_axis_shadow_summary_counts_proposals(self):
        record = {
            "event": "decision",
            "candidate_diagnostics": {
                "multi_axis_selector": {
                    "candidate_count": 3,
                    "pareto_front_size": 2,
                    "baseline_dominated": True,
                    "selected_dominated": True,
                    "would_change_action": True,
                    "would_change_selected_action": True,
                    "would_change_item": False,
                    "enforced": False,
                }
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "trace.jsonl"
            path.write_text(json.dumps(record) + "\n", encoding="utf-8")
            summary = policy_trace_summary(path)

        self.assertEqual(summary["multi_axis_observed_steps"], 1)
        self.assertEqual(summary["multi_axis_multi_candidate_steps"], 1)
        self.assertEqual(summary["multi_axis_candidate_count"], 3)
        self.assertEqual(summary["multi_axis_pareto_front_count"], 2)
        self.assertEqual(summary["multi_axis_baseline_dominated_count"], 1)
        self.assertEqual(summary["multi_axis_selected_dominated_count"], 1)
        self.assertEqual(summary["multi_axis_would_change_action_count"], 1)
        self.assertEqual(
            summary["multi_axis_would_change_selected_action_count"], 1
        )
        self.assertEqual(summary["multi_axis_would_change_item_count"], 0)
        self.assertEqual(summary["multi_axis_enforced_count"], 0)

    def test_residual_affordance_summary_keeps_attribute_guard_reach(self):
        record = {
            "event": "decision",
            "candidate_diagnostics": {
                "residual_affordance_shadow": {
                    "candidate_count": 3,
                    "would_change_action": True,
                    "would_change_item": True,
                    "guarded_would_change_action": False,
                    "guarded_would_change_item": False,
                    "attribute_guard_blocked_unrestricted": True,
                    "unrestricted_contract_not_worse": False,
                    "immediate_score_delta": -0.4,
                    "guarded_immediate_score_delta": 0.0,
                }
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "trace.jsonl"
            path.write_text(json.dumps(record) + "\n", encoding="utf-8")

            summary = policy_trace_summary(path)

        self.assertEqual(summary["residual_affordance_observed_steps"], 1)
        self.assertEqual(summary["residual_affordance_candidate_count"], 3)
        self.assertEqual(summary["residual_affordance_would_change_count"], 1)
        self.assertEqual(summary["residual_affordance_guarded_change_count"], 0)
        self.assertEqual(summary["residual_affordance_attr_blocked_count"], 1)
        self.assertEqual(
            summary["residual_affordance_contract_regression_count"], 1
        )
        self.assertAlmostEqual(
            summary["residual_affordance_immediate_delta_total"], -0.4
        )

    def test_temporal_chunk_summary_counts_delay_consensus_and_cost(self):
        record = {
            "event": "decision",
            "step": 5,
            "candidate_diagnostics": {
                "temporal_chunk_ensemble": {
                    "scheduled_count": 2,
                    "static_valid_count": 2,
                    "origin_count": 2,
                    "valid_origin_count": 2,
                    "max_vote_count": 2,
                    "selected_matches_consensus": False,
                    "selected_matches_any_valid_action": True,
                    "selected_matches_any_valid_item": True,
                    "max_item_vote_count": 2,
                    "selected_matches_item_consensus": True,
                    "would_prevent_protocol_fallback": False,
                    "generated_for_future_count": 2,
                    "validation_seconds": 0.003,
                    "generation": {"elapsed_seconds": 0.012},
                    "valid_by_delay": {"1": 1, "2": 1},
                    "scheduled_by_delay": {"1": 1, "2": 1},
                }
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "trace.jsonl"
            path.write_text(json.dumps(record) + "\n", encoding="utf-8")

            summary = policy_trace_summary(path)

        self.assertEqual(summary["temporal_chunk_observed_steps"], 1)
        self.assertEqual(summary["temporal_chunk_scheduled_count"], 2)
        self.assertEqual(summary["temporal_chunk_static_valid_count"], 2)
        self.assertEqual(summary["temporal_chunk_multi_origin_steps"], 1)
        self.assertEqual(summary["temporal_chunk_consensus_steps"], 1)
        self.assertEqual(summary["temporal_chunk_selected_disagree_count"], 1)
        self.assertEqual(
            summary["temporal_chunk_selected_matches_any_action_count"], 1
        )
        self.assertEqual(
            summary["temporal_chunk_selected_matches_any_item_count"], 1
        )
        self.assertEqual(summary["temporal_chunk_item_consensus_steps"], 1)
        self.assertEqual(
            summary["temporal_chunk_selected_item_consensus_match_count"], 1
        )
        self.assertEqual(
            summary["temporal_chunk_selected_item_consensus_disagree_count"], 0
        )
        self.assertEqual(summary["temporal_chunk_generated_count"], 2)
        self.assertEqual(summary["temporal_chunk_valid_by_delay"], {"1": 1, "2": 1})
        self.assertEqual(
            summary["temporal_chunk_scheduled_by_delay"],
            {"1": 1, "2": 1},
        )
        self.assertAlmostEqual(
            summary["temporal_chunk_generation_seconds_total"], 0.012
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


class TerminalFailureChannelTests(unittest.TestCase):
    def test_keeps_transport_topple_slide_and_other_separate(self):
        self.assertEqual(
            terminal_failure_channel(
                {"status": {"is_valid": False}}, {}
            ),
            "transport_invalid",
        )
        self.assertEqual(
            terminal_failure_channel(
                {
                    "status": {"is_valid": True, "is_placed_safe": False},
                    "settle_angle_deg": 31.0,
                },
                {},
            ),
            "topple",
        )
        self.assertEqual(
            terminal_failure_channel(
                {
                    "status": {"is_valid": True, "is_placed_safe": False},
                    "settle_displacement_norm": 0.31,
                },
                {},
            ),
            "slide",
        )
        self.assertEqual(
            terminal_failure_channel(
                {"status": {"is_valid": True, "is_placed_safe": False}},
                {},
            ),
            "unsafe_other",
        )


if __name__ == "__main__":
    unittest.main()


class TrueEnvelopeArmTests(unittest.TestCase):
    def test_submission22_composes_the_two_historical_live_knobs(self):
        env = {
            "ANCHOR_TRUE_ENVELOPE": "1",
            "ANCHOR_FIRST_PASS_ATTEMPTS": "256",
            "LIVE_SEARCH_INTERLEAVE": "8",
        }

        configure_arm_environment(env, "submission22", 2.0, 0.0)

        self.assertEqual(env.pop("ANCHOR_TRUE_ENVELOPE"), "0")
        self.assertEqual(env.pop("ANCHOR_FIRST_PASS_ATTEMPTS"), "64")
        self.assertNotIn("LIVE_SEARCH_INTERLEAVE", env)

    def test_true_envelope_is_the_shipped_baseline_plus_the_flag(self):
        base: dict[str, str] = {}
        arm: dict[str, str] = {}
        configure_arm_environment(base, "base", 2.0, 0.0)
        configure_arm_environment(arm, "true_envelope", 2.0, 0.0)

        self.assertEqual(arm.pop("ANCHOR_TRUE_ENVELOPE"), "1")
        self.assertEqual(arm, base)

    def test_the_box_envelope_stays_reachable_after_the_flip(self):
        """
        The default moved to the true envelope on 2026-08-02 without the
        Task B guard having run. Without this arm the previously shipped
        behaviour would be unmeasurable and the guard could not be settled
        either way.
        """
        base: dict[str, str] = {}
        arm: dict[str, str] = {}
        configure_arm_environment(base, "base", 2.0, 0.0)
        configure_arm_environment(arm, "box_envelope", 2.0, 0.0)

        self.assertEqual(arm.pop("ANCHOR_TRUE_ENVELOPE"), "0")
        self.assertEqual(arm, base)

    def test_base_clears_the_true_envelope_flag(self):
        env = {"ANCHOR_TRUE_ENVELOPE": "1"}

        configure_arm_environment(env, "base", 2.0, 0.0)

        self.assertNotIn("ANCHOR_TRUE_ENVELOPE", env)

    def test_guard_off_arm_actually_turns_the_probe_off(self):
        """
        `base` sets nothing, so it inherits whatever the agent's defaults
        are. When PHYSICS_PROBE_MODE defaulted to guard_quiet on
        2026-08-17, `base` silently stopped being a guard-off baseline --
        its traces carry physics_probe_guard events on every step -- and
        for a day no arm in the registry could turn the guard off. This
        pins the replacement so the next default flip cannot repeat it.
        """
        env: dict[str, str] = {}

        configure_arm_environment(env, "guard_off", 2.0, 0.0)

        self.assertEqual(env.get("PHYSICS_PROBE_MODE"), "off")

    def test_a_control_arm_exists_for_every_default_on_behaviour(self):
        """
        Every knob the shipped agent defaults to an ACTIVE value must have
        some arm that can switch it off, or the shipped behaviour is
        unmeasurable. Checked against the agent's own defaults rather
        than a hardcoded list, so adopting a new default fails here until
        its control arm exists.
        """
        import agent.agent as shipped

        default_on = {
            "PHYSICS_PROBE_MODE": shipped.PHYSICS_PROBE_MODE != "off",
            "ANCHOR_TRUE_ENVELOPE": shipped.ANCHOR_TRUE_ENVELOPE != "0",
        }
        off_values = {
            "PHYSICS_PROBE_MODE": "off",
            "ANCHOR_TRUE_ENVELOPE": "0",
        }
        arms = ("off", "base", "guard_off", "box_envelope", "quiet_guard")
        for knob, is_on in default_on.items():
            if not is_on:
                continue
            reachable = False
            for arm in arms:
                env: dict[str, str] = {}
                configure_arm_environment(env, arm, 2.0, 0.0)
                if env.get(knob) == off_values[knob]:
                    reachable = True
                    break
            self.assertTrue(
                reachable,
                f"{knob} defaults to an active value but no arm sets it "
                f"to {off_values[knob]!r}; the shipped behaviour has no "
                "control",
            )

    def test_headroom_arm_only_moves_the_policy_deadline(self):
        """
        The headroom arm is a measurement, not a candidate: it must be
        the shipped configuration and the deadline, nothing else, or the
        contrast stops being about search time.
        """
        base: dict[str, str] = {}
        arm: dict[str, str] = {}
        configure_arm_environment(base, "base", 2.0, 0.0)
        configure_arm_environment(arm, "headroom", 2.0, 0.0)

        self.assertEqual(arm.pop("POLICY_BUDGET_SECONDS"), "32.5")
        self.assertEqual(arm, base)


class ArmRegistryIntegrityTests(unittest.TestCase):
    """Every named arm must actually configure something.

    An arm listed in the membership set but missing its branch falls
    through and returns {}, which is indistinguishable from `base` --
    the run is labelled as the arm and silently executes the shipped
    default. That already happened twice: `base` stopped being a
    baseline when a default flipped under it, and five reconstruction
    arms were named in a commit whose branches never landed.

    `base` and `base_null` are the deliberate exceptions: they mean
    "shipped defaults" and say so.
    """

    INHERITS_DEFAULTS = {"base", "base_null"}

    def _arm_names(self):
        import ast
        import pathlib

        source = pathlib.Path(
            __file__
        ).resolve().parents[1] / "scripts" / "run_risk_ablation.py"
        tree = ast.parse(source.read_text(encoding="utf-8"))
        names = set()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Set):
                continue
            values = [
                e.value
                for e in node.elts
                if isinstance(e, ast.Constant) and isinstance(e.value, str)
            ]
            if "base" in values and "quiet_guard" in values:
                names.update(values)
        return names

    def test_every_named_arm_configures_something(self):
        missing = []
        for arm in sorted(self._arm_names() - self.INHERITS_DEFAULTS):
            env: dict[str, str] = {}
            configure_arm_environment(env, arm, 2.0, 0.0)
            if not env:
                missing.append(arm)

        self.assertEqual(
            missing,
            [],
            f"named arms with no branch, they silently run as base: "
            f"{missing}",
        )
