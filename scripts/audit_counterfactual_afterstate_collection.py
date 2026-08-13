"""Audit whether H3 runs add unique model-visible afterstate support."""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import pathlib
from typing import Any

try:
    from scripts.evaluate_counterfactual_afterstate_value import (
        _eligible,
        _state_block_delta,
        load_run,
    )
except ModuleNotFoundError:
    from evaluate_counterfactual_afterstate_value import (
        _eligible,
        _state_block_delta,
        load_run,
    )


def _signature(row: dict[str, Any]) -> str:
    values = [
        _state_block_delta(row, block)
        for block in ("packed", "packed_visible")
    ]
    payload = json.dumps(values, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(payload.encode()).hexdigest()


def audit(runs: list[dict[str, Any]]) -> dict[str, Any]:
    if len({run["run_id"] for run in runs}) != len(runs):
        raise ValueError("run IDs must be unique")
    splits = {}
    for split in ("discovery", "late"):
        rows = [
            (run["run_id"], row)
            for run in runs
            for row in _eligible(run[split], "fill_score_proxy")
        ]
        groups: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
        for run_id, row in rows:
            groups[_signature(row)].append({
                "run_id": run_id,
                "teacher_id": row["teacher_id"],
                "case_id": row.get("case_id"),
                "root_step": row.get("root_step"),
                "relation": row["continuation_labels"]["fill_score_proxy"]
                ["relation"],
            })
        cross = [
            values for values in groups.values()
            if len({value["run_id"] for value in values}) > 1
        ]
        splits[split] = {
            "directional_rows": len(rows),
            "unique_afterstate_signatures": len(groups),
            "cross_run_duplicate_groups": len(cross),
            "rows_in_cross_run_duplicate_groups": sum(map(len, cross)),
            "effective_unique_fraction": len(groups) / len(rows) if rows else 0.0,
            "cross_run_duplicate_groups_detail": cross,
        }
    late = splits["late"]
    passes = (
        late["unique_afterstate_signatures"] >= 12
        and late["effective_unique_fraction"] >= 0.75
    )
    return {
        "schema_version": 1,
        "run_ids": [run["run_id"] for run in runs],
        "axis": "fill_score_proxy",
        "signature": (
            "exact concatenation of packed and packed+visible model feature "
            "deltas; identifiers and labels excluded"
        ),
        "splits": splits,
        "development_independence_gate": {
            "minimum_unique_late_signatures": 12,
            "minimum_unique_fraction": 0.75,
            "passed": passes,
        },
        "claim": (
            "Collection audit only. Different run IDs, serialized rows, or "
            "environment seeds are not independent model support when their "
            "model-visible afterstate signatures repeat."
        ),
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Counterfactual afterstate collection audit", "",
        f"- Runs: {', '.join(report['run_ids'])}",
        f"- Independence gate: **{'PASS' if report['development_independence_gate']['passed'] else 'FAIL'}**",
        "",
        "| Split | Directional rows | Unique signatures | Unique fraction | "
        "Cross-run duplicate groups | Rows in duplicate groups |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for split in ("discovery", "late"):
        row = report["splits"][split]
        lines.append(
            f"| {split} | {row['directional_rows']} | "
            f"{row['unique_afterstate_signatures']} | "
            f"{row['effective_unique_fraction']:.1%} | "
            f"{row['cross_run_duplicate_groups']} | "
            f"{row['rows_in_cross_run_duplicate_groups']} |"
        )
    lines.extend(["", f"> {report['claim']}", ""])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--teacher-dir", type=pathlib.Path, action="append", required=True)
    parser.add_argument("--json-output", type=pathlib.Path, required=True)
    parser.add_argument("--markdown-output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    report = audit([load_run(path) for path in args.teacher_dir])
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    args.markdown_output.write_text(render_markdown(report), encoding="utf-8")
    print(args.markdown_output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
