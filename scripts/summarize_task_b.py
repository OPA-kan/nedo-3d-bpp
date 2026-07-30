from __future__ import annotations

import argparse
import hashlib
import json
import math
import pathlib
from typing import Any


def _total_items(placed_count: int, placed_fraction: float) -> int | None:
    if placed_count <= 0 or placed_fraction <= 0:
        return None
    return int(round(placed_count / placed_fraction))


def _last_decision(trace_events: list[dict[str, Any]] | None) -> dict[str, Any]:
    decisions = [
        event
        for event in (trace_events or [])
        if isinstance(event, dict) and event.get("event") == "decision"
    ]
    return decisions[-1] if decisions else {}


def _trace_episodes(
    trace_events: list[dict[str, Any]] | None,
) -> list[list[dict[str, Any]]]:
    episodes = []
    current = []
    for event in trace_events or []:
        if not isinstance(event, dict):
            continue
        if event.get("event") == "init" and any(
            record.get("event") == "decision" for record in current
        ):
            episodes.append(current)
            current = []
        current.append(event)
    if any(record.get("event") == "decision" for record in current):
        episodes.append(current)
    return episodes


def _failure_mode(
    *,
    final_safe: bool,
    decision: dict[str, Any],
) -> str:
    if final_safe:
        return "none"
    action_source = decision.get("action_source")
    candidate_kind = decision.get("candidate_kind")
    if action_source in {
        "fixed_fallback",
        "unsafe_protocol_fallback",
    }:
        return "unsafe_protocol_fallback"
    if candidate_kind == "release_candidate":
        return "release_failure"
    if action_source == "placement_core":
        return "placement_failure"
    return "unknown"


def _starvation_signal(decision: dict[str, Any]) -> bool:
    if decision.get("action_source") not in {
        "fixed_fallback",
        "unsafe_protocol_fallback",
    }:
        return False
    selected_item = decision.get("selected_item_index")
    lifecycle = decision.get("item_lifecycle")
    if not isinstance(lifecycle, list):
        return False
    record = next(
        (
            item
            for item in lifecycle
            if isinstance(item, dict)
            and item.get("item_index") == selected_item
        ),
        None,
    )
    return bool(
        isinstance(record, dict)
        and record.get("selected_step") is None
        and record.get("candidate_topk_steps")
    )


def _coverage_values(
    trace_events: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    decisions = [
        event
        for event in (trace_events or [])
        if isinstance(event, dict) and event.get("event") == "decision"
    ]

    def mean_ratio(
        scope: str,
        metric: str,
        class_name: str | None = None,
    ) -> float | None:
        values = []
        for decision in decisions:
            coverage = decision.get("coverage")
            if not isinstance(coverage, dict):
                continue
            metrics = coverage.get(scope)
            if scope == "by_class" and isinstance(metrics, dict):
                metrics = metrics.get(class_name)
            if not isinstance(metrics, dict):
                continue
            value = metrics.get(metric)
            if isinstance(value, (int, float)):
                values.append(float(value))
        if not values:
            return None
        return sum(values) / len(values)

    def ratios(scope: str, class_name: str | None = None):
        return {
            "c1": mean_ratio(
                scope, "included_over_visible", class_name
            ),
            "c2": mean_ratio(
                scope, "started_over_included", class_name
            ),
            "c3": mean_ratio(
                scope, "generated_over_started", class_name
            ),
        }

    return {
        "overall": ratios("overall"),
        "by_class": {
            class_name: ratios("by_class", class_name)
            for class_name in ("normal", "soft", "priority")
        },
    }


ROTATION_LABEL_DEG = 30.0
DISPLACEMENT_LABEL_FOOTPRINT_RATIO = 0.5

# Physical outcomes are kept apart on purpose. `physically_dangerous` is the
# historical composite (rotation OR 3D displacement OR not placed safe) and
# stays only so existing series remain comparable; anything that models the
# outcome should use the separated labels instead.
_SEPARATED_LABEL_NAMES = (
    "rotated_over_30",
    "displaced_over_half_footprint",
    "horizontal_displaced_over_half_footprint",
    "not_placed_safe",
    "not_valid",
    "not_included",
    "physically_dangerous",
)

# 2x2 over SELECTED release candidates only. These cells are conditioned on
# the ranking having chosen the candidate, so they are not gate-wide.
_CONFUSION_CELL_NAMES = (
    "selected_gate_pass_physical_safe_count",
    "selected_gate_pass_physical_failure_count",
    "selected_gate_reject_physical_safe_count",
    "selected_gate_reject_physical_failure_count",
)

SELECTED_CONFUSION_SCOPE = (
    "selected_release_candidates_only; conditioned on ranking selection, "
    "not a gate-wide precision/recall"
)


def _finite(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    return value if math.isfinite(value) else None


def separated_physical_labels(metric: dict[str, Any]) -> dict[str, Any]:
    """
    Split one step's settle telemetry into independent outcomes.

    Returns the continuous quantities (angle, horizontal and vertical
    displacement) next to the individual boolean labels, so a caller can
    threshold them differently without re-deriving anything.
    """
    angle_deg = _finite(metric.get("settle_angle_deg"))
    displacement_norm = _finite(metric.get("settle_displacement_norm"))

    displacement_xyz = metric.get("settle_displacement_xyz")
    d_xy = None
    d_z = None
    if isinstance(displacement_xyz, list) and len(displacement_xyz) >= 3:
        dx = _finite(displacement_xyz[0])
        dy = _finite(displacement_xyz[1])
        dz = _finite(displacement_xyz[2])
        if dx is not None and dy is not None:
            d_xy = math.hypot(dx, dy)
        if dz is not None:
            d_z = abs(dz)

    aabb = metric.get("settle_aabb_dimensions")
    footprint = None
    if isinstance(aabb, list) and len(aabb) >= 2:
        side_x = _finite(aabb[0])
        side_y = _finite(aabb[1])
        if side_x is not None and side_y is not None:
            footprint = max(1e-9, min(side_x, side_y))

    def over_footprint(distance: float | None) -> bool:
        if distance is None or footprint is None:
            return False
        return distance / footprint > DISPLACEMENT_LABEL_FOOTPRINT_RATIO

    status = metric.get("status")
    status = status if isinstance(status, dict) else {}

    rotated = angle_deg is not None and angle_deg > ROTATION_LABEL_DEG
    displaced = over_footprint(displacement_norm)
    not_placed_safe = status.get("is_placed_safe") is False

    return {
        "settle_angle_deg": angle_deg,
        "settle_displacement_norm": displacement_norm,
        "settle_displacement_xy": d_xy,
        "settle_displacement_z": d_z,
        "settle_footprint": footprint,
        "rotated_over_30": rotated,
        "displaced_over_half_footprint": displaced,
        "horizontal_displaced_over_half_footprint": over_footprint(d_xy),
        "not_placed_safe": not_placed_safe,
        "not_valid": status.get("is_valid") is False,
        "not_included": status.get("is_included") is False,
        "physically_dangerous": bool(
            rotated or displaced or not_placed_safe
        ),
    }


def _release_values(
    trace_events: list[dict[str, Any]] | None,
    step_metrics: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    decisions = [
        event
        for event in (trace_events or [])
        if isinstance(event, dict) and event.get("event") == "decision"
    ]
    metrics_by_step = {
        metric.get("step"): metric
        for metric in (step_metrics or [])
        if isinstance(metric, dict)
    }
    action_commands = [
        decision.get("action_command")
        for decision in decisions
        if isinstance(decision.get("action_command"), dict)
    ]
    action_sequence_sha256 = (
        hashlib.sha256(
            json.dumps(
                action_commands,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        if action_commands
        else None
    )
    gate_evaluated = 0
    gate_would_reject = 0
    gate_enforced_rejections = 0
    release_static_count = 0
    release_gate_pass_count = 0
    release_gate_reject_count = 0
    release_all_rejected_count = 0
    release_static_step_count = 0
    protocol_fallback_count = 0
    gate_modes = set()
    selected_release = []
    for decision in decisions:
        diagnostics = decision.get("candidate_diagnostics")
        gate = (
            diagnostics.get("release_risk_gate")
            if isinstance(diagnostics, dict)
            else None
        )
        if isinstance(gate, dict):
            gate_evaluated += int(gate.get("evaluated", 0))
            gate_would_reject += int(gate.get("would_reject", 0))
            gate_enforced_rejections += int(
                gate.get("enforced_rejections", 0)
            )
            if gate.get("mode"):
                gate_modes.add(str(gate["mode"]))
        if isinstance(diagnostics, dict):
            step_static_count = int(
                diagnostics.get("release_static_count", 0)
            )
            release_static_count += step_static_count
            release_static_step_count += int(step_static_count > 0)
            release_gate_pass_count += int(
                diagnostics.get("release_gate_pass_count", 0)
            )
            release_gate_reject_count += int(
                diagnostics.get("release_gate_reject_count", 0)
            )
            release_all_rejected_count += int(
                bool(diagnostics.get("release_all_rejected", False))
            )
        if decision.get("action_source") in {
            "fixed_fallback",
            "unsafe_protocol_fallback",
        }:
            protocol_fallback_count += 1
        if decision.get("candidate_kind") == "release_candidate":
            selected_release.append(decision)

    rotation_over_30 = 0
    displacement_over_half_footprint = 0
    physical_failures = 0
    labels = {name: 0 for name in _SEPARATED_LABEL_NAMES}
    labelled_steps = 0
    confusion = {name: 0 for name in _CONFUSION_CELL_NAMES}
    selected_gate_pass_count = 0
    selected_gate_pass_physical_failure_count = 0
    shadow_rejected_but_safe_count = 0
    for decision in selected_release:
        metric = metrics_by_step.get(decision.get("step"))
        if not isinstance(metric, dict):
            continue
        outcome = separated_physical_labels(metric)
        rotated = outcome["rotated_over_30"]
        displaced = outcome["displaced_over_half_footprint"]
        if rotated:
            rotation_over_30 += 1
        if displaced:
            displacement_over_half_footprint += 1
        if outcome["not_placed_safe"]:
            physical_failures += 1
        labelled_steps += 1
        for name in _SEPARATED_LABEL_NAMES:
            labels[name] += int(bool(outcome[name]))
        # Kept as the historical composite so existing series stay
        # comparable; the separated labels above are the ones to model on.
        physically_dangerous = bool(outcome["physically_dangerous"])
        diagnostics = decision.get("candidate_diagnostics")
        selected_risk = (
            diagnostics.get("selected_release_risk")
            if isinstance(diagnostics, dict)
            else None
        )
        if not isinstance(selected_risk, dict):
            continue
        passed = selected_risk.get("passed")
        if passed is True:
            selected_gate_pass_count += 1
            if physically_dangerous:
                selected_gate_pass_physical_failure_count += 1
                confusion["selected_gate_pass_physical_failure_count"] += 1
            else:
                confusion["selected_gate_pass_physical_safe_count"] += 1
        elif passed is False:
            if physically_dangerous:
                confusion["selected_gate_reject_physical_failure_count"] += 1
            else:
                confusion["selected_gate_reject_physical_safe_count"] += 1
                if selected_risk.get("mode") == "shadow":
                    shadow_rejected_but_safe_count += 1

    selected_gate_reject_count = (
        confusion["selected_gate_reject_physical_failure_count"]
        + confusion["selected_gate_reject_physical_safe_count"]
    )
    selected_scored_count = selected_gate_pass_count + selected_gate_reject_count

    return {
        "gate_mode_observed": (
            ",".join(sorted(gate_modes)) if gate_modes else None
        ),
        "action_sequence_sha256": action_sequence_sha256,
        "gate_evaluated": gate_evaluated,
        "gate_would_reject": gate_would_reject,
        "gate_enforced_rejections": gate_enforced_rejections,
        "release_static_count": release_static_count,
        "release_gate_pass_count": release_gate_pass_count,
        "release_gate_reject_count": release_gate_reject_count,
        "release_all_rejected_count": release_all_rejected_count,
        "release_static_step_count": release_static_step_count,
        "protocol_fallback_count": protocol_fallback_count,
        "gate_pass_ratio": (
            release_gate_pass_count / gate_evaluated
            if gate_evaluated > 0
            else None
        ),
        "release_all_rejected_ratio": (
            release_all_rejected_count / release_static_step_count
            if release_static_step_count > 0
            else None
        ),
        "protocol_fallback_ratio": (
            protocol_fallback_count / len(decisions)
            if decisions
            else None
        ),
        "gate_rejection_ratio": (
            gate_would_reject / gate_evaluated
            if gate_evaluated > 0
            else None
        ),
        "selected_release_count": len(selected_release),
        "rotation_over_30_count": rotation_over_30,
        "large_displacement_count": displacement_over_half_footprint,
        "physical_failure_count": physical_failures,
        "selected_gate_pass_count": selected_gate_pass_count,
        "selected_gate_pass_physical_failure_count": (
            selected_gate_pass_physical_failure_count
        ),
        "gate_passing_release_failure_rate": (
            selected_gate_pass_physical_failure_count
            / selected_gate_pass_count
            if selected_gate_pass_count > 0
            else None
        ),
        "shadow_rejected_but_safe_count": (
            shadow_rejected_but_safe_count
        ),
        # --- 2x2 over selected release candidates only -------------------
        # Conditioned on the ranking having selected the candidate. Do not
        # report these as the gate's precision/recall.
        "selected_confusion_scope": SELECTED_CONFUSION_SCOPE,
        "selected_gate_reject_count": selected_gate_reject_count,
        "selected_gate_scored_count": selected_scored_count,
        **{name: confusion[name] for name in _CONFUSION_CELL_NAMES},
        "selected_gate_reject_physical_failure_rate": (
            confusion["selected_gate_reject_physical_failure_count"]
            / selected_gate_reject_count
            if selected_gate_reject_count > 0
            else None
        ),
        # --- separated physical labels over selected release candidates --
        "selected_labelled_count": labelled_steps,
        **{
            f"selected_{name}_count": labels[name]
            for name in _SEPARATED_LABEL_NAMES
        },
    }


def task_b_result_rows(
    payload: dict[str, Any],
    *,
    look_ahead: int,
    selection_mode: str,
    coverage_mode: str | None = None,
    risk_gate_mode: str | None = None,
    replicate: int | None = None,
    trace_events: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    evaluation = payload.get("evaluation")
    if not isinstance(evaluation, dict):
        return []
    trace_episodes = _trace_episodes(trace_events)
    case_count = len(evaluation)
    rows = []
    for case_index, (case_id, case) in enumerate(evaluation.items()):
        case_trace = (
            trace_episodes[case_index]
            if len(trace_episodes) == case_count
            else trace_events
        )
        decision = _last_decision(case_trace)
        score = case.get("evaluation") if isinstance(case, dict) else None
        if not isinstance(score, dict):
            continue
        metrics = score.get("step_metrics")
        last = metrics[-1] if isinstance(metrics, list) and metrics else {}
        placed_count = int(last.get("placed_count", 0))
        placed_fraction = float(score.get("num_placed_items", 0.0))
        final_status = last.get("status")
        final_safe = (
            final_status.get("is_placed_safe") is True
            if isinstance(final_status, dict)
            else False
        )
        time_results = case.get("time_results")
        policy_seconds = (
            float(time_results.get("policy", 0.0))
            if isinstance(time_results, dict)
            else 0.0
        )
        rows.append(
            {
                "case": case_id,
                "look_ahead": int(look_ahead),
                "selection_mode": selection_mode,
                "coverage_mode": coverage_mode or "unspecified",
                "risk_gate_mode": risk_gate_mode or "unspecified",
                "replicate": replicate,
                "placed_count": placed_count,
                "total_items": _total_items(
                    placed_count, placed_fraction
                ),
                "placed_fraction": placed_fraction,
                "fill_score": float(score.get("fill_score", 0.0)),
                "final_step": last.get("step"),
                "final_item": last.get("selected_item_index"),
                "final_safe": final_safe,
                "policy_seconds": policy_seconds,
                "failure_mode": _failure_mode(
                    final_safe=final_safe,
                    decision=decision,
                ),
                "starvation_signal": _starvation_signal(decision),
                "coverage": _coverage_values(case_trace),
                "release": _release_values(
                    case_trace,
                    metrics if isinstance(metrics, list) else None,
                ),
            }
        )
    return rows


def _percent(value: Any) -> str:
    if not isinstance(value, (int, float)):
        return "-"
    return f"{float(value):.1%}"


def build_task_b_summary(
    payload: dict[str, Any],
    *,
    look_ahead: int,
    selection_mode: str,
    coverage_mode: str | None = None,
    risk_gate_mode: str | None = None,
    replicate: int | None = None,
    trace_events: list[dict[str, Any]] | None = None,
) -> str:
    execution = (
        "valid" if payload.get("simulator_execution_valid") is True else "invalid"
    )
    packing = (
        "complete" if payload.get("simulator_validation") is True else "incomplete"
    )
    title_parts = [f"k={look_ahead}"]
    if replicate is not None:
        title_parts.append(f"r={replicate}")
    title_parts.append(selection_mode)
    if coverage_mode is not None:
        title_parts.append(coverage_mode)
    if risk_gate_mode is not None:
        title_parts.append(f"risk={risk_gate_mode}")
    lines = [
        f"## Task B benchmark: {', '.join(title_parts)}",
        "",
        f"- Git SHA: `{payload.get('git_sha') or 'unknown'}`",
        f"- Benchmark execution: `{execution}`",
        f"- Full packing: `{packing}`",
        "",
        "| Case | Placed | Fraction | Fill | Final step | Final item | "
        "Final safe | Policy max |",
        "| --- | ---: | ---: | ---: | ---: | ---: | --- | ---: |",
    ]

    rows = task_b_result_rows(
        payload,
        look_ahead=look_ahead,
        selection_mode=selection_mode,
        coverage_mode=coverage_mode,
        risk_gate_mode=risk_gate_mode,
        replicate=replicate,
        trace_events=trace_events,
    )
    if not rows:
        lines.append("| unavailable | - | - | - | - | - | false | - |")
        return "\n".join(lines) + "\n"

    for row in rows:
        placed = (
            f"{row['placed_count']}/{row['total_items']}"
            if row["total_items"] is not None
            else str(row["placed_count"])
        )
        lines.append(
            "| "
            f"{row['case']} | {placed} | {row['placed_fraction']:.1%} | "
            f"{row['fill_score']:.3f} | "
            f"{row['final_step']} | "
            f"{row['final_item']} | "
            f"{str(row['final_safe']).lower()} | "
            f"{row['policy_seconds']:.3f} s |"
        )
    lines.extend(
        [
            "",
            "### Mean coverage and failure",
            "",
            "| Case | C1 included/visible | C2 started/included | "
            "C3 generated/started | Failure | Starvation signal |",
            "| --- | ---: | ---: | ---: | --- | --- |",
        ]
    )
    for row in rows:
        overall = row["coverage"]["overall"]
        lines.append(
            f"| {row['case']} | {_percent(overall['c1'])} | "
            f"{_percent(overall['c2'])} | "
            f"{_percent(overall['c3'])} | "
            f"{row['failure_mode']} | "
            f"{str(row['starvation_signal']).lower()} |"
        )
    lines.extend(
        [
            "",
            "### Mean class coverage",
            "",
            "| Case | Class | C1 | C2 | C3 |",
            "| --- | --- | ---: | ---: | ---: |",
        ]
    )
    for row in rows:
        for class_name in ("normal", "soft", "priority"):
            values = row["coverage"]["by_class"][class_name]
            lines.append(
                f"| {row['case']} | {class_name} | "
                f"{_percent(values['c1'])} | "
                f"{_percent(values['c2'])} | "
                f"{_percent(values['c3'])} |"
            )
    lines.extend(
        [
            "",
            "### Release risk gate",
            "",
            "| Case | Gate mode | Static | Gate pass | Pass rate | "
            "Gate reject | All rejected | All-reject rate | "
            "Protocol fallback | Evaluated | Enforced | "
            "Selected release | >30° | Large displacement | "
            "Physical failure | Gate-pass failure rate | "
            "Shadow reject but safe |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | "
            "---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | "
            "---: |",
        ]
    )
    for row in rows:
        release = row["release"]
        lines.append(
            f"| {row['case']} | {row['risk_gate_mode']} | "
            f"{release['release_static_count']} | "
            f"{release['release_gate_pass_count']} | "
            f"{_percent(release['gate_pass_ratio'])} | "
            f"{release['release_gate_reject_count']} | "
            f"{release['release_all_rejected_count']} | "
            f"{_percent(release['release_all_rejected_ratio'])} | "
            f"{release['protocol_fallback_count']} | "
            f"{release['gate_evaluated']} | "
            f"{release['gate_enforced_rejections']} | "
            f"{release['selected_release_count']} | "
            f"{release['rotation_over_30_count']} | "
            f"{release['large_displacement_count']} | "
            f"{release['physical_failure_count']} | "
            f"{_percent(release['gate_passing_release_failure_rate'])} | "
            f"{release['shadow_rejected_but_safe_count']} |"
        )
    lines.extend(
        [
            "",
            "### Selected-release confusion matrix",
            "",
            "Counts cover only release candidates the ranking actually "
            "selected, so they are conditioned on that selection and are "
            "**not** the gate's overall precision/recall. In `enforce` the "
            "reject column is empty by construction, because rejected "
            "candidates never reach selection.",
            "",
            "| Case | Risk gate | Scored | TN pass/safe | FN pass/failed | "
            "FP reject/safe | TP reject/failed | Reject failure rate |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in rows:
        release = row["release"]
        lines.append(
            f"| {row['case']} | {row['risk_gate_mode']} | "
            f"{release['selected_gate_scored_count']} | "
            f"{release['selected_gate_pass_physical_safe_count']} | "
            f"{release['selected_gate_pass_physical_failure_count']} | "
            f"{release['selected_gate_reject_physical_safe_count']} | "
            f"{release['selected_gate_reject_physical_failure_count']} | "
            f"{_percent(release['selected_gate_reject_physical_failure_rate'])} |"
        )
    lines.extend(
        [
            "",
            "### Selected-release physical labels",
            "",
            "Independent outcomes, not the composite. `Dangerous` is the "
            "historical OR of rotation, 3D displacement and not-placed-safe, "
            "kept only for continuity with earlier runs.",
            "",
            "| Case | Labelled | Rotated >30° | Displaced 3D | "
            "Displaced XY | Not placed safe | Not valid | Not included | "
            "Dangerous |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in rows:
        release = row["release"]
        lines.append(
            f"| {row['case']} | "
            f"{release['selected_labelled_count']} | "
            f"{release['selected_rotated_over_30_count']} | "
            f"{release['selected_displaced_over_half_footprint_count']} | "
            f"{release['selected_horizontal_displaced_over_half_footprint_count']} | "
            f"{release['selected_not_placed_safe_count']} | "
            f"{release['selected_not_valid_count']} | "
            f"{release['selected_not_included_count']} | "
            f"{release['selected_physically_dangerous_count']} |"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=pathlib.Path)
    parser.add_argument("--look-ahead", type=int, required=True)
    parser.add_argument("--selection-mode", required=True)
    parser.add_argument("--coverage-mode")
    parser.add_argument("--risk-gate-mode")
    parser.add_argument("--replicate", type=int)
    parser.add_argument("--trace", type=pathlib.Path)
    parser.add_argument("--output", type=pathlib.Path)
    parser.add_argument("--json-output", type=pathlib.Path)
    args = parser.parse_args()

    payload = json.loads(args.report.read_text(encoding="utf-8"))
    trace_events = None
    if args.trace is not None and args.trace.exists():
        trace_events = [
            json.loads(line)
            for line in args.trace.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    summary = build_task_b_summary(
        payload,
        look_ahead=args.look_ahead,
        selection_mode=args.selection_mode,
        coverage_mode=args.coverage_mode,
        risk_gate_mode=args.risk_gate_mode,
        replicate=args.replicate,
        trace_events=trace_events,
    )
    if args.output is None:
        print(summary, end="")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(summary, encoding="utf-8")
        print(args.output)
    if args.json_output is not None:
        rows = task_b_result_rows(
            payload,
            look_ahead=args.look_ahead,
            selection_mode=args.selection_mode,
            coverage_mode=args.coverage_mode,
            risk_gate_mode=args.risk_gate_mode,
            replicate=args.replicate,
            trace_events=trace_events,
        )
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(
            json.dumps(rows, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(args.json_output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
