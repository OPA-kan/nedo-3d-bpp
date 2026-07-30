from __future__ import annotations

import argparse
import hashlib
import json
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
    selected_gate_pass_count = 0
    selected_gate_pass_physical_failure_count = 0
    shadow_rejected_but_safe_count = 0
    for decision in selected_release:
        metric = metrics_by_step.get(decision.get("step"))
        if not isinstance(metric, dict):
            continue
        rotated = float(metric.get("settle_angle_deg", 0.0)) > 30.0
        if rotated:
            rotation_over_30 += 1
        displacement = metric.get("settle_displacement_norm")
        aabb = metric.get("settle_aabb_dimensions")
        displaced = False
        if (
            isinstance(displacement, (int, float))
            and isinstance(aabb, list)
            and len(aabb) >= 2
        ):
            footprint = max(1e-9, min(float(aabb[0]), float(aabb[1])))
            if float(displacement) / footprint > 0.5:
                displacement_over_half_footprint += 1
                displaced = True
        status = metric.get("status")
        physically_invalid = (
            isinstance(status, dict)
            and status.get("is_placed_safe") is False
        )
        if physically_invalid:
            physical_failures += 1
        physically_dangerous = bool(
            rotated or displaced or physically_invalid
        )
        diagnostics = decision.get("candidate_diagnostics")
        selected_risk = (
            diagnostics.get("selected_release_risk")
            if isinstance(diagnostics, dict)
            else None
        )
        if not isinstance(selected_risk, dict):
            continue
        if selected_risk.get("passed") is True:
            selected_gate_pass_count += 1
            if physically_dangerous:
                selected_gate_pass_physical_failure_count += 1
        elif (
            selected_risk.get("mode") == "shadow"
            and selected_risk.get("passed") is False
            and not physically_dangerous
        ):
            shadow_rejected_but_safe_count += 1

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
