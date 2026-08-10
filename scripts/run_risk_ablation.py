"""
Online risk ablation: does Q - lambda*P_hat raise placed/fill?

Runs one full simulator episode for a task-b config under one arm
(risk off, or live mechanics rerank at a given lambda) and appends a
result row; --summarize aggregates all rows collected so far into
per-arm and per-config-paired tables. Rows accumulate across
invocations, so repeats can be added incrementally and scheduled with
run_queue.

Constraints (docs/RELEASE_RISK_PROTOCOL.md section 8): development
configurations only -- final_holdout cases (b001-k40, b001-k10) are
refused; the submission default stays risk-off.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import sys
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.measurement_budget import record_from_env  # noqa: E402
from scripts.run_checks import load_json, run  # noqa: E402

SIMULATOR = ROOT / "simulator"
AGENT = ROOT / "agent" / "agent.py"
DEFAULT_OUTPUT_DIR = ROOT / "reports" / "risk-ablation"
FINAL_HOLDOUT_CASES = frozenset({"b001-k40", "b001-k10"})
DEVELOPMENT_CASES = frozenset(
    {"b000-k15", "b000-k20", "b000-k40", "b001-k20", "b001-k30"}
)
REGISTERED_DEVELOPMENT_BASELINE = {
    "placed": 88.0,
    "fill": 114.6,
}


def configure_arm_environment(
    env: dict[str, str],
    arm: str,
    risk_lambda: float,
    slide_lambda: float,
) -> None:
    """Apply one ablation arm without inheriting experiment controls."""
    for name in (
        "RESCUE_SCAN_ENABLED",
        "RESCUE_SCAN_RESERVE_SECONDS",
        "RESCUE_SCAN_ATTEMPT_BUDGET",
        "RESCUE_SCAN_ATTEMPTS_PER_UNIT",
        "CROSS_STEP_INCUMBENT_MODE",
        "CROSS_STEP_INCUMBENT_PER_ITEM",
        "VISIBLE_POOL_ROLLOUT_MODE",
        "VISIBLE_POOL_ROLLOUT_TOP_K",
        "VISIBLE_POOL_ROLLOUT_DEPTH",
        "VISIBLE_POOL_ROLLOUT_ATTEMPTS",
        "VISIBLE_POOL_ROLLOUT_STRIDE",
        "LIVE_SEARCH_INTERLEAVE",
        "MAX_POOL_ITEMS_EVALUATED",
        "VISIBLE_POOL_ROLLOUT_Q_BAND",
        "LOOKAHEAD_SELECTION_MODE",
        "ANCHOR_FIRST_PASS_ATTEMPTS",
        "LOOKAHEAD_TOP_K",
        "BOARD_CELL_SIZE",
        "BOARD_PROBE_SHAPES",
        "RELEASE_RISK_LIVE_RERANK",
        "RELEASE_RISK_P_MODEL",
        "RELEASE_RISK_RERANK_LAMBDA",
        "RELEASE_RISK_SLIDE_LAMBDA",
        "RELEASE_RISK_SHADOW_RERANK",
        "ANCHOR_FALLBACK_ENABLED",
        "ANCHOR_FALLBACK_STRIDES",
        "ANCHOR_TRUE_ENVELOPE",
        "ANCHOR_TILT_MARGIN_DEG",
        "L3_PREFER_EMPTY_BAND",
        "L3_RELEASE_ROUTE",
        "DEATH_BAND_FALLBACK",
        "DEATH_BAND_SCORE",
        "DEATH_BAND_REQUIRE_DOMINANCE",
        "TEMPORAL_CHUNK_ENSEMBLE_MODE",
        "TEMPORAL_CHUNK_DEPTH",
        "TEMPORAL_CHUNK_ATTEMPTS_PER_STEP",
        "TEMPORAL_CHUNK_STRIDE",
        "TEMPORAL_CHUNK_CELL_SIZE",
        "PLACEMENT_SELECTOR_MODE",
    ):
        env.pop(name, None)
    if arm == "off":
        env["RELEASE_RISK_LIVE_RERANK"] = "0"
    elif arm in {
        "base",
        "rescue",
        "cross_step_shadow",
        "temporal_chunk_shadow",
        "temporal_chunk_shadow_stride4",
        "rollout_shadow",
        "rollout_enforce",
        "anchor_fallback",
        "true_envelope",
        "box_envelope",
        "tilt_margin2",
        "tilt_margin4",
        "l3_prefer_empty",
        "l3_release_route",
        "death_band",
        "no_death_band",
        "death_band_unbanded",
        "death_band_v1",
        "base_null",
        "zone_doctrine",
        "zone_reversed",
        "attr_guard_priority",
        "attr_guard_all",
        "rollout_enforce_stride4",
        "rollout_shadow_stride4",
        "live_interleave4",
        "live_interleave8",
        "item_cap16",
        "item_cap20",
        "board_k3",
        "board_k8",
        "board_k16",
        "topk8",
        "first_pass16",
        "first_pass32",
        "first_pass64",
        "first_pass128",
        "first_pass256",
        "structured_noop",
        "structured_retained",
    }:
        if arm == "anchor_fallback":
            env["ANCHOR_FALLBACK_ENABLED"] = "1"
        elif arm == "true_envelope":
            # Redundant since the default flipped on 2026-08-02, kept so a
            # run can pin the value explicitly rather than inherit it.
            env["ANCHOR_TRUE_ENVELOPE"] = "1"
        elif arm == "death_band_v1":
            # The version that shipped and regressed: swap on P_rot alone,
            # no support-ratio dominance requirement.
            env["DEATH_BAND_FALLBACK"] = "1"
            env["DEATH_BAND_REQUIRE_DOMINANCE"] = "0"
        elif arm == "death_band_unbanded":
            # P_rot alone, no score pre-filter: prices the fitted -1.5 by
            # measuring what the gate does without it.
            env["DEATH_BAND_SCORE"] = ""
        elif arm == "base_null":
            pass  # identical to base: carries the run's own noise floor
        elif arm == "structured_noop":
            # Same scoring and settled-first selection as base, but through
            # the explicit proposal/evaluation/selector/command contracts.
            # This is the physical negative control for abstraction cost.
            env["PLACEMENT_SELECTOR_MODE"] = "structured_noop"
        elif arm == "structured_retained":
            # Preserve the scalar generator/ranker hot path and materialize
            # named terms only for decisions retained by final selection.
            env["PLACEMENT_SELECTOR_MODE"] = "structured_retained"
        elif arm == "zone_doctrine":
            # Loading order over zones: shelf top, deep, centre, under the
            # shelf. The corridor scan is what motivates it -- 62.9% of the
            # free-and-fits poses at a terminal board are refused only by
            # transport_path_clear, and they sit deep.
            env["ZONE_ORDER"] = "doctrine"
        elif arm == "attr_guard_priority":
            # Refuse release poses whose settled proxy rests on a priority
            # top. At the board c000-k1 dies on, all 950 legal release
            # candidates rest on soft or priority cargo, so this is the
            # population -- and the risk is that removing it leaves no legal
            # pose and simply ends the episode sooner. `priority` is the
            # narrower half of that population and is measured separately
            # from `all` for exactly that reason.
            env["RELEASE_ATTRIBUTE_GUARD"] = "priority"
        elif arm == "attr_guard_all":
            env["RELEASE_ATTRIBUTE_GUARD"] = "all"
        elif arm == "zone_reversed":
            # The same machinery pointed the other way. Without it a
            # doctrine arm that beats base has only shown that SOME zone
            # bonus helps, not that this order is the right one.
            env["ZONE_ORDER"] = "reversed"
        elif arm == "death_band":
            # Redundant since the default flipped on 2026-08-04; kept so a
            # run can pin the value explicitly rather than inherit it.
            env["DEATH_BAND_FALLBACK"] = "1"
        elif arm == "no_death_band":
            env["DEATH_BAND_FALLBACK"] = "0"
        elif arm == "l3_release_route":
            env["L3_RELEASE_ROUTE"] = "1"
        elif arm == "l3_prefer_empty":
            env["L3_PREFER_EMPTY_BAND"] = "0.15"
        elif arm == "tilt_margin2":
            env["ANCHOR_TILT_MARGIN_DEG"] = "2"
        elif arm == "tilt_margin4":
            env["ANCHOR_TILT_MARGIN_DEG"] = "4"
        elif arm == "box_envelope":
            # The pre-2026-08-02 box formula. Kept for the same reason
            # first_pass64 was kept when that default moved: the previously
            # shipped behaviour has to stay measurable rather than become
            # unreachable, and the Task B guard for the flip has not run.
            env["ANCHOR_TRUE_ENVELOPE"] = "0"
        elif arm == "rescue":
            env["RESCUE_SCAN_ENABLED"] = "1"
        elif arm == "cross_step_shadow":
            env["CROSS_STEP_INCUMBENT_MODE"] = "shadow"
        elif arm == "temporal_chunk_shadow":
            env["TEMPORAL_CHUNK_ENSEMBLE_MODE"] = "shadow"
        elif arm == "temporal_chunk_shadow_stride4":
            env["TEMPORAL_CHUNK_ENSEMBLE_MODE"] = "shadow"
            env["TEMPORAL_CHUNK_STRIDE"] = "4"
        elif arm == "rollout_shadow":
            env["VISIBLE_POOL_ROLLOUT_MODE"] = "shadow"
        elif arm == "rollout_enforce":
            env["VISIBLE_POOL_ROLLOUT_MODE"] = "enforce"
        elif arm == "rollout_shadow_stride4":
            # Same telemetry as rollout_shadow, but the rollout's future
            # search spreads its unchanged per-step attempt budget over the
            # anchor grid instead of its prefix.
            env["VISIBLE_POOL_ROLLOUT_MODE"] = "shadow"
            env["VISIBLE_POOL_ROLLOUT_STRIDE"] = "4"
        elif arm == "rollout_enforce_stride4":
            env["VISIBLE_POOL_ROLLOUT_MODE"] = "enforce"
            env["VISIBLE_POOL_ROLLOUT_STRIDE"] = "4"
        elif arm == "live_interleave4":
            # The live candidate search only; the rollout stays off. This is
            # a scan-ORDER change, not a search-breadth change: a unit that
            # exhausts still sees the identical anchor set.
            env["LIVE_SEARCH_INTERLEAVE"] = "4"
        elif arm == "live_interleave8":
            env["LIVE_SEARCH_INTERLEAVE"] = "8"
        elif arm == "item_cap16":
            # Item-dimension breadth. The anchor dimension has twice failed
            # a breadth intervention; this is the axis where one worked.
            env["MAX_POOL_ITEMS_EVALUATED"] = "16"
        elif arm == "item_cap20":
            env["MAX_POOL_ITEMS_EVALUATED"] = "20"
        elif arm.startswith("board_k"):
            # The ranker proposes, the board disposes: keep the same top-K
            # search and reorder it by acceptance breadth, alternativity and
            # sealed void instead of by the discounted lookahead sum.
            env["LOOKAHEAD_SELECTION_MODE"] = "board"
            env["LOOKAHEAD_TOP_K"] = arm.removeprefix("board_k")
        elif arm.startswith("first_pass"):
            # Depth per unit on the first breadth-first pass. The probe in
            # reports/same-class-stacking puts the cliff between 64 and 256
            # attempts per item; 128 is there because a cliff located
            # between two points is not a located cliff. The 16 and 32 rungs
            # were added for a Task C hypothesis that the sweep then refuted:
            # depth is inert on c001-k1 (identical placed, fill and death at
            # every rung, because that space holds no solution at any budget)
            # and non-monotonic on c000-k1. Kept so the refutation stays
            # reproducible. first_pass64 is kept after the default moved to
            # 256 so the old shipped behaviour stays measurable rather than
            # becoming unreachable.
            env["ANCHOR_FIRST_PASS_ATTEMPTS"] = arm.removeprefix("first_pass")
        elif arm == "topk8":
            # Control for board_k8. Widening the top-K alone also changes
            # the decision, so a board_k8 win over base confounds the board
            # features with the wider candidate set.
            env["LOOKAHEAD_TOP_K"] = "8"
    else:
        env["RELEASE_RISK_LIVE_RERANK"] = "1"
        env["RELEASE_RISK_P_MODEL"] = "mech"
        env["RELEASE_RISK_RERANK_LAMBDA"] = str(risk_lambda)
    if slide_lambda > 0.0:
        env["RELEASE_RISK_SLIDE_LAMBDA"] = str(slide_lambda)


def sync_agent_into_simulator() -> None:
    """
    The simulator imports SIMULATOR/agent.py, which is a copy -- the
    checks harness refreshes it before every run (run_checks.py). Without
    this step an ablation silently measures a stale agent on BOTH arms
    (that is exactly how round 1 failed). Content-compare first so
    parallel episodes of the same commit skip the racy rewrite.
    """
    target = SIMULATOR / "agent.py"
    # AGENT_PATH lets a previously submitted agent.py be replayed. Without
    # it this sync silently overwrites any hand-placed simulator/agent.py
    # with the working tree, so an attempt to measure an OLD build ends up
    # measuring the current one and reports the two as identical.
    source = pathlib.Path(os.environ.get("AGENT_PATH", "") or AGENT)
    source_bytes = source.read_bytes()
    if target.exists() and target.read_bytes() == source_bytes:
        return
    target.write_bytes(source_bytes)


def terminal_failure_channel(final_step: dict, place_states: dict) -> str:
    """Classify the terminal action without collapsing physical labels."""
    status = final_step.get("status") or place_states or {}
    is_valid = status.get("is_valid")
    is_safe = status.get("is_placed_safe")
    angle = float(final_step.get("settle_angle_deg") or 0.0)
    displacement = float(
        final_step.get("settle_displacement_norm") or 0.0
    )
    if is_valid is False:
        return "transport_invalid"
    if angle > 30.0:
        return "topple"
    if displacement > 0.3:
        return "slide"
    if is_safe is False:
        return "unsafe_other"
    return "safe_end"


def case_summary(
    evaluation: Any, config: dict[str, Any]
) -> dict[str, Any]:
    cases = {}
    if not isinstance(evaluation, dict):
        return cases
    for case_id, case in evaluation.items():
        if not isinstance(case, dict):
            continue
        item_list = (
            config.get(case_id, {})
            .get("item_stream", {})
            .get("item_list", [])
        )
        score = case.get("evaluation") or {}
        place_states = case.get("place_states") or {}
        placed_fraction = float(score.get("num_placed_items", 0.0))
        steps = score.get("step_metrics") or []
        final_step = steps[-1] if steps else {}
        # Copy every scalar score component generically: the bundled
        # simulator only emits fill_score / num_placed_items, but the
        # official environment adds cog_score, stability_score,
        # placement_score, and soft_item_score -- picked up here
        # automatically when present.
        components = {
            key: float(value)
            for key, value in score.items()
            if isinstance(value, (int, float))
        }
        angles = [
            float(step["settle_angle_deg"])
            for step in steps
            if step.get("settle_angle_deg") is not None
        ]
        displacements = [
            float(step["settle_displacement_norm"])
            for step in steps
            if step.get("settle_displacement_norm") is not None
        ]
        # placement_score and soft_item_score are computed only on the
        # evaluation platform. These are the published rules behind them,
        # as violation counts on the final settled state -- a monotone
        # proxy for comparing arms, never a stand-in for the official
        # number. See simulator/src/ground_handling/diagnostics.py.
        attribute_placement = {
            key: final_step.get(key)
            for key in (
                "priority_items",
                "soft_items",
                "has_priority_container",
                "priority_covered_by_other",
                "priority_misrouted",
                "soft_covered_by_other",
                "priority_clean_ratio",
                "soft_clean_ratio",
            )
            if key in final_step
        }
        cases[case_id] = {
            "status": case.get("status"),
            "message": case.get("message"),
            "attribute_placement": attribute_placement,
            # Local proxy for stability_score, from the end-of-episode shake.
            # Undisclosed protocol, so a monotone comparator between arms and
            # never the official number.
            "shake_response": score.get("shake_response") or {},
            # Raw centre of gravity. cog_score has no published procedure,
            # so com_contract ships with the numbers; see diagnostics.py.
            "center_of_gravity": {
                key: final_step.get(key)
                for key in (
                    "com_z",
                    "com_z_above_floor",
                    "com_height_ratio",
                    "com_contract",
                )
                if key in final_step
            },
            # Stability proxies (per the diagnostics decomposition: no
            # pseudo-total score, each proxy kept separate).
            "max_settle_angle_deg": max(angles) if angles else None,
            "settle_over_30_steps": sum(1 for a in angles if a > 30.0),
            "settle_5_to_30_steps": sum(
                1 for a in angles if 5.0 < a <= 30.0
            ),
            "mean_settle_displacement": (
                sum(displacements) / len(displacements)
                if displacements
                else None
            ),
            "final_surface_total_variation": (
                float(final_step["surface_total_variation"])
                if "surface_total_variation" in final_step
                else None
            ),
            "final_flat_support_edge_ratio": (
                float(final_step["flat_support_edge_ratio"])
                if "flat_support_edge_ratio" in final_step
                else None
            ),
            "fill_score": float(score.get("fill_score", 0.0)),
            "score_components": components,
            "placed_fraction": placed_fraction,
            "placed_count": int(round(placed_fraction * len(item_list))),
            "total_items": len(item_list),
            "steps": len(steps),
            "is_included": place_states.get("is_included") is True,
            "is_valid": place_states.get("is_valid") is True,
            "is_placed_safe": place_states.get("is_placed_safe") is True,
            "terminal_channel": terminal_failure_channel(
                final_step, place_states
            ),
            "final_com_z": (
                float(final_step["center_of_mass_z"])
                if "center_of_mass_z" in final_step
                else None
            ),
            "final_surface_height_std": (
                float(final_step["surface_height_std"])
                if "surface_height_std" in final_step
                else None
            ),
            "policy_seconds": float(
                (case.get("time_results") or {}).get("policy", 0.0)
            ),
        }
    return cases


def policy_trace_summary(path: pathlib.Path) -> dict[str, Any]:
    summary = {
        "decision_count": 0,
        "search_attempts_total": 0,
        "search_attempts_max": 0,
        "structured_evaluation_count": 0,
        "rescue_trigger_count": 0,
        "rescue_action_count": 0,
        "protocol_fallback_count": 0,
        "cross_step_observed_steps": 0,
        "cross_step_previous_count": 0,
        "cross_step_pool_survivor_count": 0,
        "cross_step_static_valid_count": 0,
        "cross_step_would_prevent_fallback_count": 0,
        "cross_step_validation_seconds_total": 0.0,
        "cross_step_validation_seconds_max": 0.0,
        "cross_step_deadline_overrun_count": 0,
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
    }
    if not path.exists():
        return summary
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            if record.get("event") != "decision":
                continue
            summary["decision_count"] += 1
            source = record.get("action_source")
            if source == "rescue_scan":
                summary["rescue_action_count"] += 1
            if source in {
                "fixed_fallback",
                "unsafe_protocol_fallback",
            }:
                summary["protocol_fallback_count"] += 1
            diagnostics = record.get("candidate_diagnostics")
            search = (
                diagnostics.get("search")
                if isinstance(diagnostics, dict)
                else None
            )
            if isinstance(search, dict):
                attempts = int(search.get("attempts_consumed", 0))
                summary["search_attempts_total"] += attempts
                summary["search_attempts_max"] = max(
                    summary["search_attempts_max"], attempts
                )
            if (
                isinstance(diagnostics, dict)
                and isinstance(
                    diagnostics.get("selected_candidate_evaluation"), dict
                )
            ):
                summary["structured_evaluation_count"] += 1
            rescue = (
                diagnostics.get("rescue_scan")
                if isinstance(diagnostics, dict)
                else None
            )
            if isinstance(rescue, dict) and rescue.get("triggered") is True:
                summary["rescue_trigger_count"] += 1
            cross_step = (
                diagnostics.get("cross_step_incumbent")
                if isinstance(diagnostics, dict)
                else None
            )
            if isinstance(cross_step, dict):
                summary["cross_step_observed_steps"] += 1
                summary["cross_step_previous_count"] += int(
                    cross_step.get("previous_count", 0)
                )
                summary["cross_step_pool_survivor_count"] += int(
                    cross_step.get("pool_survivor_count", 0)
                )
                summary["cross_step_static_valid_count"] += int(
                    cross_step.get("static_valid_count", 0)
                )
                if cross_step.get("would_prevent_protocol_fallback") is True:
                    summary[
                        "cross_step_would_prevent_fallback_count"
                    ] += 1
                validation_seconds = float(
                    cross_step.get("validation_seconds", 0.0)
                )
                summary["cross_step_validation_seconds_total"] += (
                    validation_seconds
                )
                summary["cross_step_validation_seconds_max"] = max(
                    summary["cross_step_validation_seconds_max"],
                    validation_seconds,
                )
                remaining = cross_step.get(
                    "deadline_remaining_after_validation"
                )
                if remaining is not None and float(remaining) < 0.0:
                    summary["cross_step_deadline_overrun_count"] += 1
            temporal = (
                diagnostics.get("temporal_chunk_ensemble")
                if isinstance(diagnostics, dict)
                else None
            )
            if isinstance(temporal, dict):
                summary["temporal_chunk_observed_steps"] += 1
                summary["temporal_chunk_scheduled_count"] += int(
                    temporal.get("scheduled_count", 0)
                )
                summary["temporal_chunk_static_valid_count"] += int(
                    temporal.get("static_valid_count", 0)
                )
                summary["temporal_chunk_multi_origin_steps"] += int(
                    int(temporal.get("valid_origin_count", 0)) >= 2
                )
                has_consensus = int(temporal.get("max_vote_count", 0)) >= 2
                summary["temporal_chunk_consensus_steps"] += int(
                    has_consensus
                )
                if has_consensus:
                    if temporal.get("selected_matches_consensus") is True:
                        summary[
                            "temporal_chunk_selected_match_count"
                        ] += 1
                    else:
                        summary[
                            "temporal_chunk_selected_disagree_count"
                        ] += 1
                summary[
                    "temporal_chunk_selected_matches_any_action_count"
                ] += int(
                    temporal.get("selected_matches_any_valid_action") is True
                )
                summary[
                    "temporal_chunk_selected_matches_any_item_count"
                ] += int(
                    temporal.get("selected_matches_any_valid_item") is True
                )
                has_item_consensus = (
                    int(temporal.get("max_item_vote_count", 0)) >= 2
                )
                summary["temporal_chunk_item_consensus_steps"] += int(
                    has_item_consensus
                )
                if has_item_consensus:
                    if (
                        temporal.get("selected_matches_item_consensus")
                        is True
                    ):
                        summary[
                            "temporal_chunk_selected_item_consensus_match_count"
                        ] += 1
                    else:
                        summary[
                            "temporal_chunk_selected_item_consensus_disagree_count"
                        ] += 1
                if temporal.get("would_prevent_protocol_fallback") is True:
                    summary[
                        "temporal_chunk_would_prevent_fallback_count"
                    ] += 1
                summary["temporal_chunk_generated_count"] += int(
                    temporal.get("generated_for_future_count", 0)
                )
                validation_seconds = float(
                    temporal.get("validation_seconds", 0.0)
                )
                summary[
                    "temporal_chunk_validation_seconds_total"
                ] += validation_seconds
                summary["temporal_chunk_validation_seconds_max"] = max(
                    summary["temporal_chunk_validation_seconds_max"],
                    validation_seconds,
                )
                generation = temporal.get("generation")
                generation_seconds = (
                    float(generation.get("elapsed_seconds", 0.0))
                    if isinstance(generation, dict)
                    else 0.0
                )
                summary[
                    "temporal_chunk_generation_seconds_total"
                ] += generation_seconds
                summary["temporal_chunk_generation_seconds_max"] = max(
                    summary["temporal_chunk_generation_seconds_max"],
                    generation_seconds,
                )
                for delay, count in temporal.get(
                    "valid_by_delay", {}
                ).items():
                    delay_key = str(delay)
                    summary["temporal_chunk_valid_by_delay"][delay_key] = (
                        summary["temporal_chunk_valid_by_delay"].get(
                            delay_key, 0
                        )
                        + int(count)
                    )
                for delay, count in temporal.get(
                    "scheduled_by_delay", {}
                ).items():
                    delay_key = str(delay)
                    summary[
                        "temporal_chunk_scheduled_by_delay"
                    ][delay_key] = (
                        summary["temporal_chunk_scheduled_by_delay"].get(
                            delay_key, 0
                        )
                        + int(count)
                    )
            rollout = (
                diagnostics.get("visible_pool_rollout")
                if isinstance(diagnostics, dict)
                else None
            )
            if isinstance(rollout, dict):
                summary["rollout_observed_steps"] += 1
                summary["rollout_candidate_count"] += int(
                    rollout.get("candidate_count", 0)
                )
                summary["rollout_eligible_count"] += int(
                    rollout.get("eligible_count", 0)
                )
                if rollout.get("would_change_item") is True:
                    summary["rollout_would_change_count"] += 1
                unrestricted_change = bool(
                    rollout.get("unrestricted_would_change_item") is True
                )
                if unrestricted_change:
                    summary["rollout_unrestricted_change_count"] += 1
                    if rollout.get(
                        "unrestricted_proposal_within_q_band"
                    ) is True:
                        summary[
                            "rollout_unrestricted_within_band_count"
                        ] += 1
                    q_loss = float(
                        rollout.get("unrestricted_proposed_q_loss", 0.0)
                    )
                    if q_loss <= 0.0:
                        q_bin = "nonpositive"
                    elif q_loss <= 0.05:
                        q_bin = "0_to_0.05"
                    elif q_loss <= 0.10:
                        q_bin = "0.05_to_0.10"
                    elif q_loss <= 0.15:
                        q_bin = "0.10_to_0.15"
                    else:
                        q_bin = "over_0.15"
                    summary["rollout_q_loss_bins"][q_bin] += 1
                if rollout.get("enforced") is True:
                    summary["rollout_enforced_count"] += 1
                keys = {
                    tuple(candidate.get("rollout_key", []))
                    for candidate in rollout.get("candidates", [])
                    if isinstance(candidate, dict)
                }
                if len(keys) > 1:
                    summary["rollout_non_degenerate_count"] += 1
                elapsed = float(rollout.get("elapsed_seconds", 0.0))
                summary["rollout_seconds_total"] += elapsed
                summary["rollout_seconds_max"] = max(
                    summary["rollout_seconds_max"], elapsed
                )
                step_key = str(int(record.get("step", -1)))
                step_bucket = summary["rollout_by_step"].setdefault(
                    step_key,
                    {
                        "observed": 0,
                        "non_degenerate": 0,
                        "would_change": 0,
                        "enforced": 0,
                        "unrestricted_change": 0,
                        "seconds_total": 0.0,
                        "seconds_max": 0.0,
                    },
                )
                step_bucket["observed"] += 1
                step_bucket["non_degenerate"] += int(len(keys) > 1)
                step_bucket["would_change"] += int(
                    rollout.get("would_change_item") is True
                )
                step_bucket["enforced"] += int(
                    rollout.get("enforced") is True
                )
                step_bucket["unrestricted_change"] += int(
                    unrestricted_change
                )
                step_bucket["seconds_total"] += elapsed
                step_bucket["seconds_max"] = max(
                    step_bucket["seconds_max"], elapsed
                )
    return summary


def run_episode(
    config_path: pathlib.Path,
    arm: str,
    risk_lambda: float,
    repeat: int,
    output_dir: pathlib.Path,
    open_final_holdout: bool = False,
    slide_lambda: float = 0.0,
) -> dict[str, Any]:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    case_ids = list(config)
    holdout = FINAL_HOLDOUT_CASES.intersection(case_ids)
    if holdout and not open_final_holdout:
        raise SystemExit(
            f"refusing to run online ablation on final_holdout cases: "
            f"{sorted(holdout)} (protocol section 8; the one-shot final "
            "evaluation passes --open-final-holdout explicitly)"
        )

    sync_agent_into_simulator()
    label = f"{'-'.join(case_ids)}-{arm}-r{repeat}"
    run_dir = output_dir / "runs" / label
    run_dir.mkdir(parents=True, exist_ok=True)
    result_path = run_dir / "evaluation_results.json"

    env = os.environ.copy()
    env["PYTHONPATH"] = str(SIMULATOR)
    configure_arm_environment(env, arm, risk_lambda, slide_lambda)
    trace_path = run_dir / "policy-trace.jsonl"
    env["NEDO_POLICY_TRACE_PATH"] = str(trace_path.resolve())

    record_from_env(1)
    result = run(
        [
            sys.executable,
            "scripts/run_test.py",
            "--config-path",
            str(config_path.resolve()),
            "--module-path",
            "",
            "--result-dir",
            str(run_dir.resolve()),
            "--result-fname",
            result_path.name,
        ],
        SIMULATOR,
        env,
    )
    (run_dir / "simulator.log").write_text(
        result["stdout"] + result["stderr"], encoding="utf-8"
    )
    evaluation = load_json(result_path)
    row = {
        "label": label,
        "arm": arm,
        "risk_lambda": risk_lambda if arm not in ("off", "base") else None,
        "slide_lambda": slide_lambda if slide_lambda > 0.0 else None,
        "repeat": repeat,
        "config": config_path.name,
        "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(
            timespec="seconds"
        ),
        "process_returncode": result["returncode"],
        "process_seconds": result["seconds"],
        "cases": case_summary(evaluation, config),
        "policy_trace": policy_trace_summary(trace_path),
    }
    rows_path = output_dir / "rows.jsonl"
    with rows_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


def load_rows(output_dir: pathlib.Path) -> list[dict[str, Any]]:
    rows_path = output_dir / "rows.jsonl"
    if not rows_path.exists():
        return []
    rows = []
    with rows_path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    per_arm: dict[str, dict[str, list[float]]] = {}
    per_case_arm: dict[tuple[str, str], dict[str, list[float]]] = {}
    terminal_channels_by_arm: dict[str, dict[str, int]] = {}
    policy_trace_by_arm: dict[str, dict[str, float]] = {}
    for row in rows:
        if row["process_returncode"] != 0:
            continue
        trace = row.get("policy_trace")
        if isinstance(trace, dict):
            trace_bucket = policy_trace_by_arm.setdefault(
                row["arm"],
                {
                    "episodes": 0,
                    "decision_count": 0,
                    "search_attempts_total": 0,
                    "search_attempts_max": 0,
                    "structured_evaluation_count": 0,
                    "observed_steps": 0,
                    "previous_count": 0,
                    "pool_survivor_count": 0,
                    "static_valid_count": 0,
                    "would_prevent_fallback_count": 0,
                    "validation_seconds_total": 0.0,
                    "validation_seconds_max": 0.0,
                    "deadline_overrun_count": 0,
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
                    "rollout_q_loss_bins": {},
                    "rollout_by_step": {},
                    "rollout_seconds_total": 0.0,
                    "rollout_seconds_max": 0.0,
                },
            )
            trace_bucket["episodes"] += 1
            trace_bucket["decision_count"] += int(
                trace.get("decision_count", 0)
            )
            trace_bucket["search_attempts_total"] += int(
                trace.get("search_attempts_total", 0)
            )
            trace_bucket["search_attempts_max"] = max(
                trace_bucket["search_attempts_max"],
                int(trace.get("search_attempts_max", 0)),
            )
            trace_bucket["structured_evaluation_count"] += int(
                trace.get("structured_evaluation_count", 0)
            )
            trace_bucket["observed_steps"] += int(
                trace.get("cross_step_observed_steps", 0)
            )
            trace_bucket["previous_count"] += int(
                trace.get("cross_step_previous_count", 0)
            )
            trace_bucket["pool_survivor_count"] += int(
                trace.get("cross_step_pool_survivor_count", 0)
            )
            trace_bucket["static_valid_count"] += int(
                trace.get("cross_step_static_valid_count", 0)
            )
            trace_bucket["would_prevent_fallback_count"] += int(
                trace.get(
                    "cross_step_would_prevent_fallback_count", 0
                )
            )
            trace_bucket["validation_seconds_total"] += float(
                trace.get("cross_step_validation_seconds_total", 0.0)
            )
            trace_bucket["validation_seconds_max"] = max(
                trace_bucket["validation_seconds_max"],
                float(
                    trace.get("cross_step_validation_seconds_max", 0.0)
                ),
            )
            trace_bucket["deadline_overrun_count"] += int(
                trace.get("cross_step_deadline_overrun_count", 0)
            )
            for name in (
                "temporal_chunk_observed_steps",
                "temporal_chunk_scheduled_count",
                "temporal_chunk_static_valid_count",
                "temporal_chunk_multi_origin_steps",
                "temporal_chunk_consensus_steps",
                "temporal_chunk_selected_match_count",
                "temporal_chunk_selected_disagree_count",
                "temporal_chunk_selected_matches_any_action_count",
                "temporal_chunk_selected_matches_any_item_count",
                "temporal_chunk_item_consensus_steps",
                "temporal_chunk_selected_item_consensus_match_count",
                "temporal_chunk_selected_item_consensus_disagree_count",
                "temporal_chunk_would_prevent_fallback_count",
                "temporal_chunk_generated_count",
            ):
                trace_bucket[name] += int(trace.get(name, 0))
            for name in (
                "temporal_chunk_validation_seconds_total",
                "temporal_chunk_generation_seconds_total",
            ):
                trace_bucket[name] += float(trace.get(name, 0.0))
            for name in (
                "temporal_chunk_validation_seconds_max",
                "temporal_chunk_generation_seconds_max",
            ):
                trace_bucket[name] = max(
                    trace_bucket[name], float(trace.get(name, 0.0))
                )
            for delay, count in trace.get(
                "temporal_chunk_valid_by_delay", {}
            ).items():
                delay_key = str(delay)
                trace_bucket["temporal_chunk_valid_by_delay"][delay_key] = (
                    trace_bucket["temporal_chunk_valid_by_delay"].get(
                        delay_key, 0
                    )
                    + int(count)
                )
            for delay, count in trace.get(
                "temporal_chunk_scheduled_by_delay", {}
            ).items():
                delay_key = str(delay)
                trace_bucket[
                    "temporal_chunk_scheduled_by_delay"
                ][delay_key] = (
                    trace_bucket["temporal_chunk_scheduled_by_delay"].get(
                        delay_key, 0
                    )
                    + int(count)
                )
            for name in (
                "rollout_observed_steps",
                "rollout_candidate_count",
                "rollout_eligible_count",
                "rollout_non_degenerate_count",
                "rollout_would_change_count",
                "rollout_unrestricted_change_count",
                "rollout_unrestricted_within_band_count",
                "rollout_enforced_count",
            ):
                trace_bucket[name] += int(trace.get(name, 0))
            for q_bin, count in trace.get(
                "rollout_q_loss_bins", {}
            ).items():
                trace_bucket["rollout_q_loss_bins"][q_bin] = (
                    trace_bucket["rollout_q_loss_bins"].get(q_bin, 0)
                    + int(count)
                )
            for step, values in trace.get("rollout_by_step", {}).items():
                step_bucket = trace_bucket["rollout_by_step"].setdefault(
                    str(step),
                    {
                        "observed": 0,
                        "non_degenerate": 0,
                        "would_change": 0,
                        "enforced": 0,
                        "unrestricted_change": 0,
                        "seconds_total": 0.0,
                        "seconds_max": 0.0,
                    },
                )
                for name in (
                    "observed",
                    "non_degenerate",
                    "would_change",
                    "enforced",
                    "unrestricted_change",
                ):
                    step_bucket[name] += int(values.get(name, 0))
                step_bucket["seconds_total"] += float(
                    values.get("seconds_total", 0.0)
                )
                step_bucket["seconds_max"] = max(
                    step_bucket["seconds_max"],
                    float(values.get("seconds_max", 0.0)),
                )
            trace_bucket["rollout_seconds_total"] += float(
                trace.get("rollout_seconds_total", 0.0)
            )
            trace_bucket["rollout_seconds_max"] = max(
                trace_bucket["rollout_seconds_max"],
                float(trace.get("rollout_seconds_max", 0.0)),
            )
        for case_id, case in row["cases"].items():
            arm_bucket = per_arm.setdefault(
                row["arm"],
                {
                    "placed": [],
                    "fill": [],
                    "steps": [],
                    "com_z": [],
                    "near_miss": [],
                    "surface_tv": [],
                    "shake_max_shift": [],
                    "shake_peak_ke": [],
                    "shake_shifted": [],
                    "shake_toppled": [],
                    "shake_shifted_fraction": [],
                    "priority_clean": [],
                    "soft_clean": [],
                    "policy_seconds": [],
                    "official_cog": [],
                    "official_stability": [],
                    "official_placement": [],
                    "official_soft": [],
                    "terminal_included": [],
                    "terminal_valid": [],
                    "terminal_placed_safe": [],
                },
            )
            case_bucket = per_case_arm.setdefault(
                (case_id, row["arm"]), {}
            )

            def record(metric, value):
                if not isinstance(value, (int, float)):
                    return
                arm_bucket[metric].append(float(value))
                case_bucket.setdefault(metric, []).append(float(value))

            record("placed", case["placed_count"])
            record("fill", case["fill_score"])
            record("steps", case["steps"])
            if case.get("final_com_z") is not None:
                record("com_z", case["final_com_z"])
            if case.get("settle_5_to_30_steps") is not None:
                record("near_miss", case["settle_5_to_30_steps"])
            if case.get("final_surface_total_variation") is not None:
                record(
                    "surface_tv", case["final_surface_total_variation"]
                )
            record("policy_seconds", case.get("policy_seconds"))
            attribute = case.get("attribute_placement") or {}
            record("priority_clean", attribute.get("priority_clean_ratio"))
            record("soft_clean", attribute.get("soft_clean_ratio"))
            official = case.get("score_components") or {}
            for metric, component in (
                ("official_cog", "cog_score"),
                ("official_stability", "stability_score"),
                ("official_placement", "placement_score"),
                ("official_soft", "soft_item_score"),
            ):
                record(metric, official.get(component))
            for metric, field in (
                ("terminal_included", "is_included"),
                ("terminal_valid", "is_valid"),
                ("terminal_placed_safe", "is_placed_safe"),
            ):
                value = case.get(field)
                if isinstance(value, bool):
                    record(metric, float(value))
            # The shake proxy has been carried in every row since it was
            # added and aggregated by nothing, which is how a selection
            # change shipped on a placed gain while worsening peak kinetic
            # energy by 74% (AGENT_OPERATIONS 5.05). It is the only local
            # stand-in whose direction has ever agreed with an official
            # component, so it belongs in the table the reader actually
            # sees.
            shake = case.get("shake_response") or {}
            for bucket_key, shake_key in (
                ("shake_max_shift", "shake_max_shift"),
                ("shake_peak_ke", "shake_peak_kinetic_energy"),
                ("shake_shifted", "shake_items_shifted"),
            ):
                value = shake.get(shake_key)
                record(bucket_key, value)
            record("shake_toppled", shake.get("shake_items_toppled"))
            shake_items = shake.get("shake_items")
            shake_shifted = shake.get("shake_items_shifted")
            if (
                isinstance(shake_items, (int, float))
                and shake_items > 0
                and isinstance(shake_shifted, (int, float))
            ):
                record(
                    "shake_shifted_fraction",
                    float(shake_shifted) / float(shake_items),
                )
            channel = str(case.get("terminal_channel") or "unknown")
            channel_bucket = terminal_channels_by_arm.setdefault(
                row["arm"], {}
            )
            channel_bucket[channel] = channel_bucket.get(channel, 0) + 1

    def stats(values: list[float]) -> dict[str, float]:
        if not values:
            return {"n": 0}
        mean = sum(values) / len(values)
        return {
            "n": len(values),
            "mean": round(mean, 3),
            "min": min(values),
            "max": max(values),
        }

    arms = {
        arm: {metric: stats(vals) for metric, vals in buckets.items()}
        for arm, buckets in per_arm.items()
    }
    cases: dict[str, Any] = {}
    for (case_id, arm), buckets in sorted(per_case_arm.items()):
        cases.setdefault(case_id, {})[arm] = {
            metric: stats(vals) for metric, vals in buckets.items()
        }
    available_arms = set(per_arm)
    baseline_arm = "off" if "off" in available_arms else "base"
    paired = {}
    paired_full_vector = {}
    for case_id, arm_stats in cases.items():
        baseline = arm_stats.get(baseline_arm)
        for arm, arm_stat in arm_stats.items():
            if (
                arm == baseline_arm
                or not baseline
                or baseline["placed"]["n"] == 0
            ):
                continue
            if arm_stat["placed"]["n"] == 0:
                continue
            paired.setdefault(arm, {})[case_id] = {
                "placed_diff": round(
                    arm_stat["placed"]["mean"]
                    - baseline["placed"]["mean"],
                    3,
                ),
                "fill_diff": round(
                    arm_stat["fill"]["mean"]
                    - baseline["fill"]["mean"],
                    3,
                ),
            }
            metric_diffs = {}
            for metric, arm_metric in arm_stat.items():
                baseline_metric = baseline.get(metric)
                if (
                    not isinstance(baseline_metric, dict)
                    or baseline_metric.get("n", 0) == 0
                    or arm_metric.get("n", 0) == 0
                ):
                    continue
                metric_diffs[metric] = round(
                    arm_metric["mean"] - baseline_metric["mean"], 6
                )
            paired_full_vector.setdefault(arm, {})[case_id] = metric_diffs
    policy_trace = {}
    for arm, bucket in sorted(policy_trace_by_arm.items()):
        previous_count = int(bucket["previous_count"])
        pool_survivor_count = int(bucket["pool_survivor_count"])
        observed_steps = int(bucket["observed_steps"])
        policy_trace[arm] = {
            "episodes": int(bucket["episodes"]),
            "decision_count": int(bucket["decision_count"]),
            "search_attempts_total": int(bucket["search_attempts_total"]),
            "search_attempts_max": int(bucket["search_attempts_max"]),
            "structured_evaluation_count": int(
                bucket["structured_evaluation_count"]
            ),
            "search_attempts_per_decision": (
                round(
                    bucket["search_attempts_total"]
                    / bucket["decision_count"],
                    3,
                )
                if bucket["decision_count"]
                else None
            ),
            "observed_steps": observed_steps,
            "previous_count": previous_count,
            "pool_survivor_count": pool_survivor_count,
            "static_valid_count": int(bucket["static_valid_count"]),
            "pool_survival_rate": (
                round(pool_survivor_count / previous_count, 6)
                if previous_count
                else None
            ),
            "static_survival_rate": (
                round(bucket["static_valid_count"] / previous_count, 6)
                if previous_count
                else None
            ),
            "static_survival_given_pool": (
                round(
                    bucket["static_valid_count"] / pool_survivor_count,
                    6,
                )
                if pool_survivor_count
                else None
            ),
            "would_prevent_fallback_count": int(
                bucket["would_prevent_fallback_count"]
            ),
            "validation_seconds_total": round(
                bucket["validation_seconds_total"], 6
            ),
            "validation_seconds_max": round(
                bucket["validation_seconds_max"], 6
            ),
            "validation_ms_per_observed_step": (
                round(
                    1000.0
                    * bucket["validation_seconds_total"]
                    / observed_steps,
                    3,
                )
                if observed_steps
                else None
            ),
            "deadline_overrun_count": int(
                bucket["deadline_overrun_count"]
            ),
            "temporal_chunk_observed_steps": int(
                bucket["temporal_chunk_observed_steps"]
            ),
            "temporal_chunk_scheduled_count": int(
                bucket["temporal_chunk_scheduled_count"]
            ),
            "temporal_chunk_static_valid_count": int(
                bucket["temporal_chunk_static_valid_count"]
            ),
            "temporal_chunk_static_survival_rate": (
                round(
                    bucket["temporal_chunk_static_valid_count"]
                    / bucket["temporal_chunk_scheduled_count"],
                    6,
                )
                if bucket["temporal_chunk_scheduled_count"]
                else None
            ),
            "temporal_chunk_multi_origin_steps": int(
                bucket["temporal_chunk_multi_origin_steps"]
            ),
            "temporal_chunk_consensus_steps": int(
                bucket["temporal_chunk_consensus_steps"]
            ),
            "temporal_chunk_selected_match_count": int(
                bucket["temporal_chunk_selected_match_count"]
            ),
            "temporal_chunk_selected_disagree_count": int(
                bucket["temporal_chunk_selected_disagree_count"]
            ),
            "temporal_chunk_selected_matches_any_action_count": int(
                bucket["temporal_chunk_selected_matches_any_action_count"]
            ),
            "temporal_chunk_selected_matches_any_item_count": int(
                bucket["temporal_chunk_selected_matches_any_item_count"]
            ),
            "temporal_chunk_item_consensus_steps": int(
                bucket["temporal_chunk_item_consensus_steps"]
            ),
            "temporal_chunk_selected_item_consensus_match_count": int(
                bucket[
                    "temporal_chunk_selected_item_consensus_match_count"
                ]
            ),
            "temporal_chunk_selected_item_consensus_disagree_count": int(
                bucket[
                    "temporal_chunk_selected_item_consensus_disagree_count"
                ]
            ),
            "temporal_chunk_would_prevent_fallback_count": int(
                bucket["temporal_chunk_would_prevent_fallback_count"]
            ),
            "temporal_chunk_generated_count": int(
                bucket["temporal_chunk_generated_count"]
            ),
            "temporal_chunk_validation_seconds_total": round(
                bucket["temporal_chunk_validation_seconds_total"], 6
            ),
            "temporal_chunk_validation_seconds_max": round(
                bucket["temporal_chunk_validation_seconds_max"], 6
            ),
            "temporal_chunk_generation_seconds_total": round(
                bucket["temporal_chunk_generation_seconds_total"], 6
            ),
            "temporal_chunk_generation_seconds_max": round(
                bucket["temporal_chunk_generation_seconds_max"], 6
            ),
            "temporal_chunk_ms_per_observed_step": (
                round(
                    1000.0
                    * (
                        bucket["temporal_chunk_validation_seconds_total"]
                        + bucket["temporal_chunk_generation_seconds_total"]
                    )
                    / bucket["temporal_chunk_observed_steps"],
                    3,
                )
                if bucket["temporal_chunk_observed_steps"]
                else None
            ),
            "temporal_chunk_valid_by_delay": dict(
                sorted(
                    bucket["temporal_chunk_valid_by_delay"].items(),
                    key=lambda pair: int(pair[0]),
                )
            ),
            "temporal_chunk_scheduled_by_delay": dict(
                sorted(
                    bucket["temporal_chunk_scheduled_by_delay"].items(),
                    key=lambda pair: int(pair[0]),
                )
            ),
            "temporal_chunk_survival_by_delay": {
                delay: round(
                    bucket["temporal_chunk_valid_by_delay"].get(delay, 0)
                    / scheduled,
                    6,
                )
                for delay, scheduled in sorted(
                    bucket["temporal_chunk_scheduled_by_delay"].items(),
                    key=lambda pair: int(pair[0]),
                )
                if scheduled
            },
            "rollout_observed_steps": int(
                bucket["rollout_observed_steps"]
            ),
            "rollout_candidate_count": int(
                bucket["rollout_candidate_count"]
            ),
            "rollout_eligible_count": int(
                bucket["rollout_eligible_count"]
            ),
            "rollout_non_degenerate_count": int(
                bucket["rollout_non_degenerate_count"]
            ),
            "rollout_would_change_count": int(
                bucket["rollout_would_change_count"]
            ),
            "rollout_unrestricted_change_count": int(
                bucket["rollout_unrestricted_change_count"]
            ),
            "rollout_unrestricted_within_band_count": int(
                bucket["rollout_unrestricted_within_band_count"]
            ),
            "rollout_unrestricted_within_band_rate": (
                round(
                    bucket["rollout_unrestricted_within_band_count"]
                    / bucket["rollout_unrestricted_change_count"],
                    6,
                )
                if bucket["rollout_unrestricted_change_count"]
                else None
            ),
            "rollout_enforced_count": int(
                bucket["rollout_enforced_count"]
            ),
            "rollout_q_loss_bins": dict(
                sorted(bucket["rollout_q_loss_bins"].items())
            ),
            "rollout_by_step": {
                step: {
                    **values,
                    "seconds_total": round(values["seconds_total"], 6),
                    "seconds_max": round(values["seconds_max"], 6),
                    "non_degenerate_rate": round(
                        values["non_degenerate"] / values["observed"], 6
                    ),
                    "ms_per_step": round(
                        1000.0
                        * values["seconds_total"]
                        / values["observed"],
                        3,
                    ),
                }
                for step, values in sorted(
                    bucket["rollout_by_step"].items(),
                    key=lambda pair: int(pair[0]),
                )
                if values["observed"]
            },
            "rollout_seconds_total": round(
                bucket["rollout_seconds_total"], 6
            ),
            "rollout_seconds_max": round(
                bucket["rollout_seconds_max"], 6
            ),
            "rollout_ms_per_observed_step": (
                round(
                    1000.0
                    * bucket["rollout_seconds_total"]
                    / bucket["rollout_observed_steps"],
                    3,
                )
                if bucket["rollout_observed_steps"]
                else None
            ),
        }
    def case_mean_totals(selected_cases):
        totals = {}
        for case_id, arm_stats in cases.items():
            if case_id not in selected_cases:
                continue
            for arm, metrics in arm_stats.items():
                bucket = totals.setdefault(
                    arm, {"placed": 0.0, "fill": 0.0, "cases": 0}
                )
                bucket["placed"] += float(metrics["placed"]["mean"])
                bucket["fill"] += float(metrics["fill"]["mean"])
                bucket["cases"] += 1
        for bucket in totals.values():
            bucket["placed"] = round(bucket["placed"], 3)
            bucket["fill"] = round(bucket["fill"], 3)
        return totals

    return {
        "arms": arms,
        "cases": cases,
        "development_totals": case_mean_totals(DEVELOPMENT_CASES),
        "suite_totals": case_mean_totals(set(cases)),
        "registered_development_baseline": dict(
            REGISTERED_DEVELOPMENT_BASELINE
        ),
        "baseline_arm": baseline_arm,
        "paired_vs_baseline": paired,
        "paired_full_vector_vs_baseline": paired_full_vector,
        "paired_vs_off": paired if baseline_arm == "off" else {},
        "policy_trace_by_arm": policy_trace,
        "terminal_channels": terminal_channels_by_arm,
    }


def render_markdown(summary: dict[str, Any], rows: int) -> str:
    lines = [
        "# Online policy ablation",
        "",
        f"- episode rows: {rows}; paired differences use "
        f"`{summary.get('baseline_arm', 'off')}` as the baseline arm.",
        "",
        "- fill_score / num_placed_items are the only official "
        "components the bundled simulator computes; cog / stability / "
        "placement / soft_item scores exist only in the official "
        "environment and are captured automatically when present "
        "(score_components). final CoM z is the local cog proxy.",
        "",
        "## Per arm",
        "",
        "Lower is better for the three shake columns. They are the veto in "
        "AGENT_OPERATIONS 5.05: a selection, ordering or allocation change "
        "that worsens them is not adopted on a placed gain.",
        "",
        "`final CoM z` is retained for continuity but its direction has been "
        "falsified once against an official submission pair (it improved "
        "while official cog fell 20.7%). Do not read it as a cog proxy.",
        "",
        "| arm | episodes | placed mean | fill mean | steps mean "
        "| shake max shift | shake peak KE | shake shifted "
        "| final CoM z | near-miss settles (5-30 deg) | surface TV |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for arm, stats in sorted(summary["arms"].items()):
        lines.append(
            f"| {arm} | {stats['placed']['n']} "
            f"| {stats['placed'].get('mean', '-')} "
            f"| {stats['fill'].get('mean', '-')} "
            f"| {stats['steps'].get('mean', '-')} "
            f"| {stats['shake_max_shift'].get('mean', '-')} "
            f"| {stats['shake_peak_ke'].get('mean', '-')} "
            f"| {stats['shake_shifted'].get('mean', '-')} "
            f"| {stats['com_z'].get('mean', '-')} "
            f"| {stats['near_miss'].get('mean', '-')} "
            f"| {stats['surface_tv'].get('mean', '-')} |"
        )
    lines += [
        "",
        "## Full local proxy vector",
        "",
        "No weighted total is formed. Higher is better for the two clean "
        "ratios; lower is better for shake and policy cost.",
        "",
        "| arm | shake toppled | shifted fraction | priority clean "
        "| soft clean | included rate | valid rate | placed-safe rate "
        "| policy seconds |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for arm, stats in sorted(summary["arms"].items()):
        lines.append(
            f"| {arm} | {stats['shake_toppled'].get('mean', '-')} "
            f"| {stats['shake_shifted_fraction'].get('mean', '-')} "
            f"| {stats['priority_clean'].get('mean', '-')} "
            f"| {stats['soft_clean'].get('mean', '-')} "
            f"| {stats['terminal_included'].get('mean', '-')} "
            f"| {stats['terminal_valid'].get('mean', '-')} "
            f"| {stats['terminal_placed_safe'].get('mean', '-')} "
            f"| {stats['policy_seconds'].get('mean', '-')} |"
        )
    if any(
        stats["official_cog"].get("n", 0)
        for stats in summary["arms"].values()
    ):
        lines += [
            "",
            "## Official-only components returned by the environment",
            "",
            "| arm | cog | stability | placement | soft item |",
            "|---|---:|---:|---:|---:|",
        ]
        for arm, stats in sorted(summary["arms"].items()):
            lines.append(
                f"| {arm} | {stats['official_cog'].get('mean', '-')} "
                f"| {stats['official_stability'].get('mean', '-')} "
                f"| {stats['official_placement'].get('mean', '-')} "
                f"| {stats['official_soft'].get('mean', '-')} |"
            )
    lines += [
        "",
        "## Terminal channels",
        "",
        "Counts remain categorical and are not folded into a score.",
        "",
        "| arm | channels |",
        "|---|---|",
    ]
    for arm, channels in sorted(summary.get("terminal_channels", {}).items()):
        lines.append(
            f"| {arm} | `{json.dumps(channels, sort_keys=True)}` |"
        )
    lines += [
        "",
        "## Mean totals and registered development guard",
        "",
        "| arm | development cases | dev placed total | dev fill total "
        "| suite cases | suite placed total | suite fill total |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    development_totals = summary.get("development_totals", {})
    suite_totals = summary.get("suite_totals", {})
    for arm in sorted(set(development_totals) | set(suite_totals)):
        dev = development_totals.get(arm, {})
        suite = suite_totals.get(arm, {})
        lines.append(
            f"| {arm} | {dev.get('cases', 0)} "
            f"| {dev.get('placed', '-')} | {dev.get('fill', '-')} "
            f"| {suite.get('cases', 0)} | {suite.get('placed', '-')} "
            f"| {suite.get('fill', '-')} |"
        )
    registered = summary.get("registered_development_baseline", {})
    lines += [
        "",
        "Registered current-default development baseline: "
        f"placed `{registered.get('placed')}`, fill `{registered.get('fill')}`. "
        "This is a historical guard; the simultaneously executed base arm "
        "is the causal comparator for this run.",
    ]
    policy_trace = summary.get("policy_trace_by_arm", {})
    if policy_trace:
        lines += [
            "",
            "## Search work",
            "",
            "| arm | decisions | structured records | attempts total "
            "| attempts/decision | max attempts |",
            "|---|---:|---:|---:|---:|---:|",
        ]
        for arm, trace in sorted(policy_trace.items()):
            lines.append(
                f"| {arm} | {trace['decision_count']} "
                f"| {trace['structured_evaluation_count']} "
                f"| {trace['search_attempts_total']} "
                f"| {trace['search_attempts_per_decision']} "
                f"| {trace['search_attempts_max']} |"
            )
        lines += [
            "",
            "## Cross-step incumbent telemetry",
            "",
            "| arm | steps | carried | pool survived | static valid "
            "| static survival | would prevent fallback | validation ms/step "
            "| deadline overruns |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
        for arm, trace in sorted(policy_trace.items()):
            lines.append(
                f"| {arm} | {trace['observed_steps']} "
                f"| {trace['previous_count']} "
                f"| {trace['pool_survivor_count']} "
                f"| {trace['static_valid_count']} "
                f"| {trace['static_survival_rate']} "
                f"| {trace['would_prevent_fallback_count']} "
                f"| {trace['validation_ms_per_observed_step']} "
                f"| {trace['deadline_overrun_count']} |"
            )
        lines += [
            "",
            "## Temporal chunk ensemble telemetry",
            "",
            "| arm | steps | scheduled | static valid | survival "
            "| multi-origin | action consensus | action match/disagree "
            "| any action/item match | item consensus | item match/disagree "
            "| fallback rescue | generated "
            "| ms/step | survival by delay |",
            "|---|---:|---:|---:|---:|---:|---:|---|---|---:|---|---:|---:|---:|---|",
        ]
        for arm, trace in sorted(policy_trace.items()):
            lines.append(
                f"| {arm} | {trace['temporal_chunk_observed_steps']} "
                f"| {trace['temporal_chunk_scheduled_count']} "
                f"| {trace['temporal_chunk_static_valid_count']} "
                f"| {trace['temporal_chunk_static_survival_rate']} "
                f"| {trace['temporal_chunk_multi_origin_steps']} "
                f"| {trace['temporal_chunk_consensus_steps']} "
                f"| {trace['temporal_chunk_selected_match_count']}/"
                f"{trace['temporal_chunk_selected_disagree_count']} "
                f"| {trace['temporal_chunk_selected_matches_any_action_count']}/"
                f"{trace['temporal_chunk_selected_matches_any_item_count']} "
                f"| {trace['temporal_chunk_item_consensus_steps']} "
                f"| {trace['temporal_chunk_selected_item_consensus_match_count']}/"
                f"{trace['temporal_chunk_selected_item_consensus_disagree_count']} "
                f"| {trace['temporal_chunk_would_prevent_fallback_count']} "
                f"| {trace['temporal_chunk_generated_count']} "
                f"| {trace['temporal_chunk_ms_per_observed_step']} "
                f"| `{json.dumps(trace['temporal_chunk_survival_by_delay'], sort_keys=True)}` |"
            )
        lines += [
            "",
            "## Visible-pool rollout telemetry",
            "",
            "| arm | steps | candidates | eligible | non-degenerate "
            "| would change item | unrestricted change | within band "
            "| enforced | ms/step | max seconds |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
        for arm, trace in sorted(policy_trace.items()):
            lines.append(
                f"| {arm} | {trace['rollout_observed_steps']} "
                f"| {trace['rollout_candidate_count']} "
                f"| {trace['rollout_eligible_count']} "
                f"| {trace['rollout_non_degenerate_count']} "
                f"| {trace['rollout_would_change_count']} "
                f"| {trace['rollout_unrestricted_change_count']} "
                f"| {trace['rollout_unrestricted_within_band_rate']} "
                f"| {trace['rollout_enforced_count']} "
                f"| {trace['rollout_ms_per_observed_step']} "
                f"| {trace['rollout_seconds_max']} |"
            )
        lines += [
            "",
            "### Rollout telemetry by step index",
            "",
            "| arm | step | observed | non-degenerate | rate "
            "| would change | enforced | unrestricted change | ms/step "
            "| max seconds |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
        for arm, trace in sorted(policy_trace.items()):
            for step, values in trace["rollout_by_step"].items():
                lines.append(
                    f"| {arm} | {step} | {values['observed']} "
                    f"| {values['non_degenerate']} "
                    f"| {values['non_degenerate_rate']} "
                    f"| {values['would_change']} "
                    f"| {values['enforced']} "
                    f"| {values['unrestricted_change']} "
                    f"| {values['ms_per_step']} "
                    f"| {values['seconds_max']} |"
                )
    lines += [
        "",
        "## Paired per-case difference vs "
        f"{summary.get('baseline_arm', 'off')}",
        "",
        "| arm | case | placed diff | fill diff |",
        "|---|---|---:|---:|",
    ]
    for arm, cases in sorted(summary["paired_vs_baseline"].items()):
        for case_id, diff in sorted(cases.items()):
            lines.append(
                f"| {arm} | {case_id} | {diff['placed_diff']} "
                f"| {diff['fill_diff']} |"
            )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=pathlib.Path)
    parser.add_argument("--arm", default="off")
    parser.add_argument("--risk-lambda", type=float, default=2.0)
    parser.add_argument(
        "--slide-lambda",
        type=float,
        default=0.0,
        help="RELEASE_RISK_SLIDE_LAMBDA for this episode (0 = off).",
    )
    parser.add_argument("--repeat", type=int, default=0)
    parser.add_argument(
        "--output-dir", type=pathlib.Path, default=DEFAULT_OUTPUT_DIR
    )
    parser.add_argument(
        "--summarize",
        action="store_true",
        help="Aggregate rows.jsonl into summary.md/json and exit.",
    )
    parser.add_argument(
        "--open-final-holdout",
        action="store_true",
        help=(
            "Allow a final_holdout case. Reserved for the one-shot "
            "final evaluation (protocol section 7)."
        ),
    )
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    if args.summarize:
        rows = load_rows(args.output_dir)
        summary = summarize(rows)
        (args.output_dir / "summary.json").write_text(
            json.dumps(summary, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        markdown = render_markdown(summary, len(rows))
        (args.output_dir / "summary.md").write_text(
            markdown, encoding="utf-8"
        )
        print(args.output_dir / "summary.md")
        return 0

    if args.config is None:
        raise SystemExit("--config is required unless --summarize")
    row = run_episode(
        args.config,
        args.arm,
        args.risk_lambda,
        args.repeat,
        args.output_dir,
        open_final_holdout=args.open_final_holdout,
        slide_lambda=args.slide_lambda,
    )
    print(json.dumps({k: row[k] for k in ("label", "cases")}, indent=1))
    return 0 if row["process_returncode"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
