"""Evaluate H3/B3 afterstate models on independent signature units."""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
from typing import Any

try:
    from scripts.audit_counterfactual_afterstate_collection import _signature
    from scripts.evaluate_afterstate_spatial_representations import (
        evaluate,
    )
    from scripts.evaluate_counterfactual_afterstate_value import (
        _eligible,
        load_run,
    )
except ModuleNotFoundError:
    from audit_counterfactual_afterstate_collection import _signature
    from evaluate_afterstate_spatial_representations import evaluate
    from evaluate_counterfactual_afterstate_value import _eligible, load_run


AXIS = "fill_score_proxy"


def _deduplicate(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for row in _eligible(rows, AXIS):
        groups[_signature(row)].append(row)
    result = []
    for signature, members in groups.items():
        relations = {
            row["continuation_labels"][AXIS]["relation"] for row in members
        }
        if len(relations) != 1:
            raise ValueError(
                f"signature {signature} has conflicting relations: "
                f"{sorted(relations)}"
            )
        result.append(members[0])
    return result


def _signature_runs(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            **run,
            "discovery": _deduplicate(run["discovery"]),
            "late": _deduplicate(run["late"]),
        }
        for run in runs
    ]


def _has_symmetric_continuation_support(
    row: dict[str, Any], minimum: int = 2,
) -> bool:
    label = row["continuation_labels"][AXIS]
    return (
        len(label["lower_continuation_values"]) >= minimum
        and len(label["higher_continuation_values"]) >= minimum
    )


def _filter_late_support(
    runs: list[dict[str, Any]], minimum: int = 2,
) -> list[dict[str, Any]]:
    return [
        {
            **run,
            "late": [
                row for row in run["late"]
                if _has_symmetric_continuation_support(row, minimum)
            ],
        }
        for run in runs
    ]


def evaluate_signature_policy(runs: list[dict[str, Any]]) -> dict[str, Any]:
    signature_runs = _signature_runs(runs)
    unfiltered = evaluate([], signature_runs)
    supported_runs = _filter_late_support(signature_runs)
    supported = evaluate([], supported_runs)
    total = unfiltered["total_directional_rows"]
    retained = supported["total_directional_rows"]
    coverage = retained / total if total else 0.0
    best_models = unfiltered["best_models"]
    unique_best = len(best_models) == 1
    development_gate = unique_best and unfiltered[
        "zero_error_representation_found"
    ]
    support_gate = (
        retained >= 12
        and coverage >= 0.75
        and supported["zero_error_representation_found"]
    )
    return {
        "schema_version": 1,
        "run_ids": [run["run_id"] for run in runs],
        "unit": (
            "one exact packed plus packed-visible afterstate-delta signature; "
            "consistent duplicates collapsed without multiplicity weighting"
        ),
        "whole_stream_leave_one_out": unfiltered,
        "development_freeze_gate": {
            "unique_best_model": best_models[0] if unique_best else None,
            "unique_best": unique_best,
            "zero_errors": unfiltered["zero_error_representation_found"],
            "passed": development_gate,
        },
        "symmetric_continuation_support": {
            "minimum_values_per_afterstate": 2,
            "retained_signature_units": retained,
            "total_signature_units": total,
            "coverage": coverage,
            "minimum_units": 12,
            "minimum_coverage": 0.75,
            "model_evaluation": supported,
            "passed": support_gate,
        },
        "candidate_frozen": development_gate and support_gate,
        "decision": (
            "Freeze no agent candidate. Keep the rotate-000-7 holdout sealed."
            if not (development_gate and support_gate)
            else "The development gates pass; the preregistered holdout may be evaluated."
        ),
    }


def render_markdown(report: dict[str, Any]) -> str:
    raw = report["whole_stream_leave_one_out"]
    gate = report["development_freeze_gate"]
    support = report["symmetric_continuation_support"]
    filtered = support["model_evaluation"]
    lines = [
        "# H3/B3 signature-unit policy audit", "",
        f"- Runs: {', '.join(report['run_ids'])}",
        f"- Best development model: {', '.join(raw['best_models'])} "
        f"({raw['best_correct']}/{raw['total_directional_rows']})",
        f"- Zero-error development gate: **{'PASS' if gate['passed'] else 'FAIL'}**",
        f"- Symmetric continuation support: "
        f"{support['retained_signature_units']}/{support['total_signature_units']} "
        f"({support['coverage']:.1%})",
        f"- Supported-set best: {', '.join(filtered['best_models'])} "
        f"({filtered['best_correct']}/{filtered['total_directional_rows']})",
        f"- Support gate: **{'PASS' if support['passed'] else 'FAIL'}**",
        f"- Agent candidate frozen: **{'yes' if report['candidate_frozen'] else 'no'}**",
        "", "| Representation | Correct |", "|---|---:|",
    ]
    for name, row in raw["models"].items():
        lines.append(f"| {name} | {row['correct']}/{row['total']} |")
    lines.extend(["", f"> {report['decision']}", ""])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--teacher-dir", type=pathlib.Path, action="append", required=True)
    parser.add_argument("--json-output", type=pathlib.Path, required=True)
    parser.add_argument("--markdown-output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    report = evaluate_signature_policy(
        [load_run(path) for path in args.teacher_dir]
    )
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    args.markdown_output.write_text(render_markdown(report), encoding="utf-8")
    print(args.markdown_output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
