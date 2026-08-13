"""Apply the preregistered H4/B3 teacher-pilot acceptance gate."""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
from typing import Any

try:
    from scripts.audit_counterfactual_afterstate_collection import _signature
    from scripts.evaluate_counterfactual_afterstate_value import _eligible, load_run
except ModuleNotFoundError:
    from audit_counterfactual_afterstate_collection import _signature
    from evaluate_counterfactual_afterstate_value import _eligible, load_run


AXIS = "fill_score_proxy"


def audit(run: dict[str, Any]) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for row in _eligible(run["late"], AXIS):
        groups[_signature(row)].append(row)
    conflicts = {
        signature: sorted({
            row["continuation_labels"][AXIS]["relation"] for row in rows
        })
        for signature, rows in groups.items()
        if len({
            row["continuation_labels"][AXIS]["relation"] for row in rows
        }) > 1
    }
    representatives = [rows[0] for rows in groups.values()]
    supported = [
        row for row in representatives
        if min(
            len(row["continuation_labels"][AXIS][key])
            for key in (
                "lower_continuation_values", "higher_continuation_values"
            )
        ) >= 2
    ]
    unique = len(groups)
    coverage = len(supported) / unique if unique else 0.0
    passed = unique >= 12 and not conflicts and coverage >= 0.75
    return {
        "schema_version": 1,
        "run_id": run["run_id"],
        "axis": AXIS,
        "unique_directional_late_signatures": unique,
        "minimum_unique_directional_late_signatures": 12,
        "conflicting_signature_groups": len(conflicts),
        "conflicts": conflicts,
        "symmetric_support_signatures": len(supported),
        "symmetric_support_coverage": coverage,
        "minimum_symmetric_support_coverage": 0.75,
        "passed": passed,
        "decision": (
            "H4 multi-stream development collection may proceed."
            if passed else
            "Do not expand H4 collection or freeze an agent candidate."
        ),
    }


def render_markdown(report: dict[str, Any]) -> str:
    return "\n".join([
        "# H4/B3 teacher pilot audit", "",
        f"- Run: {report['run_id']}",
        f"- Unique directional late signatures: "
        f"{report['unique_directional_late_signatures']} / required 12",
        f"- Conflicting signature groups: "
        f"{report['conflicting_signature_groups']}",
        f"- Symmetric continuation support: "
        f"{report['symmetric_support_signatures']}/"
        f"{report['unique_directional_late_signatures']} "
        f"({report['symmetric_support_coverage']:.1%}) / required 75%",
        f"- Pilot gate: **{'PASS' if report['passed'] else 'FAIL'}**",
        "", f"> {report['decision']}", "",
    ])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--teacher-dir", type=pathlib.Path, required=True)
    parser.add_argument("--json-output", type=pathlib.Path, required=True)
    parser.add_argument("--markdown-output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    report = audit(load_run(args.teacher_dir))
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    args.markdown_output.write_text(render_markdown(report), encoding="utf-8")
    print(args.markdown_output)
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
