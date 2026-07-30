from __future__ import annotations

import argparse
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


def _failure_mode(
    *,
    final_safe: bool,
    decision: dict[str, Any],
) -> str:
    if final_safe:
        return "none"
    action_source = decision.get("action_source")
    candidate_kind = decision.get("candidate_kind")
    if action_source == "fixed_fallback":
        return "fixed_fallback"
    if candidate_kind == "release_candidate":
        return "release_failure"
    if action_source == "placement_core":
        return "placement_failure"
    return "unknown"


def _starvation_signal(decision: dict[str, Any]) -> bool:
    if decision.get("action_source") != "fixed_fallback":
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


def task_b_result_rows(
    payload: dict[str, Any],
    *,
    look_ahead: int,
    selection_mode: str,
    coverage_mode: str | None = None,
    replicate: int | None = None,
    trace_events: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    evaluation = payload.get("evaluation")
    if not isinstance(evaluation, dict):
        return []
    decision = _last_decision(trace_events)
    rows = []
    for case_id, case in evaluation.items():
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
                "coverage": _coverage_values(trace_events),
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
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=pathlib.Path)
    parser.add_argument("--look-ahead", type=int, required=True)
    parser.add_argument("--selection-mode", required=True)
    parser.add_argument("--coverage-mode")
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
