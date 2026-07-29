from __future__ import annotations

import argparse
import json
import pathlib
from typing import Any


def _total_items(placed_count: int, placed_fraction: float) -> int | None:
    if placed_count <= 0 or placed_fraction <= 0:
        return None
    return int(round(placed_count / placed_fraction))


def build_task_b_summary(
    payload: dict[str, Any],
    *,
    look_ahead: int,
    selection_mode: str,
) -> str:
    execution = (
        "valid" if payload.get("simulator_execution_valid") is True else "invalid"
    )
    packing = (
        "complete" if payload.get("simulator_validation") is True else "incomplete"
    )
    lines = [
        f"## Task B benchmark: k={look_ahead}, {selection_mode}",
        "",
        f"- Git SHA: `{payload.get('git_sha') or 'unknown'}`",
        f"- Benchmark execution: `{execution}`",
        f"- Full packing: `{packing}`",
        "",
        "| Case | Placed | Fraction | Fill | Final step | Final item | "
        "Final safe | Policy max |",
        "| --- | ---: | ---: | ---: | ---: | ---: | --- | ---: |",
    ]

    evaluation = payload.get("evaluation")
    if not isinstance(evaluation, dict):
        lines.append("| unavailable | - | - | - | - | - | false | - |")
        return "\n".join(lines) + "\n"

    for case_id, case in evaluation.items():
        score = case.get("evaluation") if isinstance(case, dict) else None
        if not isinstance(score, dict):
            lines.append(f"| {case_id} | - | - | - | - | - | false | - |")
            continue
        metrics = score.get("step_metrics")
        last = metrics[-1] if isinstance(metrics, list) and metrics else {}
        placed_count = int(last.get("placed_count", 0))
        placed_fraction = float(score.get("num_placed_items", 0.0))
        total_items = _total_items(placed_count, placed_fraction)
        placed = (
            f"{placed_count}/{total_items}"
            if total_items is not None
            else str(placed_count)
        )
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
        lines.append(
            "| "
            f"{case_id} | {placed} | {placed_fraction:.1%} | "
            f"{float(score.get('fill_score', 0.0)):.3f} | "
            f"{last.get('step', '-')} | "
            f"{last.get('selected_item_index', '-')} | "
            f"{str(final_safe).lower()} | {policy_seconds:.3f} s |"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=pathlib.Path)
    parser.add_argument("--look-ahead", type=int, required=True)
    parser.add_argument("--selection-mode", required=True)
    parser.add_argument("--output", type=pathlib.Path)
    args = parser.parse_args()

    payload = json.loads(args.report.read_text(encoding="utf-8"))
    summary = build_task_b_summary(
        payload,
        look_ahead=args.look_ahead,
        selection_mode=args.selection_mode,
    )
    if args.output is None:
        print(summary, end="")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(summary, encoding="utf-8")
        print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
