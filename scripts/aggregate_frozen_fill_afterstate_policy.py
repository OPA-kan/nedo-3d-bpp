"""Aggregate frozen fill-policy reports under a preregistered gate."""

from __future__ import annotations

import argparse
import json
import pathlib

try:
    from scripts.evaluate_frozen_fill_afterstate_policy import (
        aggregate_fallback_reports,
    )
except ModuleNotFoundError:
    from evaluate_frozen_fill_afterstate_policy import aggregate_fallback_reports


def render_markdown(report: dict) -> str:
    paired = report["paired_vs_action_geometry"]
    lines = [
        "# Frozen distributional fill fallback confirmation", "",
        f"- Target runs: {', '.join(report['target_run_ids'])}",
        f"- Correct: {report['correct']}/{report['rows']}",
        "- Action geometry: "
        f"{report['action_geometry_correct']}/{report['rows']}",
        "- Afterstate consensus used: "
        f"{report['afterstate_rows']}/{report['rows']}",
        "- Paired W/T/L: "
        f"{paired['wins']}/{paired['ties']}/{paired['losses']} "
        f"(exact two-sided p={paired['exact_two_sided_sign_p']:.6g})",
        f"- Frozen gate: **{'PASS' if report['gate_passed'] else 'FAIL'}**",
        "", "| Run | Correct | Action | Afterstate use | Non-regression |",
        "|---|---:|---:|---:|---|",
    ]
    for row in report["per_run"]:
        lines.append(
            f"| {row['target_run_id']} | {row['correct']}/{row['rows']} | "
            f"{row['action_geometry_correct']}/{row['rows']} | "
            f"{row['afterstate_rows']}/{row['rows']} | "
            f"{'yes' if row['non_regression'] else 'no'} |"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", type=pathlib.Path, required=True)
    parser.add_argument("--evaluation", type=pathlib.Path, action="append", required=True)
    parser.add_argument("--json-output", type=pathlib.Path, required=True)
    parser.add_argument("--markdown-output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    policy = json.loads(args.policy.read_text(encoding="utf-8"))
    reports = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in args.evaluation
    ]
    report = aggregate_fallback_reports(policy, reports)
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    args.markdown_output.write_text(render_markdown(report), encoding="utf-8")
    print(args.markdown_output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
