"""Evaluate the frozen step-6 residual-affordance hybrid on a fourth run."""

from __future__ import annotations

import argparse
import json
import pathlib

try:
    from scripts.evaluate_residual_affordance_value import (
        build_affordance_rows,
        evaluate_phase_hybrid_candidate,
    )
except ModuleNotFoundError:
    from evaluate_residual_affordance_value import (
        build_affordance_rows,
        evaluate_phase_hybrid_candidate,
    )


def render_markdown(report: dict) -> str:
    gate = report["promotion_gate"]
    graphs = report["by_graph_vs_immediate"]
    action = report["global_action_confirmation"]
    lines = [
        "# Residual-affordance phase-hybrid fourth-stream gate", "",
        f"Runs: **{report['training_run_id']} / {report['discovery_run_id']} / "
        f"{report['replication_run_id']} / {report['target_run_id']}**",
        f"Target graphs / pairs / directional rows / overlap: **"
        f"{report['target_graphs']} / {report['target_sibling_pairs']} / "
        f"{report['directional_rows']} / {report['teacher_signature_overlap']}**.", "",
        "| Model | Correct |", "|---|---:|",
    ]
    for name, value in report["models"].items():
        lines.append(f"| {name} | {value['correct']}/{value['total']} |")
    lines.extend([
        "", "| Root step | Immediate | Global action | Phase hybrid | Rows |",
        "|---:|---:|---:|---:|---:|",
    ])
    for step, value in report["by_root_step"].items():
        lines.append(
            f"| {step} | {value['immediate_correct']} | "
            f"{value['global_action_correct']} | {value['phase_hybrid_correct']} | "
            f"{value['rows']} |"
        )
    lines.extend([
        "", f"Graph wins/ties/losses vs immediate: **{graphs['wins']} / "
        f"{graphs['ties']} / {graphs['losses']}**.",
        f"Global action confirmation: **"
        f"{'PASS' if action['confirmed'] else 'FAIL'}**, gain "
        f"**{action['gain_over_immediate']:+d}**, graph W/T/L "
        f"**{action['graph_wins']}/{action['graph_ties']}/"
        f"{action['graph_losses']}**.",
        "", f"Promotion gate: **{'PASS' if gate['passed'] else 'FAIL'}**; "
        f"gain vs immediate **{gate['gain_over_immediate']:+d}**, vs global action "
        f"**{gate['gain_over_global_action']:+d}** ({gate['decision']}).", "",
    ])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", type=pathlib.Path, required=True)
    parser.add_argument("--target-graphs", type=pathlib.Path, required=True)
    parser.add_argument("--target-run-id", required=True)
    parser.add_argument("--json-output", type=pathlib.Path, required=True)
    parser.add_argument("--markdown-output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    policy = json.loads(args.policy.read_text(encoding="utf-8"))
    rows, metadata = build_affordance_rows(args.target_graphs)
    report = evaluate_phase_hybrid_candidate(
        policy, args.target_run_id, rows, metadata
    )
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    args.markdown_output.write_text(render_markdown(report), encoding="utf-8")
    print(args.markdown_output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
