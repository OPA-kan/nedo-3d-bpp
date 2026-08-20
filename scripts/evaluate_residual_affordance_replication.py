"""Evaluate the frozen residual-affordance action candidate on a third run."""

from __future__ import annotations

import argparse
import json
import pathlib

try:
    from scripts.evaluate_residual_affordance_value import (
        build_affordance_rows,
        evaluate_replication_candidate,
        freeze_phase_hybrid_candidate,
    )
except ModuleNotFoundError:
    from evaluate_residual_affordance_value import (
        build_affordance_rows,
        evaluate_replication_candidate,
        freeze_phase_hybrid_candidate,
    )


def render_markdown(report: dict) -> str:
    immediate = report["models"]["immediate_score"]
    learned = report["models"]["frozen_action_geometry"]
    gate = report["replication_gate"]
    paired = report["paired_vs_immediate"]
    graphs = report["by_graph_vs_immediate"]
    return "\n".join([
        "# Residual-affordance third-stream replication", "",
        f"Training / discovery / target: **{report['training_run_id']} / "
        f"{report['discovery_run_id']} / {report['target_run_id']}**",
        f"Target graphs / pairs / directional rows / signature overlap: "
        f"**{report['target_graphs']} / {report['target_sibling_pairs']} / "
        f"{report['directional_rows']} / {report['teacher_signature_overlap']}**.", "",
        "| Model | Correct |", "|---|---:|",
        f"| immediate_score | {immediate['correct']}/{immediate['total']} |",
        f"| frozen_action_geometry | {learned['correct']}/{learned['total']} |", "",
        f"Pair wins/ties/losses: **{paired['wins']} / "
        f"{paired['ties_both_correct'] + paired['ties_both_wrong']} / "
        f"{paired['losses']}**.",
        f"Graph wins/ties/losses: **{graphs['wins']} / {graphs['ties']} / "
        f"{graphs['losses']}**.", "",
        f"Replication gate: **{'PASS' if gate['passed'] else 'FAIL'}**; "
        f"gain **{gate['gain_over_immediate']:+d}** ({gate['decision']}).", "",
    ])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", type=pathlib.Path, required=True)
    parser.add_argument("--target-graphs", type=pathlib.Path, required=True)
    parser.add_argument("--target-run-id", required=True)
    parser.add_argument("--json-output", type=pathlib.Path, required=True)
    parser.add_argument("--markdown-output", type=pathlib.Path, required=True)
    parser.add_argument("--hybrid-policy-output", type=pathlib.Path)
    args = parser.parse_args()
    policy = json.loads(args.policy.read_text(encoding="utf-8"))
    rows, metadata = build_affordance_rows(args.target_graphs)
    report = evaluate_replication_candidate(
        policy, args.target_run_id, rows, metadata
    )
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    args.markdown_output.write_text(render_markdown(report), encoding="utf-8")
    if args.hybrid_policy_output is not None:
        hybrid = freeze_phase_hybrid_candidate(
            policy, args.target_run_id, rows, report
        )
        args.hybrid_policy_output.parent.mkdir(parents=True, exist_ok=True)
        args.hybrid_policy_output.write_text(
            json.dumps(hybrid, indent=2) + "\n", encoding="utf-8"
        )
    print(args.markdown_output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
