"""Aggregate identical-item PyBullet equivariance audit cells."""

from __future__ import annotations

import argparse
import json
import pathlib
from typing import Any


def aggregate(root: pathlib.Path) -> dict[str, Any]:
    cells = []
    for path in sorted(root.glob("*/audit.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("contract") != "identical_item_transposition_equivariance_v1":
            raise ValueError(f"{path}: unexpected contract")
        cells.append({
            "cell": path.parent.name,
            "case_id": payload.get("case_id"),
            "passed": bool(payload.get("passed")),
            "nonvacuous": bool(payload.get("nonvacuous")),
            "steps": len(payload.get("steps") or []),
            "equivariant_steps": int(payload.get("equivariant_steps", 0)),
            "false_merge_steps": int(payload.get("false_merge_steps", 0)),
            "pair": payload.get("pair"),
        })
    if not cells:
        raise ValueError(f"no symmetry audit cells below {root}")
    result = {
        "schema_version": 1,
        "contract": "identical_item_symmetry_matrix_v1",
        "cells": cells,
        "cell_count": len(cells),
        "nonvacuous_cells": sum(cell["nonvacuous"] for cell in cells),
        "passed_cells": sum(cell["passed"] for cell in cells),
        "steps": sum(cell["steps"] for cell in cells),
        "equivariant_steps": sum(cell["equivariant_steps"] for cell in cells),
        "false_merge_steps": sum(cell["false_merge_steps"] for cell in cells),
    }
    result["passed"] = bool(
        result["nonvacuous_cells"] == result["cell_count"]
        and result["passed_cells"] == result["cell_count"]
        and result["false_merge_steps"] == 0
    )
    return result


def render_markdown(result: dict[str, Any]) -> str:
    rows = [
        "# Identical-item symmetry equivariance audit",
        "",
        f"- cells: **{result['cell_count']}**",
        f"- non-vacuous cells: **{result['nonvacuous_cells']}**",
        f"- audited transitions: **{result['steps']}**",
        f"- equivariant transitions: **{result['equivariant_steps']}**",
        f"- false-merge transitions: **{result['false_merge_steps']}**",
        f"- gate: **{'PASS' if result['passed'] else 'FAIL'}**",
        "",
        "| cell | steps | non-vacuous | false merges | pass |",
        "|---|---:|---:|---:|---:|",
    ]
    rows.extend(
        f"| {cell['cell']} | {cell['steps']} | {cell['nonvacuous']} | "
        f"{cell['false_merge_steps']} | {cell['passed']} |"
        for cell in result["cells"]
    )
    return "\n".join(rows) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=pathlib.Path, required=True)
    parser.add_argument("--expected-cells", type=int, required=True)
    parser.add_argument("--json-output", type=pathlib.Path, required=True)
    parser.add_argument("--markdown-output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    result = aggregate(args.root)
    if result["cell_count"] != args.expected_cells:
        raise ValueError(
            f"expected {args.expected_cells} cells, found {result['cell_count']}"
        )
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    args.markdown_output.write_text(render_markdown(result), encoding="utf-8")
    print(args.markdown_output.read_text(encoding="utf-8"))
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
